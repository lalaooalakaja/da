"""
P3 TD-010 Part A — Shared Counter Helper
========================================
Single Source Of Truth (SSOT) for atomic sequence counters across the ERP.

Before consolidation:
  - `counters`         (generic; rahaza_lkp, rahaza_ap_from_gr, warehouse, rahaza_po)
  - `dewi_counters`    (dewi_maklon_billing, dewi_maklon_pos, dewi_cmt_progress)
  - `rahaza_counters`  (rahaza_sprint22 — `{name: ..., seq: ...}` schema variant)

After consolidation:
  - `counters` (SSOT)  with `{_id, seq, namespace}` shape
    - `_id`: counter key (e.g., "lkp_2026", "mkl_BUY01_2026", "mi_number")
    - `namespace`: discriminator (`generic` | `dewi` | `rahaza` | …)
    - `seq`: atomic sequence integer

Pattern:
    from utils.counters import next_counter, next_counter_batch

    n = await next_counter(db, "lkp_2026", namespace="rahaza")
    # → returns increment-by-1, upsert behavior preserved

    start_seq = await next_counter_batch(db, "mi_number", count=5, namespace="rahaza")
    # → returns the FIRST seq of the reserved range (atomic batch)

Migration script: /app/backend/migrations/migrate_counters_unification.py
"""
from __future__ import annotations
import re
import time
from datetime import datetime, timezone
from pymongo import ReturnDocument
from typing import Optional


async def next_counter(db, key: str, *, namespace: str = 'generic') -> int:
    """Atomically increment counter for `key` by 1 and return new seq.

    Uses upsert + ReturnDocument.AFTER. `namespace` is recorded on first
    insert for traceability but does NOT participate in uniqueness — `_id`
    (the key) is globally unique across the unified `counters` collection.
    """
    doc = await db.counters.find_one_and_update(
        {'_id': key},
        {
            '$inc': {'seq': 1},
            '$setOnInsert': {'namespace': namespace},
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return int(doc['seq'])


async def next_counter_batch(
    db, key: str, *, count: int, namespace: str = 'generic',
) -> int:
    """Atomically reserve `count` consecutive seq values; return FIRST in range.

    Example: if current seq=10 and count=3, returns 11 (range 11..13 reserved).
    Useful for batch creation (e.g., multiple work orders in one mutation).
    """
    if count < 1:
        raise ValueError('count must be >= 1')
    doc = await db.counters.find_one_and_update(
        {'_id': key},
        {
            '$inc': {'seq': count},
            '$setOnInsert': {'namespace': namespace},
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return int(doc['seq']) - count + 1


async def peek_counter(db, key: str) -> Optional[int]:
    """Read current seq without incrementing (returns None if counter absent)."""
    doc = await db.counters.find_one({'_id': key}, {'seq': 1})
    return int(doc['seq']) if doc else None


async def gen_prefixed_number(db, collection: str, field: str, prefix: str,
                              width: int = 4, ctx: Optional[dict] = None,
                              config_key: Optional[str] = None) -> str:
    """Race-safe prefixed sequential number (RC-5 mitigation).

    Replaces the unsafe `count_documents(...) + 1` numbering anti-pattern that races
    under concurrency (→ duplicate number / E11000 500) and reuses numbers after
    void/delete. Uses the atomic `counters` SSOT (`$inc`) with a LAZY max-initialisation
    so it does not collide with historical count-based numbers already in the collection.

    key = f"autonum:{collection}:{field}:{prefix}". On first use it seeds the counter to
    the max trailing integer of existing docs under `prefix`, then increments atomically.

    Example:  await gen_prefixed_number(db, "rahaza_journal_entries", "je_number",
                                        f"JE-{d:%Y%m%d}-", 4)  ->  "JE-20260705-0007"

    FORMAT TERKONFIGURASI (2026-07): bila owner menyimpan format untuk
    "<collection>.<field>" di `doc_number_configs`, format itulah yang dipakai —
    `prefix`/`width` bawaan kode menjadi cadangan. Tidak ada generator kedua;
    ini tetap satu-satunya pintu penomoran race-safe.

    `config_key` (2026-08-05, tahap 2): dipakai bila SATU koleksi+field menampung
    LEBIH DARI SATU jenis dokumen dengan awalan berbeda — mis. `rahaza_ar_invoices.
    invoice_number` dipakai invoice AR Finance (AR-…) DAN invoice maklon otomatis
    (INV-MKL-…). Tanpa ini, satu format akan menimpa keduanya.
    """
    import re
    prefix, width = await resolve_format(db, collection, field, prefix, width, ctx,
                                         config_key=config_key)
    key = f"autonum:{collection}:{field}:{prefix}"
    if await db.counters.find_one({'_id': key}, {'_id': 1}) is None:
        start = 0
        latest = await db[collection].find(
            {field: {'$regex': f'^{re.escape(prefix)}'}}, {field: 1, '_id': 0}
        ).sort(field, -1).limit(1).to_list(1)
        if latest:
            m = re.search(r'(\d+)\s*$', str(latest[0].get(field, '')))
            if m:
                start = int(m.group(1))
        # atomic lazy-init (only the first writer wins; concurrent inits are idempotent)
        await db.counters.update_one(
            {'_id': key},
            {'$setOnInsert': {'seq': start, 'namespace': 'autonum'}},
            upsert=True,
        )
    seq = await next_counter(db, key, namespace='autonum')
    return f"{prefix}{seq:0{width}d}"


# ─── Format nomor dokumen yang bisa diatur owner ──────────────────────────────
# Layar: Portal Administrasi Sistem → Penomoran Dokumen.
CONFIG_COLL = 'doc_number_configs'
_SEQ_RE = re.compile(r'\{SEQ(?::(\d+))?\}')
_TOKEN_RE = re.compile(r'\{([A-Z_]+)(?::\d+)?\}')
_CFG_CACHE: dict[str, tuple[float, Optional[dict]]] = {}
_CFG_TTL = 10.0  # detik — perubahan format terasa hampir seketika tanpa membanjiri DB


def render_format(fmt: str, *, now: Optional[datetime] = None,
                  ctx: Optional[dict] = None, require_seq: bool = True) -> tuple[str, int]:
    """Ubah format owner menjadi (prefix, lebar_digit).

    Token: {YYYY} {YY} {MM} {DD} {SEQ:n} + token konteks per jenis dokumen.
    {SEQ:n} WAJIB berada di akhir; teks setelahnya tidak didukung karena
    generator menempelkan nomor urut di ujung.

    `require_seq=False` dipakai untuk KODE MASTER (mis. SKU potongan) yang
    keunikannya berasal dari kombinasi token, bukan dari nomor urut — lebar
    digit yang dikembalikan 0.

    Raises ValueError bila format tidak sah (dipakai juga oleh validasi API).
    """
    now = now or datetime.now(timezone.utc)
    ctx = {str(k).upper(): str(v) for k, v in (ctx or {}).items() if v not in (None, "")}

    m = _SEQ_RE.search(fmt or "")
    if not m and require_seq:
        raise ValueError("Format wajib memuat {SEQ} atau {SEQ:n}.")
    if m:
        if fmt[m.end():].strip():
            raise ValueError("{SEQ} harus berada di paling akhir format.")
        width = int(m.group(1) or 4)
        if not 1 <= width <= 10:
            raise ValueError("Jumlah digit {SEQ:n} harus antara 1 dan 10.")
        head = fmt[:m.start()]
    else:
        width, head = 0, fmt or ""

    base = {"YYYY": f"{now:%Y}", "YY": f"{now:%y}", "MM": f"{now:%m}", "DD": f"{now:%d}"}
    unknown = [t for t in _TOKEN_RE.findall(head) if t not in base and t not in ctx]
    if unknown:
        raise ValueError("Token tidak dikenal: " + ", ".join("{" + u + "}" for u in unknown))
    for token, value in {**base, **ctx}.items():
        head = head.replace("{" + token + "}", value)
    if not head.strip():
        raise ValueError("Format tidak boleh kosong.")
    return head, width


def validate_format(fmt: str, tokens: Optional[list] = None, *, require_seq: bool = True) -> str:
    """Validasi format & kembalikan contoh nomor (untuk pratinjau di layar admin)."""
    sample_ctx = {t: t[:3].upper() for t in (tokens or [])}
    prefix, width = render_format(fmt, ctx=sample_ctx, require_seq=require_seq)
    return f"{prefix}{1:0{width}d}" if width else prefix


async def resolve_master_code(db, key: str, ctx: dict, default: str) -> str:
    """Kode master (SKU) yang formatnya bisa diatur owner — tanpa nomor urut.

    Bila format belum diatur / tidak sah, `default` bawaan kode dipakai.
    """
    try:
        cfg = await db[CONFIG_COLL].find_one({"key": key, "active": True}, {"_id": 0, "format": 1})
        if cfg and cfg.get("format"):
            code, _ = render_format(cfg["format"], ctx=ctx, require_seq=False)
            return code
    except (ValueError, Exception):
        pass
    return default


async def resolve_format(db, collection: str, field: str, prefix: str,
                         width: int, ctx: Optional[dict] = None,
                         config_key: Optional[str] = None) -> tuple[str, int]:
    """Pakai format owner bila ada & sah; kalau tidak, pakai bawaan kode.

    Sengaja TIDAK pernah melempar error: format rusak = kembali ke perilaku lama,
    supaya salah ketik di layar admin tidak pernah memblokir transaksi.
    """
    key = config_key or f"{collection}.{field}"
    cached = _CFG_CACHE.get(key)
    nowts = time.time()
    if cached and nowts - cached[0] < _CFG_TTL:
        cfg = cached[1]
    else:
        try:
            cfg = await db[CONFIG_COLL].find_one({"key": key, "active": True}, {"_id": 0, "format": 1})
        except Exception:
            cfg = None
        _CFG_CACHE[key] = (nowts, cfg)
    if not cfg or not cfg.get("format"):
        return prefix, width
    try:
        return render_format(cfg["format"], ctx=ctx)
    except ValueError:
        return prefix, width


def invalidate_format_cache(key: Optional[str] = None) -> None:
    """Dipanggil layar admin setelah menyimpan supaya perubahan langsung berlaku."""
    if key:
        _CFG_CACHE.pop(key, None)
    else:
        _CFG_CACHE.clear()
