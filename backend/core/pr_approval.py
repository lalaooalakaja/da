"""core/pr_approval.py — MESIN PERSETUJUAN PEMBELIAN (SATU untuk semua jenis permintaan).

MENGAPA BERKAS INI ADA
----------------------
2026-08-07 — laporan owner: *"ada purchase request di aksesoris dan gudang, ini
harusnya tersambung ke procurement."* Benar, dan buktinya keras:

`acc_purchase_requests` (Request Pembelian Aksesoris) adalah alur PARALEL yang
menu-nya sudah dipindah ke Portal Pengadaan tetapi PERSETUJUANNYA tidak pernah
tersambung:

  · `PUT /api/acc/purchase-requests/{id}` hanya memakai `require_auth` ⇒
    **SIAPA PUN yang login bisa menyetujui**. Terbukti: akun `tim_packing`
    (staf packing gudang) membuat PR aksesoris Rp 50.000.000, submit, lalu
    **menyetujui PR-nya sendiri** — HTTP 200, tanpa satu pun pemeriksaan;
  · tidak pernah muncul di Kotak Persetujuan (`/api/procurement/inbox`) maupun
    lencana approval ⇒ approver yang berhak tidak pernah tahu ada pekerjaan;
  · satu tahap saja (tidak ada dept → keuangan → final), tidak mengikuti ambang
    nilai yang diatur owner, tidak ada jejak audit (`approved_by` hanya STRING
    nama, tanpa id aktor, tanpa waktu per tahap, tanpa penanda override).

Karena aturannya harus SAMA persis dengan Permintaan Pengadaan, mesinnya
dipindah ke sini supaya TIDAK ADA daftar peran / aturan tahap yang ditulis dua
kali (duplikasi daftar peran adalah akar bug 2026-08-06 dan 2026-08-07).

BENTUK DOKUMEN TIDAK DIIKAT
---------------------------
`eval_approval()` bekerja pada dokumen apa pun selama:
  · punya `requested_by` (id pembuat) dan `department` (opsional),
  · punya `approval_steps` (daftar langkah), dan
  · tahap aktifnya bisa ditentukan: dari `status` (Permintaan Pengadaan) ATAU
    dikirim eksplisit lewat argumen `stage` (Request Aksesoris memakai
    `current_approver_stage`).

Dipakai oleh: routes/dewi_procurement.py · routes/dewi_accessories_purchase.py ·
routes/approval_badge.py.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

STAGE_DEPT, STAGE_FINANCE, STAGE_FINAL = "dept", "finance", "final"

# Peran per tahap. WAJIB SALING LEPAS (disjoint) supaya aturan "satu orang tidak
# boleh menyetujui dua tahap" punya arti. `manager_keuangan` sengaja DIKELUARKAN
# dari tahap final — sebelumnya ia terdaftar di tahap keuangan DAN final, jadi
# orang yang baru menyetujui tahap keuangan bisa langsung menutup tahap final.
DEPT_APPROVER_ROLES = (
    "manager", "dept_head", "supervisor", "manager_produksi", "supervisor_produksi",
    "manager_hr", "manager_marketing", "manager_pengadaan", "spv_aksesoris",
    "spv_packing", "spv_cuting", "admin_gudang", "admin_pengadaan", "purchasing",
    # 2026-08-07 — divisi aksesoris ikut tahap departemen karena Request Pembelian
    # Aksesoris sekarang memakai rantai yang sama.
    "admin_aksesoris",
)
FINANCE_APPROVER_ROLES = (
    "finance", "finance_manager", "accountant",          # nama generik (jaga kompatibilitas)
    "accounting", "staff_keuangan", "manager_keuangan",  # peran NYATA di aplikasi ini
)
FINAL_APPROVER_ROLES = ("director", "cfo", "ceo", "owner")

STAGE_ROLES = {
    STAGE_DEPT: DEPT_APPROVER_ROLES,
    STAGE_FINANCE: FINANCE_APPROVER_ROLES,
    STAGE_FINAL: FINAL_APPROVER_ROLES,
}
# Izin dinamis yang setara tiap tahap (katalog: backend/data/permission_catalog.py).
# Sengaja tidak ada izin yang muncul di dua tahap.
STAGE_PERMS = {
    STAGE_DEPT: ("purchasing.approve", "proc.pr.approve"),
    STAGE_FINANCE: ("finance.approve",),
    STAGE_FINAL: ("proc.pr.final_approve",),
}
STAGE_LABELS = {
    STAGE_DEPT: "Persetujuan Departemen",
    STAGE_FINANCE: "Persetujuan Keuangan",
    STAGE_FINAL: "Persetujuan Final (Direksi)",
}
STAGE_ROLE_LABELS = {
    STAGE_DEPT: "manager/supervisor departemen",
    STAGE_FINANCE: "keuangan (accounting / staff keuangan / manager keuangan)",
    STAGE_FINAL: "direksi (director / CFO / CEO / owner)",
}
# Status Permintaan Pengadaan → tahap yang sedang menunggu keputusan.
STATUS_TO_STAGE = {
    "submitted": STAGE_DEPT,
    "dept_approved": STAGE_FINANCE,
    "finance_approved": STAGE_FINAL,
}
STAGE_TO_STATUS = {v: k for k, v in STATUS_TO_STAGE.items()}
PENDING_STATUSES = tuple(STATUS_TO_STAGE)
SUPER_APPROVER_ROLES = ("superadmin", "admin", "owner")


# ── Ambang nilai & rantai ────────────────────────────────────────────────────
async def chain_config(db) -> dict:
    """Ambang nilai PR yang berlaku (diatur owner di Ringkasan Bisnis)."""
    from services.management_alerts import PR_CHAIN_DEFAULTS, get_alert_config
    try:
        cfg = await get_alert_config(db)
        return {k: int(cfg.get(k, PR_CHAIN_DEFAULTS[k])) for k in PR_CHAIN_DEFAULTS}
    except Exception as e:  # noqa: BLE001 — ambang rusak tidak boleh mematikan approval
        logger.warning("[pr-approval] gagal baca ambang rantai persetujuan: %s", e)
        return dict(PR_CHAIN_DEFAULTS)


def compute_chain(total, cfg: dict) -> list:
    """Tahap yang WAJIB dilalui untuk permintaan bernilai `total`."""
    try:
        t = float(total or 0)
    except (TypeError, ValueError):
        t = 0.0
    if t <= float(cfg.get("pr_1_stage_max", 1_000_000)):
        return [STAGE_DEPT]
    if t <= float(cfg.get("pr_2_stage_max", 25_000_000)):
        return [STAGE_DEPT, STAGE_FINANCE]
    return [STAGE_DEPT, STAGE_FINANCE, STAGE_FINAL]


def doc_chain(doc: dict, cfg: dict) -> list:
    """Rantai tahap dokumen ini. Dipakai apa adanya bila sudah dibekukan saat
    submit; dokumen lama (sebelum fitur ini) dihitung ulang dari nilainya."""
    stored = doc.get("approval_chain")
    if isinstance(stored, list) and stored:
        keep = [s for s in stored if s in STAGE_ROLES]
        if keep:
            return keep
    return compute_chain(doc.get("total_estimated"), cfg)


def next_stage_after(chain: list, stage: str):
    try:
        return chain[chain.index(stage) + 1]
    except (ValueError, IndexError):
        return None


def status_after_stage(chain: list, stage: str) -> str:
    nxt = next_stage_after(chain, stage)
    return STAGE_TO_STATUS.get(nxt, "approved") if nxt else "approved"


def approved_actor_ids(doc: dict) -> set:
    return {s.get("actor_id") for s in (doc.get("approval_steps") or [])
            if s.get("action") == "approved" and s.get("actor_id")}


def stage_role_ok(user: dict, stage: str) -> bool:
    """Berhak atas tahap ini SEBAGAI PERAN TAHAP (bukan sebagai admin).

    Mengikuti model "fallback aman" routes/shared.py: izin dinamis menang;
    selama owner belum mengatur izin role ini, daftar peran bawaan tahap
    tersebut yang dipakai (supaya fitur lama tidak mati mendadak).

    PENTING: admin/superadmin memegang izin `"*"`. Bila `"*"` ikut dihitung di
    sini, SETIAP tindakan admin akan tampak sah dan TIDAK PERNAH tercatat
    sebagai override — padahal owner minta override tercatat. Karena itu peran
    super dinilai HANYA dari keanggotaan daftar peran tahap (mis. `owner` memang
    approver tahap final, jadi owner di tahap final = sah, bukan override).
    """
    role = (user.get("role") or "").lower()
    roles = STAGE_ROLES.get(stage, ())
    if role in SUPER_APPROVER_ROLES:
        return role in roles
    from routes.shared import perms_configured, user_permissions
    perms = user_permissions(user)
    if "*" in perms or (perms & set(STAGE_PERMS.get(stage, ()))):
        return True
    if perms_configured(user):
        return False
    return role in roles


async def with_department(db, user: dict) -> dict:
    """Lengkapi `user` dengan `department` dari master pengguna.

    `auth.create_token` baru memasukkan `department` sejak 2026-08-07, jadi token
    yang MASIH BERLAKU (24 jam) belum memuatnya. Tanpa tambalan ini batas
    departemen pada tahap pertama diam-diam tidak berjalan.
    """
    if user.get("department"):
        return user
    try:
        u = await db.users.find_one({"id": user.get("id")}, {"_id": 0, "department": 1})
        if u and u.get("department"):
            return {**user, "department": u["department"]}
    except Exception as e:  # noqa: BLE001
        logger.warning("[pr-approval] gagal resolve departemen user: %s", e)
    return user


def eval_approval(doc: dict, user: dict, chain: list, *, stage=None) -> dict:
    """Hak + konteks persetujuan untuk SATU dokumen × SATU user.

    SSOT tunggal yang dipakai oleh: kotak persetujuan, daftar & detail dokumen
    (flag tombol UI), gerbang approve/reject, dan lencana approval di TopBar.

    stage : tahap aktif. Bila None, diturunkan dari `doc["status"]`
            (Permintaan Pengadaan). Request Aksesoris mengirimnya eksplisit
            dari `current_approver_stage`.
    """
    role = (user.get("role") or "").lower()
    uid = user.get("id")
    is_super = role in SUPER_APPROVER_ROLES
    if stage is None:
        stage = STATUS_TO_STAGE.get(doc.get("status"))

    # Langkah lama menyimpan STATUS sebelum approve di field `step` → petakan
    # kembali ke tahap supaya riwayat dokumen lama tetap terbaca stepper UI.
    done_by = {}
    for s in (doc.get("approval_steps") or []):
        if s.get("action") != "approved":
            continue
        st = s.get("stage") or STATUS_TO_STAGE.get(s.get("step"))
        if st:
            done_by[st] = s

    chain_view = []
    for idx, st in enumerate(chain):
        d = done_by.get(st) or {}
        chain_view.append({
            "stage": st,
            "order": idx + 1,
            "label": STAGE_LABELS.get(st, st),
            "role_hint": STAGE_ROLE_LABELS.get(st, ""),
            "done": bool(d),
            "current": st == stage,
            "actor_name": d.get("actor_name") or "",
            "timestamp": d.get("timestamp") or "",
            "override": bool(d.get("override")),
        })

    out = {
        "approval_chain": list(chain),
        "chain": chain_view,
        "total_stages": len(chain),
        "stage": stage,
        "stage_label": STAGE_LABELS.get(stage, ""),
        "stage_role_hint": STAGE_ROLE_LABELS.get(stage, ""),
        "stage_order": (chain.index(stage) + 1) if stage in chain else None,
        "can_approve": False,
        "can_reject": False,
        "is_override": False,
        "override_reasons": [],
        "override_note": "",
        "blocked_reason": "",
    }
    nxt = next_stage_after(chain, stage) if stage else None
    out["next_stage"] = nxt
    out["next_approver_label"] = (STAGE_ROLE_LABELS.get(nxt, "")
                                  if nxt else "Selesai — permintaan disetujui penuh")

    if not stage:
        out["blocked_reason"] = "Tidak ada persetujuan yang menunggu pada permintaan ini."
        return out
    if stage not in chain:
        out["blocked_reason"] = (
            f"Tahap '{STAGE_LABELS.get(stage, stage)}' tidak ada dalam rantai persetujuan "
            "permintaan ini. Hubungi admin.")
        if not is_super:
            return out

    violations, reasons = [], []
    if not stage_role_ok(user, stage):
        violations.append("stage_role")
        reasons.append(
            f"Tahap saat ini {STAGE_LABELS.get(stage, stage)} — hanya "
            f"{STAGE_ROLE_LABELS.get(stage, 'peran tahap ini')} yang berhak memutuskan.")
    if uid and doc.get("requested_by") == uid:
        violations.append("self_approval")
        reasons.append("Anda pembuat permintaan ini — pembuat tidak boleh "
                       "menyetujui permintaannya sendiri.")
    if uid and uid in approved_actor_ids(doc):
        violations.append("double_stage")
        reasons.append("Anda sudah menyetujui permintaan ini di tahap sebelumnya — "
                       "satu orang tidak boleh menyetujui dua tahap.")
    if stage == STAGE_DEPT:
        udept = (user.get("department") or "").strip()
        pdept = (doc.get("department") or "").strip()
        if udept and pdept and udept != pdept:
            violations.append("department")
            reasons.append(f"Permintaan ini milik departemen {pdept}, "
                           f"sedangkan Anda di departemen {udept}.")

    if violations and is_super:
        out["can_approve"] = out["can_reject"] = True
        out["is_override"] = True
        out["override_reasons"] = violations
        out["override_note"] = ("Anda menembus aturan pemisahan wewenang sebagai "
                                "admin/owner — tindakan ini dicatat di riwayat.")
    elif violations:
        out["blocked_reason"] = " ".join(reasons)
    else:
        out["can_approve"] = out["can_reject"] = True
    return out


# ── Notifikasi ──────────────────────────────────────────────────────────────
async def notify_stage_approvers(db, doc: dict, stage: str, chain: list, *,
                                 module_id: str = "proc-requests",
                                 number: str = "", title: str = "",
                                 kind_label: str = "Permintaan Pengadaan"):
    """Beri tahu approver tahap `stage` lewat BEL notifikasi (SSOT `notifications`).

    Best-effort: kegagalan notifikasi tidak boleh membatalkan persetujuan.
    """
    if not stage:
        return
    try:
        from utils.notif_unified import notif_insert
        roles = list(STAGE_ROLES.get(stage, ()))
        if not roles:
            return
        rows = await db.users.find(
            {"role": {"$in": roles}, "status": {"$ne": "inactive"}},
            {"_id": 0, "id": 1, "department": 1},
        ).to_list(500)
        ids = [r["id"] for r in rows if r.get("id")]
        # Tahap departemen: utamakan approver di departemen dokumen (bila ada yang
        # cocok), supaya notifikasi tidak menyiram semua manager di perusahaan.
        pdept = (doc.get("department") or "").strip()
        if stage == STAGE_DEPT and pdept:
            same = [r["id"] for r in rows
                    if r.get("id") and (r.get("department") or "").strip() == pdept]
            if same:
                ids = same
        idx = chain.index(stage) + 1 if stage in chain else 1
        rp = f"Rp {float(doc.get('total_estimated') or 0):,.0f}".replace(",", ".")
        body = (f"{number} — {title}\n"
                f"Nilai: {rp}\n"
                f"Menunggu {STAGE_LABELS.get(stage, stage)} "
                f"(tahap {idx} dari {len(chain)})")
        await notif_insert(
            db, type="rahaza", subtype="procurement_approval", severity="warning",
            title=f"{kind_label} menunggu persetujuan Anda",
            body=body,
            target_user_ids=ids or None,
            # Bila belum ada satu pun pengguna berperan itu, jangan buang
            # notifikasinya — alamatkan ke perannya supaya muncul begitu ada.
            target_roles=None if ids else roles,
            source_type="procurement_request", source_id=doc.get("id"),
            source_ref=number,
            meta={"link_module": module_id, "pr_id": doc.get("id"),
                  "request_number": number, "stage": stage,
                  "dedup_key": f"pr-approval:{doc.get('id')}:{stage}"},
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("[pr-approval] gagal notifikasi approver tahap %s: %s", stage, e)


async def notify_requester(db, doc: dict, *, title: str, body: str,
                           severity: str = "info", module_id: str = "proc-requests",
                           number: str = ""):
    """Kabari pembuat permintaan di bel notifikasi."""
    uid = doc.get("requested_by")
    if not uid:
        return
    try:
        from utils.notif_unified import notif_insert
        await notif_insert(
            db, type="rahaza", subtype="procurement_request_status", severity=severity,
            title=title, body=body, user_id=uid,
            source_type="procurement_request", source_id=doc.get("id"),
            source_ref=number,
            meta={"link_module": module_id, "pr_id": doc.get("id"),
                  "request_number": number},
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("[pr-approval] gagal kabari pembuat permintaan: %s", e)


# ── KOTAK PERSETUJUAN GABUNGAN ──────────────────────────────────────────────
# Satu daftar untuk SEMUA permintaan pembelian, apa pun asalnya. Ini yang
# menjawab laporan owner: pekerjaan pembelian tidak boleh tersebar di dua inbox.
ACC_STATUS_DISPLAY = {
    # Status Request Aksesoris (kapital) → kosakata status Permintaan Pengadaan
    # supaya lencana & warna di UI konsisten tanpa cabang khusus di frontend.
    "Draft": "draft",
    "Rejected": "rejected",
    "Approved": "approved",
    "Ordered": "in_procurement",
    "Received": "completed",
}


def acc_display_status(doc: dict) -> str:
    st = doc.get("status") or "Draft"
    if st == "Submitted":
        stage = doc.get("current_approver_stage") or STAGE_DEPT
        return STAGE_TO_STATUS.get(stage, "submitted")
    return ACC_STATUS_DISPLAY.get(st, "draft")


def normalize_acc_pr(doc: dict) -> dict:
    """Bentuk Request Pembelian Aksesoris → bentuk yang dipahami UI pengadaan."""
    prio = (doc.get("priority") or "Normal").strip().lower()
    return {
        "id": doc.get("id"),
        "kind": "acc_pr",
        "kind_label": "Aksesoris",
        "api_base": "/api/acc/purchase-requests",
        "module_id": "proc-accessory-pr",
        "request_number": doc.get("pr_number") or "",
        "title": doc.get("purpose") or "Request Pembelian Aksesoris",
        "description": doc.get("notes") or "",
        "justification": doc.get("purpose") or "",
        "department": doc.get("department") or "",
        "priority": {"urgent": "urgent", "normal": "medium", "low": "low"}.get(prio, "medium"),
        "request_type": "consumable",
        "status": acc_display_status(doc),
        "raw_status": doc.get("status"),
        "total_estimated": float(doc.get("total_estimated") or 0),
        "items": doc.get("items") or [],
        "requested_by": doc.get("requested_by"),
        "requested_by_name": doc.get("requested_by_name") or doc.get("created_by") or "",
        "created_at": doc.get("created_at"),
        "submitted_at": doc.get("submitted_at") or None,
        "rejection_reason": doc.get("finance_notes") if doc.get("status") == "Rejected" else None,
        "supplier": doc.get("supplier") or "",
        "approval_steps": doc.get("approval_steps") or [],
    }


async def pending_for_user(db, user: dict, *, include_acc: bool = True) -> list:
    """SEMUA permintaan pembelian yang menunggu KEPUTUSAN user ini.

    Dipakai bersama oleh `/api/procurement/inbox` dan lencana
    `/api/approval-inbox/badge` supaya angka lencana = isi kotak persetujuan.
    """
    from routes.dewi_procurement import _ser
    u = await with_department(db, user)
    cfg = await chain_config(db)
    out = []

    rows = await db.dewi_procurement_requests.find(
        {"status": {"$in": list(PENDING_STATUSES)}}, {"_id": 0}
    ).sort("submitted_at", 1).to_list(500)
    for d in rows:
        ev = eval_approval(d, u, doc_chain(d, cfg))
        if not ev["can_approve"]:
            continue
        item = _ser(d)
        item.update(ev)
        item.update({"kind": "pr", "kind_label": "Pengadaan",
                     "api_base": "/api/procurement/requests",
                     "module_id": "proc-requests"})
        out.append(item)

    if include_acc:
        accs = await db.acc_purchase_requests.find(
            {"status": "Submitted"}, {"_id": 0}
        ).sort("submitted_at", 1).to_list(500)
        for d in accs:
            chain = doc_chain(d, cfg)
            ev = eval_approval(d, u, chain, stage=d.get("current_approver_stage") or STAGE_DEPT)
            if not ev["can_approve"]:
                continue
            item = _ser(normalize_acc_pr(d))
            item.update(ev)
            out.append(item)

    out.sort(key=lambda x: str(x.get("submitted_at") or x.get("created_at") or ""))
    return out
