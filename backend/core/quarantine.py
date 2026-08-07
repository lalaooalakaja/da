"""core.quarantine — FASE 6 (INV-8): KARANTINA QC sebagai SSOT barang reject.

Masalah yang diselesaikan (BUG-INV-8):
  * GR (`warehouse.py update_receiving`) hanya memasukkan `net_qty = received − rejected`
    ke stok. Qty **reject hilang tanpa jejak fisik** → tidak bisa ditindaklanjuti
    (retur supplier / rework / scrap) dan tidak terlihat di laporan mana pun.
  * QC pasca-terima tidak bisa mengoreksi stok → risiko over-count.

Desain:
  * **Lokasi karantina kanonik** — utamakan zona `wh_*` peran 'karantina'
    (ZN-QRT/ZN-KARANTINA/ZN-QC), fallback + auto-provision `rahaza_locations`
    kode `ZNA-KARANTINA`. SENGAJA **di luar** `location_resolver.list_storage_locations`
    supaya tidak muncul di dropdown penerimaan/transfer normal.
  * **Blokir ketersediaan** — stok karantina ditulis via `stock_service.add` lalu
    `stock_service.reserve` sejumlah qty ⇒ `available_quantity = 0`. Fisik tercatat &
    auditable (ledger `rahaza_stock_ledger`), tapi TIDAK bisa dipakai produksi/BOM/jual.
  * **Jejak per-kejadian** — koleksi `wh_quarantine_items` (satu dok per kejadian
    karantina, punya `remaining_qty` + riwayat `dispositions`).
  * **Nilai (valued)** — `valued=False` bila barang belum pernah masuk nilai persediaan
    (reject saat GR: AP invoice pakai net qty ⇒ belum di-invoice/di-kapitalisasi);
    `valued=True` bila barang sudah masuk stok lalu dipindah ke karantina (re-inspeksi
    pasca-terima). Penentu apakah disposisi perlu jurnal keuangan.

Modul ini TIDAK meng-import `routes.*` (hindari circular import). Posting jurnal
dilakukan pemanggil (`routes/wms_quarantine.py`).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from core import stock_service
from core.stock_schema import read_qty
from utils.reject_reasons import normalize_reject_reasons, summarize_by_reason

QUARANTINE_COLL = "wh_quarantine_items"
QUARANTINE_CODE = "ZNA-KARANTINA"
QUARANTINE_ROLE = "karantina"

# Aksi disposisi yang sah
ACTION_RELEASE = "release"
ACTION_RETURN = "return_supplier"
ACTION_SCRAP = "scrap"
VALID_ACTIONS = (ACTION_RELEASE, ACTION_RETURN, ACTION_SCRAP)


def _now():
    return datetime.now(timezone.utc)


def _uid():
    return str(uuid.uuid4())


def _r(v) -> float:
    return round(float(v or 0), 4)


# ─────────────────────────────────────────────────────────────────────────────
# LOKASI KARANTINA
# ─────────────────────────────────────────────────────────────────────────────
async def get_quarantine_location_id(db) -> str:
    """Resolve (dan auto-provision) lokasi karantina. Selalu balik id yang valid."""
    # 1) zona kanonik wh_* peran 'karantina'
    try:
        from core import location_resolver
        zid = await location_resolver.canonical_zone_id_for_role(db, QUARANTINE_ROLE)
        if zid:
            return zid
    except Exception:
        pass
    # 2) legacy rahaza_locations (auto-create bila belum ada)
    loc = await db.rahaza_locations.find_one({"code": QUARANTINE_CODE}, {"_id": 0, "id": 1})
    if loc:
        return loc["id"]
    new_id = _uid()
    await db.rahaza_locations.insert_one({
        "id": new_id,
        "code": QUARANTINE_CODE,
        "name": "Area Karantina QC",
        "description": "Barang reject QC menunggu keputusan (retur supplier / rework / scrap). "
                       "Stok di sini DIBLOKIR (tidak tersedia untuk produksi/penjualan).",
        "type": "warehouse",
        "role": QUARANTINE_ROLE,
        "blocked": True,
        "active": True,
        "created_at": _now(),
    })
    return new_id


async def get_quarantine_location_info(db) -> dict:
    """Info lokasi karantina utk UI: {id, code, name}."""
    qid = await get_quarantine_location_id(db)
    code, name = QUARANTINE_CODE, ""
    try:
        from core import location_resolver
        disp = (await location_resolver.build_display_map(db, [qid])).get(qid) or {}
        # build_display_map balik {id: {code, name, source}} — ambil string-nya
        name = disp.get("name") or ""
        code = disp.get("code") or code
    except Exception:
        pass
    if not name:
        loc = await db.rahaza_locations.find_one({"id": qid}, {"_id": 0, "name": 1, "code": 1}) or {}
        name = loc.get("name") or "Area Karantina QC"
        code = loc.get("code") or code
    return {"id": qid, "code": code, "name": name}


# ─────────────────────────────────────────────────────────────────────────────
# MASUK KARANTINA
# ─────────────────────────────────────────────────────────────────────────────
async def quarantine_in(db, *, material_id: str, qty: float, unit: str = "pcs",
                        source: dict | None = None, reject_reasons: list | None = None,
                        valued: bool = False, unit_cost: float | None = None,
                        notes: str = "", actor: dict | None = None,
                        from_location_id: str | None = None) -> dict:
    """Masukkan `qty` material ke KARANTINA (stok fisik tercatat, available = 0).

    from_location_id = None  → barang BELUM pernah masuk stok (reject saat GR) ⇒ `add`.
    from_location_id = <loc> → barang SUDAH di stok ⇒ `move` (issue asal → add karantina).
    """
    qty = _r(qty)
    if qty <= 0:
        raise ValueError("qty karantina harus > 0")
    qloc = await get_quarantine_location_id(db)
    if from_location_id and from_location_id == qloc:
        raise ValueError("lokasi asal tidak boleh sama dengan lokasi karantina")

    mat = await db.rahaza_materials.find_one(
        {"id": material_id}, {"_id": 0, "code": 1, "name": 1, "unit": 1, "unit_cost": 1, "hpp": 1, "type": 1}) or {}
    if unit_cost is None:
        unit_cost = float(mat.get("unit_cost") or mat.get("hpp") or 0)

    ref = {"source": "quarantine_in", "reason": "qc_reject", **(source or {})}
    meta = {
        "unit": unit or mat.get("unit") or "pcs",
        "material_code": mat.get("code"),
        "material_name": mat.get("name"),
        "quarantine": True,
    }

    if from_location_id:
        await stock_service.move(material_id, from_location_id, qloc, qty,
                                 meta=meta, ref=ref, actor=actor, db=db)
    else:
        await stock_service.add(material_id, qloc, qty, meta=meta, ref=ref, actor=actor, db=db)

    # Blokir ketersediaan: reserve sebesar qty yang baru masuk
    try:
        await stock_service.reserve(material_id, qloc, qty,
                                   ref={**ref, "reason": "quarantine_block"}, actor=actor, db=db)
    except Exception:
        # tidak fatal: baris tetap bertanda quarantine + tidak muncul di dropdown storage
        pass
    await db[stock_service.STOCK].update_one(
        {"material_id": material_id, "location_id": qloc},
        {"$set": {"quarantine": True, "blocked": True}})

    doc = {
        "id": _uid(),
        "material_id": material_id,
        "material_code": mat.get("code", ""),
        "material_name": mat.get("name", ""),
        "material_type": mat.get("type", ""),
        "unit": unit or mat.get("unit") or "pcs",
        "unit_cost": _r(unit_cost),
        "qty": qty,
        "remaining_qty": qty,
        "location_id": qloc,
        "valued": bool(valued),
        "status": "open",
        "source": source or {},
        # SSOT bentuk alasan reject — dinormalisasi DI SINI (gerbang tulis terakhir)
        # supaya tak ada penulis yang bisa menyimpan bentuk liar (mis. list of string
        # dari `routes/rahaza_grn_qc.py`) yang dulu merobohkan `summary()` dengan 500.
        "reject_reasons": normalize_reject_reasons(reject_reasons, default_qty=qty),
        "notes": notes,
        "dispositions": [],
        "created_at": _now(),
        "created_by": (actor or {}).get("name", ""),
        "created_by_id": (actor or {}).get("id", ""),
        "updated_at": _now(),
    }
    await db[QUARANTINE_COLL].insert_one(doc)
    doc.pop("_id", None)
    return doc


# ─────────────────────────────────────────────────────────────────────────────
# KELUAR KARANTINA (dipakai router; JE ditangani pemanggil)
# ─────────────────────────────────────────────────────────────────────────────
async def quarantine_out(db, *, item: dict, action: str, qty: float,
                         to_location_id: str | None = None,
                         actor: dict | None = None, notes: str = "") -> dict:
    """Terapkan disposisi pada stok karantina. Return dict info mutasi.

    release          → move karantina → `to_location_id` (stok kembali tersedia)
    return_supplier  → issue keluar dari karantina (barang keluar gudang)
    scrap            → issue keluar dari karantina (dibuang)
    """
    if action not in VALID_ACTIONS:
        raise ValueError(f"action tidak dikenal: {action}")
    qty = _r(qty)
    if qty <= 0:
        raise ValueError("qty disposisi harus > 0")
    remaining = _r(item.get("remaining_qty") or 0)
    if qty - remaining > 1e-6:
        raise ValueError(f"qty {qty} melebihi sisa karantina {remaining}")

    qloc = item.get("location_id") or await get_quarantine_location_id(db)
    material_id = item["material_id"]
    ref = {"source": f"quarantine_{action}", "quarantine_item_id": item["id"],
           "quarantine_no": item.get("id"), "notes": notes}

    # lepas blokir (reserved) sebesar qty agar mutasi fisik boleh jalan
    try:
        await stock_service.release(material_id, qloc, qty,
                                   ref={**ref, "reason": "quarantine_unblock"}, actor=actor, db=db)
    except Exception:
        pass

    if action == ACTION_RELEASE:
        if not to_location_id:
            raise ValueError("to_location_id wajib untuk release")
        if to_location_id == qloc:
            raise ValueError("lokasi tujuan release tidak boleh lokasi karantina")
        await stock_service.move(material_id, qloc, to_location_id, qty,
                                 meta={"quarantine": False}, ref=ref, actor=actor, db=db)
        # baris tujuan bukan karantina
        await db[stock_service.STOCK].update_one(
            {"material_id": material_id, "location_id": to_location_id},
            {"$set": {"quarantine": False, "blocked": False}})
    else:
        await stock_service.issue(material_id, qloc, qty, ref=ref, actor=actor, db=db)

    new_remaining = _r(remaining - qty)
    disp = {
        "id": _uid(),
        "action": action,
        "qty": qty,
        "to_location_id": to_location_id if action == ACTION_RELEASE else None,
        "notes": notes,
        "at": _now(),
        "by": (actor or {}).get("name", ""),
        "by_id": (actor or {}).get("id", ""),
    }
    await db[QUARANTINE_COLL].update_one(
        {"id": item["id"]},
        {"$set": {"remaining_qty": new_remaining,
                  "status": "open" if new_remaining > 1e-6 else "closed",
                  "updated_at": _now()},
         "$push": {"dispositions": disp}})
    return {"disposition": disp, "remaining_qty": new_remaining,
            "closed": new_remaining <= 1e-6, "location_id": qloc}


# ─────────────────────────────────────────────────────────────────────────────
# BACA
# ─────────────────────────────────────────────────────────────────────────────
async def list_items(db, *, status: str | None = "open", material_id: str | None = None,
                     source_id: str | None = None, limit: int = 500) -> list:
    q: dict = {}
    if status and status != "all":
        q["status"] = status
    if material_id:
        q["material_id"] = material_id
    if source_id:
        q["source.id"] = source_id
    rows = await db[QUARANTINE_COLL].find(q, {"_id": 0}).sort("created_at", -1).to_list(limit)
    for r in rows:
        r["value"] = _r(_r(r.get("remaining_qty")) * _r(r.get("unit_cost")))
        r["age_days"] = _age_days(r.get("created_at"))
    return rows


def _age_days(ts) -> int:
    if not ts:
        return 0
    try:
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return max(0, (_now() - ts).days)
    except Exception:
        return 0


async def summary(db) -> dict:
    rows = await db[QUARANTINE_COLL].find({}, {"_id": 0}).to_list(5000)
    open_rows = [r for r in rows if r.get("status") == "open"]
    # `by_reason` DULU melakukan `rr.get("code")` langsung sehingga satu dokumen lama
    # berbentuk `["KOTOR"]` (list of string) mematikan SELURUH KPI dengan HTTP 500.
    # Sekarang agregasinya lewat SSOT yang tahan bentuk apa pun (utils/reject_reasons.py).
    by_reason = summarize_by_reason(open_rows, qty_field="remaining_qty")
    disposed = sum(len(r.get("dispositions") or []) for r in rows
                   if isinstance(r.get("dispositions"), (list, tuple)))
    qloc = await get_quarantine_location_info(db)
    return {
        "open_items": len(open_rows),
        "open_qty": _r(sum(_r(r.get("remaining_qty")) for r in open_rows)),
        "open_value": _r(sum(_r(r.get("remaining_qty")) * _r(r.get("unit_cost")) for r in open_rows)),
        "valued_items": len([r for r in open_rows if r.get("valued")]),
        "unvalued_items": len([r for r in open_rows if not r.get("valued")]),
        "closed_items": len([r for r in rows if r.get("status") == "closed"]),
        "dispositions_total": disposed,
        "oldest_age_days": max([_age_days(r.get("created_at")) for r in open_rows] or [0]),
        "by_reason": by_reason,
        "location": qloc,
    }


async def quarantine_qty_map(db, material_ids=None) -> dict:
    """{material_id: qty} yang sedang berada di lokasi karantina (fisik ada, tidak tersedia)."""
    qloc = await get_quarantine_location_id(db)
    q: dict = {"location_id": qloc}
    if material_ids is not None:
        ids = [m for m in material_ids if m]
        if not ids:
            return {}
        q["material_id"] = {"$in": ids}
    rows = await db[stock_service.STOCK].find(q, {"_id": 0}).to_list(20000)
    out: dict = {}
    for r in rows:
        mid = r.get("material_id")
        if mid:
            out[mid] = _r(out.get(mid, 0) + read_qty(r))
    return out
