"""dewi_rnd — HPP Calculator + Tech Pack."""
from fastapi import Depends, HTTPException
from database import get_db
from auth import require_auth
from routes.dewi_rnd_shared import (
    router, now_utc, sid, serialize,
    line_code, line_name, resolve_master_material, resolve_rnd_material,
)
from utils.fabric_costing import compute_fabric_cost
from core import bom_uom  # 2026-08-02: konversi satuan baris BOM → satuan dasar/harga

# ──────────────────────────────────────────────────────────────────────────────
# HPP CALCULATOR (Full Cost per Pcs → Harga Jual Proposal)
# ──────────────────────────────────────────────────────────────────────────────

def _num(value, default):
    """Coerce to float, respecting an explicit 0 (only None/'' fall back to default)."""
    if value is None or value == '':
        return float(default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _calculate_hpp(body: dict, bom_material_cost=None) -> dict:
    """Core HPP calculation logic.

    Jika `bom_material_cost` diberikan (mode BOM otomatis — KEPUTUSAN #2 / decision 4.a),
    biaya material diambil dari perhitungan BOM (Σ qty × unit_cost material master) dan
    input manual fabric_usage/accessories DIABAIKAN. Jika None, fallback ke input manual
    (fabric_usage × fabric_price + accessories) — kompatibilitas mundur.

    Biaya CMT (`cmt_cost_per_pcs`) tetap INPUT MANUAL per model (decision 3.a).
    """
    fabric_usage   = _num(body.get('fabric_usage_per_pcs'), 0)
    fabric_price   = _num(body.get('fabric_price_per_meter'), 0)
    accessories    = body.get('accessories_cost', [])
    cmt_cost       = _num(body.get('cmt_cost_per_pcs'), 0)
    cutting_cost   = _num(body.get('cutting_cost_per_pcs'), 0)
    packaging_cost = _num(body.get('packaging_cost_per_pcs'), 0)
    overhead_pct   = _num(body.get('overhead_pct'), 10)
    margin_pct     = _num(body.get('margin_pct'), 30)

    if bom_material_cost is not None:
        # Mode BOM otomatis: material_cost = biaya BOM (fabric+accessories dari BOM).
        material_cost = _num(bom_material_cost, 0)
        fabric_cost   = material_cost
        acc_total     = 0.0
        material_source = 'bom'
    else:
        # Mode manual (legacy).
        fabric_cost   = fabric_usage * fabric_price
        acc_total     = sum(
            _num(a.get('unit_cost'), 0) * _num(a.get('qty'), 1)
            for a in accessories
        )
        material_cost = fabric_cost + acc_total
        material_source = 'manual'

    direct_cost   = material_cost + cmt_cost + cutting_cost + packaging_cost
    overhead_val  = direct_cost * overhead_pct / 100
    hpp_total     = direct_cost + overhead_val
    selling_price = hpp_total / (1 - margin_pct / 100) if margin_pct < 100 else hpp_total

    return {
        'fabric_cost':            round(fabric_cost, 2),
        'accessories_total':      round(acc_total, 2),
        'material_cost':          round(material_cost, 2),
        'material_source':        material_source,
        'cmt_cost':               round(cmt_cost, 2),
        'cutting_cost':           round(cutting_cost, 2),
        'packaging_cost':         round(packaging_cost, 2),
        'direct_cost':            round(direct_cost, 2),
        'overhead_value':         round(overhead_val, 2),
        'hpp_total':              round(hpp_total, 2),
        'selling_price_proposal': round(selling_price, 2),
        'margin_pct':             margin_pct,
        'overhead_pct':           overhead_pct,
    }


async def _material_cost_from_bom(db, bom_items: list) -> tuple:
    """Hitung biaya material dari BOM Tech Pack × harga master (KEPUTUSAN #2 / 4.a).

    DIPERBAIKI 2026-08-02 (laporan owner: "satuan & konversi material belum ada di
    RnD untuk BOM-nya, termasuk costing"). Sebelumnya `line_cost = qty × unit_cost`
    TANPA melihat satuan, padahal:
      · `rahaza_materials.unit_cost` = harga per **satuan dasar** (INV-UOM-1),
        mis. per kg untuk kain rajut — sementara baris BOM RnD sering ditulis
        dalam meter/yard/gram/lusin → biaya bisa ratusan kali salah.
      · `dewi_rnd_materials.price_per_meter` = harga per **meter**, dipakai apa
        adanya walau baris BOM bersatuan kg/pcs.

    Sekarang setiap baris dikonversi lewat `core.bom_uom` (kemasan material →
    tabel dimensi global → gramasi×lebar kain), lalu:
      · harga dari master material  → biaya = qty(satuan dasar) × unit_cost
      · harga per meter (RnD)       → biaya = qty(meter) × price_per_meter
    Breakdown mengembalikan qty asli + qty terkonversi + status konversi supaya
    ketidakcocokan satuan kelihatan, bukan diam-diam salah.
    """
    breakdown = []
    total = 0.0
    for line in (bom_items or []):
        qty = _num(line.get('qty') or line.get('quantity') or line.get('usage'), 0)
        code = line_code(line)
        name = line_name(line) or code
        unit = bom_uom.norm_unit(line.get('unit') or '')

        # Baris Tech Pack memakai kunci `material` (nama) — bukan `material_code`.
        # Master dicari lewat id → kode → NAMA supaya baris techpack lama pun
        # tetap dapat harga & faktor konversinya.
        master = await resolve_master_material(db, line)
        if master and not code:
            code = str(master.get('code') or '')

        # Konversi baris → satuan dasar material
        factor, base_unit, uom_status, uom_note = bom_uom.line_factor(master, unit or None)
        qty_base = round(qty * factor, 6)

        unit_cost = _num(line.get('unit_cost') or line.get('unit_price'), 0)
        source = 'bom_line' if unit_cost > 0 else None
        cost_unit = unit or base_unit          # satuan yang dipakai harga baris
        qty_for_cost = qty if unit_cost > 0 else qty_base

        if unit_cost <= 0 and master and _num(master.get('unit_cost'), 0) > 0:
            unit_cost = _num(master.get('unit_cost'), 0)
            source = 'rahaza_materials.unit_cost'
            cost_unit = base_unit
            qty_for_cost = qty_base
            name = name or master.get('name') or code
        if unit_cost <= 0:
            rm = await resolve_rnd_material(db, line)
            if rm:
                # RnD boleh menyatakan satuan harganya sendiri (`unit`/`price_unit`);
                # default lama = per meter.
                rnd_unit = bom_uom.norm_unit(rm.get('price_unit') or rm.get('unit') or 'm')
                rnd_price = _num(rm.get('price_per_unit') or rm.get('price_per_meter'), 0)
                if rnd_price > 0:
                    qty_in_rnd_unit = None
                    if rnd_unit == (unit or rnd_unit):
                        qty_in_rnd_unit = qty
                    else:
                        gf = bom_uom.global_factor(unit or rnd_unit, rnd_unit)
                        if gf:
                            qty_in_rnd_unit = qty * gf
                        elif master is not None:
                            f2, _b, st2, _n2 = bom_uom.line_factor(master, rnd_unit)
                            if st2 in ('base', 'uom', 'global', 'fabric') and f2:
                                qty_in_rnd_unit = qty_base / f2
                    if qty_in_rnd_unit is not None:
                        unit_cost = rnd_price
                        source = f'dewi_rnd_materials.price_per_{rnd_unit}'
                        cost_unit = rnd_unit
                        qty_for_cost = round(qty_in_rnd_unit, 6)
                        name = name or rm.get('material_name') or code
                    else:
                        uom_status = 'mismatch'
                        uom_note = (uom_note or '') + (
                            f" Harga RnD per {rnd_unit} tidak bisa dipakai untuk satuan "
                            f"BOM '{unit or '-'}' (lengkapi satuan/kemasan material).")

        line_cost = _num(qty_for_cost, 0) * unit_cost
        total += line_cost
        breakdown.append({
            'material_code': code,
            'material_name': name,
            'qty': qty,
            'unit': unit,
            'qty_base': qty_base,
            'unit_base': base_unit,
            'uom_factor': round(factor, 8),
            'uom_status': uom_status,
            'uom_note': uom_note,
            'qty_costed': round(_num(qty_for_cost, 0), 6),
            'cost_unit': cost_unit,
            'unit_cost': round(unit_cost, 2),
            'line_cost': round(line_cost, 2),
            'cost_source': source or 'unresolved',
        })
    return round(total, 2), breakdown


async def annotate_techpack_bom(db, bom_items: list) -> list:
    """Tautkan baris BOM Tech Pack ke master material + simpan hasil konversi satuannya.

    Ditulis saat tech pack disimpan supaya `qty_base`/`unit_base`/`uom_status`
    tersedia untuk konsumen hilir (HPP dari BOM, tampilan Tech Pack) tanpa
    menghitung ulang, dan supaya satuan yang tidak bisa dikonversi kelihatan.
    """
    out = []
    for line in (bom_items or []):
        row = dict(line)
        master = await resolve_master_material(db, row)
        unit = bom_uom.norm_unit(row.get('unit') or '')
        factor, base_unit, status, note = bom_uom.line_factor(master, unit or None)
        qty = _num(row.get('qty'), 0)
        row['unit'] = unit or base_unit
        if master:
            row['material_id'] = master.get('id')
            row['material_code'] = master.get('code') or row.get('material_code') or ''
        row.update({
            'unit_base': base_unit,
            'uom_factor': round(factor, 8),
            'qty_base': round(qty * factor, 6),
            'uom_status': status,
            'uom_note': note,
        })
        out.append(row)
    return out


async def _latest_bom_for_style(db, style_id: str) -> list:
    """Ambil bom_items dari tech-pack terbaru (is_latest) untuk sebuah style."""
    tp = await db.dewi_rnd_tech_packs.find_one(
        {'style_id': style_id, 'is_latest': True}, {'_id': 0}
    )
    if not tp:
        tp = await db.dewi_rnd_tech_packs.find_one(
            {'style_id': style_id}, {'_id': 0}, sort=[('created_at', -1)]
        )
    return (tp or {}).get('bom_items', []) or []


async def _propagate_hpp(db, style_id: str, hpp_total: float, selling_price=None) -> dict:
    """Propagasi HPP RnD → Production Model → FG → Katalog Marketing (auto-refresh).

    KEPUTUSAN #2 (4.a): saat HPP RnD dihitung/di-update, HPP pada item katalog yang
    tertaut (via model_id / fg_material_id) ikut ter-refresh otomatis. `hpp` katalog =
    HPP dari RnD (bukan input marketing).
    """
    if not style_id:
        return {'models': 0, 'fg': 0, 'catalog_items': 0}
    now = now_utc()
    hpp_total = round(_num(hpp_total, 0), 2)

    # 1) Production models turunan style ini
    model_ids = [m['id'] async for m in db.rahaza_models.find({'rnd_style_id': style_id}, {'id': 1})]
    if model_ids:
        await db.rahaza_models.update_many(
            {'id': {'$in': model_ids}},
            {'$set': {'hpp': hpp_total, 'hpp_updated_at': now}},
        )

    # 2) FG (rahaza_materials type='fg') tertaut ke style / model → set hpp
    fg_filter = {'$or': [{'rnd_style_id': style_id}]}
    if model_ids:
        fg_filter['$or'].append({'model_id': {'$in': model_ids}})
    fg_ids = [f['id'] async for f in db.rahaza_materials.find(fg_filter, {'id': 1})]
    if fg_ids:
        await db.rahaza_materials.update_many(
            {'id': {'$in': fg_ids}},
            {'$set': {'hpp': hpp_total, 'hpp_updated_at': now}},
        )

    # 3) Katalog marketing tertaut (model_id ATAU fg_material_id)
    cat_or = []
    if model_ids:
        cat_or.append({'model_id': {'$in': model_ids}})
    if fg_ids:
        cat_or.append({'fg_material_id': {'$in': fg_ids}})
    cat_modified = 0
    if cat_or:
        res = await db.marketing_catalog_items.update_many(
            {'$or': cat_or},
            {'$set': {
                'hpp': hpp_total,
                'hpp_source': 'rnd',
                'hpp_updated_at': now,
                'updated_at': now,
            }},
        )
        cat_modified = res.modified_count
    return {'models': len(model_ids), 'fg': len(fg_ids), 'catalog_items': cat_modified}


@router.get('/hpp-calculator')
async def list_hpp(
    style_id: str = None,
    user: dict = Depends(require_auth),
):
    db = get_db()
    q = {}
    if style_id:
        q['style_id'] = style_id
    docs = await db.dewi_rnd_hpp.find(q, {'_id': 0}).sort('created_at', -1).to_list(200)
    return [serialize(d) for d in docs]


@router.get('/hpp/fabric-estimate')
async def hpp_fabric_estimate(
    style_id: str,
    size: str = None,
    user: dict = Depends(require_auth),
):
    """#1 HPP otomatis: estimasi biaya kain/pcs per-size dari fabric_consumption techpack.

    Dipakai HPP Calculator (auto-fill pemakaian kain + harga tertimbang) & Pola/Marking.
    """
    db = get_db()
    tp = await db.dewi_rnd_tech_packs.find_one(
        {'style_id': style_id, 'is_latest': True}, {'_id': 0}
    ) or await db.dewi_rnd_tech_packs.find_one(
        {'style_id': style_id}, {'_id': 0}, sort=[('created_at', -1)]
    )
    if not tp:
        raise HTTPException(404, 'Tech pack untuk style ini belum ada. Buat/import techpack dulu.')
    res = await compute_fabric_cost(db, tp, size)
    res['style_id'] = style_id
    res['style_code'] = tp.get('style_code', '')
    res['style_name'] = tp.get('style_name', '')
    res['fabric_consumption_rows'] = len(tp.get('fabric_consumption') or [])
    return serialize(res)


@router.post('/hpp-calculator')
async def create_hpp(body: dict, user: dict = Depends(require_auth)):
    db = get_db()
    style_id = body.get('style_id', '')

    # Mode BOM otomatis (KEPUTUSAN #2 / 4.a): material dari BOM × unit_cost master.
    use_bom = bool(body.get('use_bom')) or ('bom_items' in body)
    bom_breakdown = []
    if use_bom:
        bom_items = body.get('bom_items')
        if not bom_items and style_id:
            bom_items = await _latest_bom_for_style(db, style_id)
        material_cost, bom_breakdown = await _material_cost_from_bom(db, bom_items or [])
        calc = _calculate_hpp(body, bom_material_cost=material_cost)
    else:
        calc = _calculate_hpp(body)

    doc = {
        'id':         sid(),
        'hpp_code':   body.get('hpp_code', f"HPP-{sid()[:6].upper()}"),
        'style_id':   style_id,
        'style_code': body.get('style_code', ''),
        'style_name': body.get('style_name', ''),
        'fabric_usage_per_pcs':   body.get('fabric_usage_per_pcs', 0),
        'fabric_price_per_meter': body.get('fabric_price_per_meter', 0),
        'fabric_source':          body.get('fabric_source', 'manual'),   # 'techpack' bila di-tarik dari fabric_consumption
        'fabric_size':            body.get('fabric_size', ''),           # size acuan saat tarik dari techpack
        'accessories_cost':       body.get('accessories_cost', []),
        'cmt_cost_per_pcs':       body.get('cmt_cost_per_pcs', 0),
        'cutting_cost_per_pcs':   body.get('cutting_cost_per_pcs', 0),
        'packaging_cost_per_pcs': body.get('packaging_cost_per_pcs', 0),
        'overhead_pct':           body.get('overhead_pct', 10),
        'margin_pct':             body.get('margin_pct', 30),
        'use_bom':                use_bom,
        'bom_breakdown':          bom_breakdown,
        'notes':                  body.get('notes', ''),
        'status':                 body.get('status', 'draft'),
        **calc,
        'created_by':      user['id'],
        'created_by_name': user.get('name', ''),
        'created_at': now_utc(),
        'updated_at': now_utc(),
    }
    await db.dewi_rnd_hpp.insert_one(doc)
    # Auto-refresh HPP ke model/FG/katalog tertaut.
    propagation = await _propagate_hpp(db, style_id, doc['hpp_total'], doc.get('selling_price_proposal'))
    out = serialize(doc)
    out['_propagation'] = propagation
    return out


@router.put('/hpp-calculator/{calc_id}')
async def update_hpp(calc_id: str, body: dict, user: dict = Depends(require_auth)):
    db = get_db()
    existing = await db.dewi_rnd_hpp.find_one({'id': calc_id}, {'_id': 0})
    if not existing:
        raise HTTPException(404, 'HPP calculation tidak ditemukan')

    style_id = body.get('style_id', existing.get('style_id', ''))
    use_bom = body.get('use_bom', existing.get('use_bom'))
    use_bom = bool(use_bom) or ('bom_items' in body)
    bom_breakdown = existing.get('bom_breakdown', [])
    if use_bom:
        bom_items = body.get('bom_items')
        if not bom_items and style_id:
            bom_items = await _latest_bom_for_style(db, style_id)
        material_cost, bom_breakdown = await _material_cost_from_bom(db, bom_items or [])
        # gabungkan input manual lain (cmt/cutting/packaging/overhead/margin) dari body+existing
        merged = {**existing, **body}
        calc = _calculate_hpp(merged, bom_material_cost=material_cost)
    else:
        merged = {**existing, **body}
        calc = _calculate_hpp(merged)

    upd = {k: v for k, v in body.items() if k not in ('id', '_id', 'created_at', 'created_by', 'bom_items')}
    upd.update(calc)
    upd['use_bom'] = use_bom
    upd['bom_breakdown'] = bom_breakdown
    upd['updated_at'] = now_utc()
    res = await db.dewi_rnd_hpp.update_one({'id': calc_id}, {'$set': upd})
    if res.matched_count == 0:
        raise HTTPException(404, 'HPP calculation tidak ditemukan')
    doc = await db.dewi_rnd_hpp.find_one({'id': calc_id}, {'_id': 0})
    propagation = await _propagate_hpp(db, style_id, doc.get('hpp_total'), doc.get('selling_price_proposal'))
    out = serialize(doc)
    out['_propagation'] = propagation
    return out


@router.delete('/hpp-calculator/{calc_id}')
async def delete_hpp(calc_id: str, user: dict = Depends(require_auth)):
    db = get_db()
    res = await db.dewi_rnd_hpp.delete_one({'id': calc_id})
    if res.deleted_count == 0:
        raise HTTPException(404, 'HPP calculation tidak ditemukan')
    return {'ok': True}


@router.post('/hpp-calculator/preview')
async def preview_hpp(body: dict, user: dict = Depends(require_auth)):
    """Calculate HPP on-the-fly without saving (for live preview)."""
    return _calculate_hpp(body)


@router.post('/hpp-calculator/compute-from-bom')
async def compute_hpp_from_bom(body: dict, user: dict = Depends(require_auth)):
    """Preview HPP dengan biaya material OTOMATIS dari BOM (KEPUTUSAN #2 / decision 4.a).

    Body:
      - style_id (opsional): jika diberikan & bom_items kosong → ambil BOM dari tech-pack terbaru.
      - bom_items (opsional): override daftar BOM [{material_code|material_id, qty, unit, unit_cost?}].
      - cmt_cost_per_pcs, cutting_cost_per_pcs, packaging_cost_per_pcs (manual), overhead_pct, margin_pct.
    Return: hasil kalkulasi + material_breakdown + bom_material_cost.
    """
    db = get_db()
    style_id = body.get('style_id', '')
    bom_items = body.get('bom_items')
    if not bom_items and style_id:
        bom_items = await _latest_bom_for_style(db, style_id)
    material_cost, breakdown = await _material_cost_from_bom(db, bom_items or [])
    calc = _calculate_hpp(body, bom_material_cost=material_cost)
    return {
        **calc,
        'bom_material_cost': material_cost,
        'material_breakdown': breakdown,
        'bom_items_count': len(bom_items or []),
        'style_id': style_id,
    }


@router.post('/hpp-calculator/{calc_id}/propagate')
async def propagate_hpp_endpoint(calc_id: str, user: dict = Depends(require_auth)):
    """Paksa propagasi ulang HPP ini ke Production Model → FG → Katalog Marketing."""
    db = get_db()
    doc = await db.dewi_rnd_hpp.find_one({'id': calc_id}, {'_id': 0})
    if not doc:
        raise HTTPException(404, 'HPP calculation tidak ditemukan')
    result = await _propagate_hpp(db, doc.get('style_id', ''), doc.get('hpp_total'), doc.get('selling_price_proposal'))
    return {'ok': True, 'hpp_total': doc.get('hpp_total'), 'propagation': result}


# ──────────────────────────────────────────────────────────────────────────────
# TECH PACK (Dokumen teknis per style: BOM, konstruksi, grading)
# ──────────────────────────────────────────────────────────────────────────────

@router.get('/tech-packs')
async def list_tech_packs(
    style_id: str = None,
    search: str = None,
    user: dict = Depends(require_auth),
):
    db = get_db()
    q: dict = {}
    if style_id:
        q['style_id'] = style_id
    if search:
        q['$or'] = [
            {'style_code':  {'$regex': search, '$options': 'i'}},
            {'style_name':  {'$regex': search, '$options': 'i'}},
            {'version':     {'$regex': search, '$options': 'i'}},
        ]
    docs = await db.dewi_rnd_tech_packs.find(q, {'_id': 0}).sort('created_at', -1).to_list(200)
    return [serialize(d) for d in docs]


@router.post('/tech-packs')
async def create_tech_pack(body: dict, user: dict = Depends(require_auth)):
    db = get_db()
    doc = {
        'id':           sid(),
        'style_id':     body.get('style_id', ''),
        'style_code':   body.get('style_code', ''),
        'style_name':   body.get('style_name', ''),
        'version':      body.get('version', 'v1'),
        'doc_url':      body.get('doc_url', None),
        'doc_type':     body.get('doc_type', 'pdf'),
        'title':        body.get('title', ''),
        'description':  body.get('description', ''),
        'bom_items':    await annotate_techpack_bom(db, body.get('bom_items', [])),
        'fabrics':            body.get('fabrics', []),               # (c) main + combination
        'fabric_consumption': body.get('fabric_consumption', []),   # (c) per-size + kombinasi
        'construction_points': body.get('construction_points', []), # (b) per-poin terstruktur
        'construction_notes': body.get('construction_notes', ''),
        'stitch_type':        body.get('stitch_type', ''),
        'seam_allowance_mm':  body.get('seam_allowance_mm', 10),
        'size_grading_notes': body.get('size_grading_notes', ''),
        'base_size':          body.get('base_size', 'M'),
        'size_range':         body.get('size_range', 'S-XL'),
        'size_columns':       body.get('size_columns', []),         # dynamic measurement categories
        'fit_categories':     body.get('fit_categories', []),       # #2b: info fit (Standar/Jumbo), tidak ubah SKU
        'measurements':       body.get('measurements', []),
        'status':       body.get('status', 'draft'),
        'approved_by':  None,
        'approved_at':  None,
        'is_latest':    True,
        'created_by':      user['id'],
        'created_by_name': user.get('name', ''),
        'created_at':   now_utc(),
        'updated_at':   now_utc(),
    }
    if body.get('style_id'):
        await db.dewi_rnd_tech_packs.update_many(
            {'style_id': body['style_id'], 'is_latest': True},
            {'$set': {'is_latest': False}},
        )
    await db.dewi_rnd_tech_packs.insert_one(doc)
    return serialize(doc)


@router.get('/tech-packs/{tp_id}')
async def get_tech_pack(tp_id: str, user: dict = Depends(require_auth)):
    db = get_db()
    doc = await db.dewi_rnd_tech_packs.find_one({'id': tp_id}, {'_id': 0})
    if not doc:
        raise HTTPException(404, 'Tech pack tidak ditemukan')
    return serialize(doc)


@router.put('/tech-packs/{tp_id}')
async def update_tech_pack(tp_id: str, body: dict, user: dict = Depends(require_auth)):
    db = get_db()
    upd = {k: v for k, v in body.items() if k not in ('id', '_id', 'created_at', 'created_by')}
    if 'bom_items' in upd:
        upd['bom_items'] = await annotate_techpack_bom(db, upd['bom_items'])
    upd['updated_at'] = now_utc()
    res = await db.dewi_rnd_tech_packs.update_one({'id': tp_id}, {'$set': upd})
    if res.matched_count == 0:
        raise HTTPException(404, 'Tech pack tidak ditemukan')
    doc = await db.dewi_rnd_tech_packs.find_one({'id': tp_id}, {'_id': 0})
    return serialize(doc)


@router.post('/tech-packs/{tp_id}/approve')
async def approve_tech_pack(tp_id: str, user: dict = Depends(require_auth)):
    from routes.shared import assert_can_act
    assert_can_act(user, 'rnd.approve', portal='rnd',
                   legacy_roles=('rnd_staff', 'manager_produksi', 'supervisor_produksi',
                                 'manager', 'owner', 'admin', 'superadmin'),
                   what='menyetujui tech pack')
    db = get_db()
    res = await db.dewi_rnd_tech_packs.update_one(
        {'id': tp_id},
        {'$set': {
            'status':      'approved',
            'approved_by':  user.get('name', ''),
            'approved_at':  now_utc(),
            'updated_at':   now_utc(),
        }},
    )
    if res.matched_count == 0:
        raise HTTPException(404, 'Tech pack tidak ditemukan')
    return {'ok': True}


@router.delete('/tech-packs/{tp_id}')
async def delete_tech_pack(tp_id: str, user: dict = Depends(require_auth)):
    db = get_db()
    res = await db.dewi_rnd_tech_packs.delete_one({'id': tp_id})
    if res.deleted_count == 0:
        raise HTTPException(404, 'Tech pack tidak ditemukan')
    return {'ok': True}
