#!/usr/bin/env python3
"""INV-DEADCODE-01 — Handler TERGABUNG: statement mati setelah `return`.

KELAS BUG YANG LOLOS SEMUA GATE SEBELUMNYA (ditemukan FASE 20)
--------------------------------------------------------------
`rahaza_payroll_runs.export_run_excel()` berakhir dengan
`return StreamingResponse(...)`, lalu **31 baris berikutnya masih di dalam fungsi
yang sama**: sebuah handler CSV yang lengkap (`await require_auth`, query Mongo,
`csv.writer`, `return StreamingResponse(media_type="text/csv")`).

Artinya dua endpoint TERGABUNG jadi satu fungsi dan dekorator
`@router.get("/payroll-runs/{run_id}/export")` HILANG. FastAPI tidak pernah
mendaftarkan route CSV-nya, sehingga tombol "Download CSV" di
`RahazaPayrollRunModule` selalu gagal — tanpa error di log, tanpa test merah.

Kenapa gate lain buta:
  · CHECK D (orphan handler) mencari `def` TANPA dekorator → di sini tidak ada
    `def` baru sama sekali, jadi tidak ada yang bisa dilihat.
  · CHECK B (kontrak FE↔BE) hanya bisa bilang "FE memanggil path yang tak ada",
    tanpa tahu implementasinya SUDAH ADA namun tak terjangkau.
  · Linter Python default tidak menandai unreachable code.

SEVERITY
  HIGH  `return` diikuti statement yang memuat `return` lain ⇒ dua handler
        tergabung / dekorator hilang ⇒ fitur mati diam-diam. MEM-BLOK.
  INFO  `raise` di awal fungsi lalu badan lama ditinggal ⇒ pola DEPREKASI yang
        SENGAJA (mis. K5 Phase C: `raise HTTPException(410, ...)`). Bukan bug.

Usage: cd /app && python scripts/guardrails/verify_unreachable_code.py [--report-only]
"""
import argparse
import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from gr_common import Report, ROOT  # noqa: E402

BACKEND = ROOT / "backend"
SKIP_PARTS = {"__pycache__", "tests", "migrations", "_archive"}
TERMINATORS = (ast.Return, ast.Raise, ast.Continue, ast.Break)


def _scan_fn(fn, path: Path, out: list):
    """Cari statement setelah terminator DI LEVEL BODY fungsi (bukan dalam if/try)."""
    body = fn.body
    for i, stmt in enumerate(body):
        if not isinstance(stmt, TERMINATORS):
            continue
        rest = [s for s in body[i + 1:] if not isinstance(s, ast.Pass)]
        if not rest:
            continue
        has_return = any(isinstance(s, ast.Return) for s in rest)
        sev = "HIGH" if isinstance(stmt, ast.Return) and has_return else "INFO"
        out.append({
            "sev": sev,
            "file": str(path.relative_to(ROOT)),
            "func": fn.name,
            "func_line": fn.lineno,
            "terminator": type(stmt).__name__,
            "terminator_line": stmt.lineno,
            "from_line": rest[0].lineno,
            "to_line": max(getattr(s, "end_lineno", s.lineno) or s.lineno for s in rest),
            "n": len(rest),
            "has_return": has_return,
        })
        return  # satu temuan per fungsi cukup


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args()

    rep = Report(
        "INV-DEADCODE-01",
        "Handler tergabung / kode mati setelah return (dekorator hilang)",
        block_sev=() if args.report_only else ("HIGH",),
    )

    findings: list[dict] = []
    for py in sorted(BACKEND.rglob("*.py")):
        if any(p in SKIP_PARTS for p in py.parts):
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                rep.bump()
                _scan_fn(node, py, findings)

    for f in sorted(findings, key=lambda x: (x["sev"] != "HIGH", x["file"])):
        where = f"{f['file']}:{f['func_line']} {f['func']}()"
        if f["sev"] == "HIGH":
            rep.add("HIGH", "MERGED_HANDLER",
                    f"{f['terminator']} di baris {f['terminator_line']} membuat baris "
                    f"{f['from_line']}-{f['to_line']} ({f['n']} statement, memuat `return`) "
                    f"TAK TERJANGKAU — kemungkinan endpoint yang kehilangan dekorator",
                    where)
        else:
            rep.add("INFO", "DEPRECATED_BODY",
                    f"{f['terminator']} di baris {f['terminator_line']} → baris "
                    f"{f['from_line']}-{f['to_line']} tak terjangkau (pola deprekasi disengaja)",
                    where)

    n_high = sum(1 for f in findings if f["sev"] == "HIGH")
    if n_high == 0:
        print(f"    {rep.checked} fungsi diperiksa — tidak ada handler tergabung.")
    else:
        print(f"    {rep.checked} fungsi diperiksa — {n_high} handler tergabung DITEMUKAN.")
    return rep.finish()


if __name__ == "__main__":
    sys.exit(main())
