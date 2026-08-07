"""
Marketing Catalog - Items
Item CRUD + photos + FG integration
"""
import logging
import os
import re
import uuid
import html
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from pydantic import BaseModel, Field
from database import get_db
from auth import require_auth
from core import material_fields as _mf  # FASE 6.6-B: SSOT nama field + alias legacy yarn_*
from core.stock_schema import read_qty, read_reserved

router = APIRouter(prefix='/api/marketing/catalogs', tags=['Marketing-Catalog-items'])

# Photo upload settings
PRODUCT_UPLOAD_ROOT = Path('/app/uploads/products')
PRODUCT_UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
MAX_PHOTO_BYTES = 5 * 1024 * 1024
ALLOWED_MIMES = {'image/jpeg', 'image/png', 'image/webp'}
ALLOWED_EXT = {'jpg', 'jpeg', 'png', 'webp'}

# Helper functions
def _uid():
    return str(uuid.uuid4())

def _now():
    return datetime.now(timezone.utc)

def _san(value: str, max_len: int = 500) -> str:
    if not isinstance(value, str):
        return value
    return html.escape(value.strip())[:max_len]

def _s(doc: dict) -> dict:
    if doc is None:
        return {}
    out = dict(doc)
    out.pop('_id', None)
    for k, v in out.items():
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    return _normalize_pricing_read(out)


def _normalize_pricing_read(out: dict) -> dict:
    """Pastikan field harga kanonik selalu ada saat dibaca (KEPUTUSAN #2).

    Kanonik: harga_jual (final ke customer), harga_coret (promo dicoret),
    harga_original (list resmi), hpp (biaya, internal — dari RnD).
    Backward-compat: item lama hanya punya `price` (=jual) & `original_price`
    (dulu dipakai ganda utk HPP/coret) → dipetakan ke harga_jual/harga_coret.
    Legacy `price`/`original_price` tetap disinkron agar konsumen lama tak rusak.
    """
    legacy_price = float(out.get('price') or 0)
    legacy_original = float(out.get('original_price') or 0)

    harga_jual = out.get('harga_jual')
    harga_jual = float(harga_jual) if harga_jual is not None else legacy_price

    harga_coret = out.get('harga_coret')
    harga_coret = float(harga_coret) if harga_coret is not None else legacy_original

    harga_original = float(out.get('harga_original') or 0)
    hpp = float(out.get('hpp') or 0)

    out['harga_jual'] = harga_jual
    out['harga_coret'] = harga_coret
    out['harga_original'] = harga_original
    out['hpp'] = hpp
    # sinkron legacy (jual→price, coret→original_price)
    out['price'] = harga_jual
    out['original_price'] = harga_coret
    return out


def _pricing_write_fields(data: dict, existing: dict = None) -> dict:
    """Bangun set-field harga untuk WRITE (create/update).

    Menerima input harga baru (harga_jual/harga_coret/harga_original/hpp) DAN/ATAU
    legacy (price/original_price). Menormalkan → simpan field kanonik + legacy sinkron.
    Hanya field yang benar-benar diberikan yang di-set (agar update parsial aman).
    """
    existing = existing or {}
    fields = {}

    def _pick(new_key, legacy_key=None):
        if data.get(new_key) is not None:
            return float(data.get(new_key) or 0)
        if legacy_key and data.get(legacy_key) is not None:
            return float(data.get(legacy_key) or 0)
        return None

    hj = _pick('harga_jual', 'price')
    hc = _pick('harga_coret', 'original_price')
    ho = _pick('harga_original')
    hp = _pick('hpp')

    if hj is not None:
        fields['harga_jual'] = hj
        fields['price'] = hj  # legacy sync
    if hc is not None:
        fields['harga_coret'] = hc
        fields['original_price'] = hc  # legacy sync
    if ho is not None:
        fields['harga_original'] = ho
    if hp is not None:
        fields['hpp'] = hp
    return fields

def _stock_status(qty: float, threshold: float) -> str:
    if qty <= 0:
        return 'out_of_stock'
    elif qty <= threshold:
        return 'low_stock'
    else:
        return 'in_stock'


# ═══════════════════════════════════════════════════════════════════════════════
# FASE 3b — Jembatan stok Toko ↔ Finished Goods (by SKU varian)
# Konvensi: rahaza_model_variants.sku == kode FG (rahaza_materials.code, type='fg').
# Stok fisik & reservasi diambil dari rahaza_material_stock (SSOT skema stok).
# ═══════════════════════════════════════════════════════════════════════════════
async def resolve_fg_stock_by_sku(db, sku: str) -> dict:
    """Resolve stok FG untuk sebuah SKU varian.

    Match: rahaza_materials (type='fg') dengan `code`/`sku` == sku (case-insensitive),
    lalu jumlahkan stok dari rahaza_material_stock lintas lokasi.

    Return dict:
      { found, fg_material_id, fg_code, onhand, reserved, available }
    - onhand    = total fisik on-hand (read_qty)
    - reserved  = total ter-reserve (read_reserved)
    - available = max(0, onhand - reserved) → yang benar-benar bisa dijual
    """
    result = {
        'found': False, 'fg_material_id': None, 'fg_code': '',
        'onhand': 0.0, 'reserved': 0.0, 'available': 0.0,
    }
    sku = (sku or '').strip()
    if not sku:
        return result
    pattern = f'^{re.escape(sku)}$'
    fg = await db.rahaza_materials.find_one(
        {
            'type': 'fg',
            '$or': [
                {'code': {'$regex': pattern, '$options': 'i'}},
                {'sku': {'$regex': pattern, '$options': 'i'}},
            ],
        },
        {'_id': 0},
    )
    if not fg:
        return result
    result['found'] = True
    result['fg_material_id'] = fg.get('id')
    result['fg_code'] = fg.get('code') or fg.get('sku') or ''
    rows = await db.rahaza_material_stock.find({'material_id': fg.get('id')}, {'_id': 0}).to_list(1000)
    onhand = sum(read_qty(s) for s in rows)
    reserved = sum(read_reserved(s) for s in rows)
    result['onhand'] = round(onhand, 2)
    result['reserved'] = round(reserved, 2)
    result['available'] = round(max(0.0, onhand - reserved), 2)
    return result


async def resolve_item_fg_stock(db, item: dict) -> dict:
    """Resolve stok FG untuk sebuah catalog item.

    Prioritas tautan (Fase 3b):
      1. item.variant_sku  → cocokkan by SKU ke master FG (jalur varian internal)
      2. item.fg_material_id / material_id → langsung by material FG

    Return dict resolver + field `link_type` ('variant_sku' | 'fg_material' | 'none').
    """
    variant_sku = (item.get('variant_sku') or '').strip()
    if variant_sku:
        res = await resolve_fg_stock_by_sku(db, variant_sku)
        res['link_type'] = 'variant_sku'
        res['variant_sku'] = variant_sku
        return res
    mat_id = item.get('fg_material_id') or item.get('material_id')
    if mat_id:
        rows = await db.rahaza_material_stock.find({'material_id': mat_id}, {'_id': 0}).to_list(1000)
        onhand = sum(read_qty(s) for s in rows)
        reserved = sum(read_reserved(s) for s in rows)
        fg = await db.rahaza_materials.find_one({'id': mat_id}, {'_id': 0, 'code': 1, 'sku': 1})
        return {
            'found': bool(rows) or bool(fg),
            'fg_material_id': mat_id,
            'fg_code': (fg.get('code') or fg.get('sku') or '') if fg else '',
            'onhand': round(onhand, 2), 'reserved': round(reserved, 2),
            'available': round(max(0.0, onhand - reserved), 2),
            'link_type': 'fg_material',
        }
    return {'found': False, 'fg_material_id': None, 'fg_code': '', 'onhand': 0.0,
            'reserved': 0.0, 'available': 0.0, 'link_type': 'none'}


async def _apply_fg_stock_sync(db, item: dict) -> dict:
    """Sinkronkan stok fisik item Toko dari FG (auto-override, KEPUTUSAN 2b).

    stock_quantity item Toko := available FG (onhand - reserved). Simpan juga snapshot
    fg_onhand / fg_reserved / fg_available + fg_material_id + last_stock_sync.

    Raise HTTPException bila item tidak tertaut atau master FG tidak ditemukan.
    """
    res = await resolve_item_fg_stock(db, item)
    if res['link_type'] == 'none':
        raise HTTPException(400, 'Item tidak tertaut ke varian/FG. Tautkan varian (variant_id) atau FG dulu.')
    if not res['found']:
        if res['link_type'] == 'variant_sku':
            raise HTTPException(404, f"Master FG untuk SKU varian '{res.get('variant_sku','')}' belum ada di inventory (rahaza_materials type='fg').")
        raise HTTPException(404, 'Master FG tidak ditemukan / belum ada stok di WMS.')
    new_stock = float(res['available'])
    threshold = float(item.get('stock_alert_threshold', 10) or 10)
    patch = {
        'stock_quantity': new_stock,
        'stock_status': _stock_status(new_stock, threshold),
        'fg_onhand': res['onhand'],
        'fg_reserved': res['reserved'],
        'fg_available': res['available'],
        'fg_material_id': item.get('fg_material_id') or res.get('fg_material_id'),
        'stock_source': res['link_type'],
        'last_stock_sync': _now(),
        'updated_at': _now(),
    }
    await db.marketing_catalog_items.update_one({'id': item['id']}, {'$set': patch})
    return {**res, 'new_stock': new_stock, 'stock_status': patch['stock_status']}


async def _refresh_catalog_stats(db, catalog_id: str):
    items = await db.marketing_catalog_items.find(
        {'catalog_id': catalog_id, 'is_active': True},
        {'_id': 0, 'stock_quantity': 1, 'stock_status': 1}
    ).to_list(500)
    total_stock = sum(float(i.get('stock_quantity', 0)) for i in items)
    low = sum(1 for i in items if i.get('stock_status') == 'low_stock')
    out = sum(1 for i in items if i.get('stock_status') == 'out_of_stock')
    await db.marketing_catalogs.update_one(
        {'id': catalog_id},
        {'$set': {
            'item_count': len(items),
            'total_stock': total_stock,
            'low_stock_count': low,
            'out_of_stock_count': out,
            'updated_at': _now(),
        }}
    )


# Pydantic models
# ─── Pydantic Models ──────────────────────────────────────────────────────────

class CatalogCreate(BaseModel):
    account_id: str
    name: str
    description: Optional[str] = ''
    platform: Optional[str] = ''     # inherited from account, stored for quick filter
    is_active: Optional[bool] = True


class CatalogUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class CatalogItemCreate(BaseModel):
    sku: str
    name: str
    description: Optional[str] = ''
    price: Optional[float] = Field(default=0, ge=0)          # legacy selling price (=harga_jual)
    original_price: Optional[float] = Field(default=0, ge=0) # legacy (=harga_coret)
    platform_price: Optional[float] = 0 # actual listed price on platform (can differ)
    # KEPUTUSAN #2 — field harga terpisah (kanonik)
    harga_jual: Optional[float] = Field(default=None, ge=0)     # harga final ke customer
    harga_coret: Optional[float] = Field(default=None, ge=0)    # harga dicoret (promo, >= jual)
    harga_original: Optional[float] = Field(default=None, ge=0) # harga normal/list resmi
    hpp: Optional[float] = Field(default=None, ge=0)            # biaya pokok (internal, dari RnD)
    stock_quantity: Optional[float] = Field(default=0, ge=0)
    stock_alert_threshold: Optional[float] = Field(default=10, ge=0)
    material_id: Optional[str] = None   # optional link to WMS material (rahaza_materials)
    model_id: Optional[str] = None      # MKT-2: FK ke rahaza_models (divalidasi bila diisi)
    variant_id: Optional[str] = None    # Fase 3b: FK ke rahaza_model_variants (link stok Toko<->FG)
    platform_url: Optional[str] = ''
    images: Optional[List[str]] = []
    tags: Optional[List[str]] = []
    weight_gram: Optional[float] = Field(default=0, ge=0)
    category: Optional[str] = ''
    variant_info: Optional[str] = ''    # e.g. "Warna: Merah, Size: L"
    is_active: Optional[bool] = True


class CatalogItemUpdate(BaseModel):
    model_id: Optional[str] = None      # MKT-2: FK ke rahaza_models
    variant_id: Optional[str] = None    # Fase 3b: FK ke rahaza_model_variants
    sku: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = Field(default=None, ge=0)
    original_price: Optional[float] = Field(default=None, ge=0)
    platform_price: Optional[float] = None
    harga_jual: Optional[float] = Field(default=None, ge=0)
    harga_coret: Optional[float] = Field(default=None, ge=0)
    harga_original: Optional[float] = Field(default=None, ge=0)
    hpp: Optional[float] = Field(default=None, ge=0)
    stock_quantity: Optional[float] = Field(default=None, ge=0)
    stock_alert_threshold: Optional[float] = Field(default=None, ge=0)
    material_id: Optional[str] = None
    platform_url: Optional[str] = None
    images: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    weight_gram: Optional[float] = Field(default=None, ge=0)
    category: Optional[str] = None
    variant_info: Optional[str] = None
    is_active: Optional[bool] = None


class StockUpdateBody(BaseModel):
    stock_quantity: float = Field(ge=0)
    notes: Optional[str] = ''


class CatalogItemFromFG(BaseModel):
    """Create catalog item by picking from FG master (rahaza_materials, type='fg').
    Backend auto-fills SKU/name/color/category from FG; user only sets selling price + URL.
    """
    fg_material_id: str  # UUID dari rahaza_materials
    price: float = Field(ge=0)                              # legacy selling price (=harga_jual)
    original_price: Optional[float] = Field(default=0, ge=0)       # legacy (=harga_coret)
    platform_price: Optional[float] = 0       # actual listed price
    harga_jual: Optional[float] = Field(default=None, ge=0)
    harga_coret: Optional[float] = Field(default=None, ge=0)
    harga_original: Optional[float] = Field(default=None, ge=0)
    platform_url: Optional[str] = ''
    images: Optional[List[str]] = []
    tags: Optional[List[str]] = []
    stock_alert_threshold: Optional[float] = Field(default=10, ge=0)
    description_override: Optional[str] = ''  # custom description (optional)


class BulkStockUpdate(BaseModel):
    updates: List[dict]   # [{ item_id, stock_quantity, notes }]


# ═══════════════════════════════════════════════════════════════════════════════

@router.post('/{catalog_id}/items', status_code=201)
async def add_catalog_item(catalog_id: str, data: CatalogItemCreate, request: Request):
    """Tambah item/produk ke dalam katalog.
    
    NOTE (Legacy mode): Untuk produk baru, prefer endpoint POST /items/from-fg
    yang link langsung ke master FG (rahaza_materials) untuk konsistensi data.
    """
    user = await require_auth(request)
    db = get_db()

    catalog = await db.marketing_catalogs.find_one({'id': catalog_id}, {'_id': 0})
    if not catalog:
        raise HTTPException(404, 'Katalog tidak ditemukan.')

    # Check SKU uniqueness within catalog
    existing_sku = await db.marketing_catalog_items.find_one({
        'catalog_id': catalog_id, 'sku': data.sku.strip().upper()
    })
    if existing_sku:
        raise HTTPException(409, f'SKU {data.sku} sudah ada dalam katalog ini.')

    stock_qty = float(data.stock_quantity or 0)
    threshold = float(data.stock_alert_threshold or 10)

    # MKT-2: validasi FK model RnD bila diisi
    if data.model_id:
        _mdl = await db.rahaza_models.find_one({'id': data.model_id, 'active': {'$ne': False}})
        if not _mdl:
            raise HTTPException(400, f"model_id '{data.model_id}' tidak valid (rahaza_models — MKT-2)")

    # Fase 3b: link ke varian produksi internal (rahaza_model_variants)
    variant_sku = ''
    variant_info_auto = ''
    if data.variant_id:
        _rv = await db.rahaza_model_variants.find_one({'id': data.variant_id, 'active': {'$ne': False}}, {'_id': 0})
        if not _rv:
            raise HTTPException(400, f"variant_id '{data.variant_id}' tidak valid (rahaza_model_variants — Fase 3b)")
        variant_sku = _rv.get('sku', '')
        variant_info_auto = f"Warna: {_rv.get('color_name', '')}, Size: {_rv.get('size_code', '')}"
        # auto-isi model_id & sku dari varian bila belum di-set manual
        if not data.model_id:
            data.model_id = _rv.get('model_id')
        if not (data.sku and data.sku.strip()):
            data.sku = variant_sku

    doc = {
        'id': _uid(),
        'catalog_id': catalog_id,
        'account_id': catalog.get('account_id', ''),
        'platform': catalog.get('platform', ''),
        'sku': _san(data.sku, 100).upper(),
        'name': _san(data.name, 200),
        'description': _san(data.description or '', 2000),
        'price': float(data.price or 0),
        'original_price': float(data.original_price or 0),
        'platform_price': float(data.platform_price or 0),
        'stock_quantity': stock_qty,
        'stock_alert_threshold': threshold,
        'stock_status': _stock_status(stock_qty, threshold),
        'material_id': data.material_id,
        'model_id': data.model_id,             # MKT-2: FK rahaza_models
        'variant_id': data.variant_id,         # Fase 3b: FK rahaza_model_variants
        'variant_sku': variant_sku,            # Fase 3b: SKU varian produksi (link stok FG)
        'fg_material_id': None,                # mark as legacy (no master link)
        'source': 'manual',                    # manual entry vs from_fg
        'platform_url': (data.platform_url or '').strip(),
        'images': data.images or [],
        'tags': data.tags or [],
        'weight_gram': float(data.weight_gram or 0),
        'category': _san(data.category or '', 100),
        'variant_info': _san(data.variant_info or variant_info_auto or '', 200),
        'is_active': data.is_active,
        'last_stock_sync': None,
        'created_at': _now(),
        'updated_at': _now(),
        'created_by': user.get('id', ''),
    }
    # KEPUTUSAN #2 — normalisasi & simpan field harga terpisah (+ legacy sync)
    doc.update(_pricing_write_fields(data.dict()))
    doc.setdefault('harga_original', float(data.harga_original or 0) if data.harga_original is not None else 0.0)
    doc.setdefault('hpp', float(data.hpp or 0) if data.hpp is not None else 0.0)

    await db.marketing_catalog_items.insert_one(doc)
    await _refresh_catalog_stats(db, catalog_id)
    return {'ok': True, 'item': _s(doc)}


# ═══════════════════════════════════════════════════════════════════════════════
# PHOTO UPLOAD — Catalog item photos (Phase B Toko Cutover)
# ═══════════════════════════════════════════════════════════════════════════════

class RemovePhotoIn(BaseModel):
    url: str


@router.post('/{catalog_id}/items/{item_id}/photos')
async def upload_catalog_item_photo(
    catalog_id: str,
    item_id: str,
    file: UploadFile = File(...),
    request: Request = None,
):
    """Upload a photo for a catalog item. Saves under /app/uploads/products/{item_id}/
    and appends URL to both `images[]` (marketing native) and `photos[]` (legacy)
    arrays for backwards compatibility.
    """
    await require_auth(request)
    db = get_db()
    item = await db.marketing_catalog_items.find_one(
        {'id': item_id, 'catalog_id': catalog_id}, {'_id': 0}
    )
    if not item:
        raise HTTPException(404, 'Item tidak ditemukan dalam katalog ini.')

    if file.content_type not in ALLOWED_MIMES:
        raise HTTPException(415, f'Hanya {sorted(ALLOWED_MIMES)} diizinkan')
    data = await file.read()
    if len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(413, 'Ukuran file > 5MB')
    if len(data) < 50:
        raise HTTPException(400, 'File terlalu kecil (min 50 bytes)')

    ext = 'jpg'
    if file.filename and '.' in file.filename:
        candidate = file.filename.rsplit('.', 1)[-1].lower()
        candidate = re.sub(r'[^a-z0-9]', '', candidate)
        if candidate in ALLOWED_EXT:
            ext = candidate
    folder = PRODUCT_UPLOAD_ROOT / item_id
    folder.mkdir(parents=True, exist_ok=True)
    fname = f'{uuid.uuid4().hex}.{ext}'
    with open(folder / fname, 'wb') as f:
        f.write(data)
    url = f'/api/uploads/products/{item_id}/{fname}'

    # Dual-write to images[] (marketing native) and photos[] (legacy back-compat)
    await db.marketing_catalog_items.update_one(
        {'id': item_id, 'catalog_id': catalog_id},
        {
            '$addToSet': {'images': url, 'photos': url},
            '$set': {'updated_at': _now()},
        },
    )
    return {'ok': True, 'url': url, 'size': len(data)}


@router.post('/{catalog_id}/items/{item_id}/photos/remove')
async def remove_catalog_item_photo(
    catalog_id: str,
    item_id: str,
    payload: RemovePhotoIn,
    request: Request,
):
    """Remove a photo URL from a catalog item. Pulls from both `images[]` and
    `photos[]` arrays and best-effort deletes the underlying file.
    """
    await require_auth(request)
    db = get_db()
    item = await db.marketing_catalog_items.find_one(
        {'id': item_id, 'catalog_id': catalog_id}, {'_id': 0}
    )
    if not item:
        raise HTTPException(404, 'Item tidak ditemukan.')

    await db.marketing_catalog_items.update_one(
        {'id': item_id, 'catalog_id': catalog_id},
        {
            '$pull': {'images': payload.url, 'photos': payload.url},
            '$set': {'updated_at': _now()},
        },
    )

    # Best-effort file delete
    try:
        if payload.url.startswith('/api/uploads/products/'):
            rel = payload.url.replace('/api/uploads/products/', '')
            fp = PRODUCT_UPLOAD_ROOT / rel
            if fp.exists() and fp.is_file():
                os.unlink(fp)
    except Exception:
        logging.getLogger(__name__).debug("suppressed exception", exc_info=True)

    return {'ok': True, 'message': 'Foto dihapus'}


# ═══════════════════════════════════════════════════════════════════════════════
# FG MASTER INTEGRATION — Item creation from FG (catalog-scoped routes)
# ═══════════════════════════════════════════════════════════════════════════════

@router.post('/{catalog_id}/items/from-fg', status_code=201)
async def add_catalog_item_from_fg(catalog_id: str, data: CatalogItemFromFG, request: Request):
    """Tambah catalog item dari master FG produk.
    
    Auto-fills SKU, name, description, weight, category, color, variant info from FG record.
    Stock quantity snapshot dari rahaza_material_stock (location default).
    User HANYA perlu set: selling price, original_price (optional), platform_url.
    """
    user = await require_auth(request)
    db = get_db()
    
    # Validate catalog exists
    catalog = await db.marketing_catalogs.find_one({'id': catalog_id}, {'_id': 0})
    if not catalog:
        raise HTTPException(404, 'Katalog tidak ditemukan.')
    
    # Validate FG material exists & is type='fg'
    fg = await db.rahaza_materials.find_one({'id': data.fg_material_id}, {'_id': 0})
    if not fg:
        raise HTTPException(404, 'FG produk tidak ditemukan di master inventory.')
    if fg.get('type') != 'fg':
        raise HTTPException(400, f"Material bukan tipe FG (tipe: {fg.get('type')}). Hanya Finished Goods yang bisa di-link ke catalog.")
    
    # Check if FG already in this catalog (prevent duplicate)
    existing = await db.marketing_catalog_items.find_one({
        'catalog_id': catalog_id,
        'fg_material_id': data.fg_material_id,
    })
    if existing:
        raise HTTPException(409, f"Produk '{fg.get('name')}' sudah ada di katalog ini.")
    
    # Get current stock from default location
    default_loc = await db.rahaza_locations.find_one({'active': True}, {'_id': 0})
    loc_id = default_loc['id'] if default_loc else None
    stock_qty = 0.0
    if loc_id:
        stock_doc = await db.rahaza_material_stock.find_one(
            {'material_id': fg.get('id'), 'location_id': loc_id}, {'_id': 0}
        )
        stock_qty = float(stock_doc.get('qty', 0)) if stock_doc else 0.0
    
    threshold = float(data.stock_alert_threshold or 10)
    
    # Auto-fill from FG record
    fg_code = fg.get('code') or ''
    fg_name = fg.get('name') or ''
    fg_color = fg.get('color') or ''
    # FASE 6.6-B: baca kanonik `composition` dulu, fallback legacy `yarn_type`
    fg_yarn = _mf.read_field(fg, 'composition', '') or ''
    fg_unit = fg.get('unit') or 'pcs'
    fg_category = fg.get('category') or fg.get('subtype') or ''
    
    # Build variant info from FG attributes
    variant_parts = []
    if fg_color:
        variant_parts.append(f"Warna: {fg_color}")
    if fg_yarn:
        variant_parts.append(f"Material: {fg_yarn}")
    variant_info = ' | '.join(variant_parts)
    
    description = (data.description_override or '').strip()
    if not description:
        description = f"FG: {fg_name}"
        if variant_info:
            description += f" ({variant_info})"
    
    doc = {
        'id': _uid(),
        'catalog_id': catalog_id,
        'account_id': catalog.get('account_id', ''),
        'platform': catalog.get('platform', ''),
        # Master FG references
        'fg_material_id': fg.get('id'),
        'material_id': fg.get('id'),       # legacy alias for backward compat
        'fg_code': fg_code,
        'fg_name': fg_name,
        'fg_color': fg_color,
        'source': 'from_fg',
        # Display fields (denormalized for performance)
        'sku': fg_code.upper(),
        'name': fg_name,
        'description': _san(description, 2000),
        'category': fg_category,
        'variant_info': variant_info,
        'unit': fg_unit,
        # Pricing
        'price': float(data.price or 0),
        'original_price': float(data.original_price or 0),
        'platform_price': float(data.platform_price or 0),
        # Stock (snapshot from master)
        'stock_quantity': stock_qty,
        'stock_alert_threshold': threshold,
        'stock_status': _stock_status(stock_qty, threshold),
        'stock_location_id': loc_id,
        'last_stock_sync': _now(),
        # Marketing fields
        'platform_url': (data.platform_url or '').strip(),
        'images': data.images or [],
        'tags': data.tags or [],
        'weight_gram': float(fg.get('weight_gram', 0)) if fg.get('weight_gram') else 0,
        'is_active': True,
        'created_at': _now(),
        'updated_at': _now(),
        'created_by': user.get('id', ''),
    }
    
    # KEPUTUSAN #2 — HPP di-snapshot dari master FG (rahaza_materials.hpp), lalu
    # akan di-refresh otomatis oleh propagasi RnD. Harga jual/coret/original dari input.
    doc['hpp'] = float(fg.get('hpp') or 0)
    doc['harga_original'] = float(data.harga_original or 0) if data.harga_original is not None else 0.0
    doc.update(_pricing_write_fields(data.dict()))

    await db.marketing_catalog_items.insert_one(doc)
    await _refresh_catalog_stats(db, catalog_id)
    
    return {'ok': True, 'item': _s(doc), 'message': f"Produk '{fg_name}' berhasil ditambahkan ke katalog dari master FG"}


@router.get('/{catalog_id}/items/{item_id}/fg-stock')
async def peek_item_fg_stock(catalog_id: str, item_id: str, request: Request):
    """Fase 3b: Intip stok FG live untuk item Toko (read-only, tanpa mengubah stok).

    Dipakai UI untuk menampilkan 'Stok FG tersedia' di samping item yang tertaut varian.
    """
    await require_auth(request)
    db = get_db()
    item = await db.marketing_catalog_items.find_one({'id': item_id, 'catalog_id': catalog_id}, {'_id': 0})
    if not item:
        raise HTTPException(404, 'Item tidak ditemukan.')
    res = await resolve_item_fg_stock(db, item)
    return {
        'ok': True,
        'item_id': item_id,
        'variant_id': item.get('variant_id'),
        'variant_sku': item.get('variant_sku') or '',
        'link_type': res['link_type'],
        'found': res['found'],
        'fg_material_id': res['fg_material_id'],
        'fg_code': res['fg_code'],
        'onhand': res['onhand'],
        'reserved': res['reserved'],
        'available': res['available'],
        'catalog_stock_quantity': float(item.get('stock_quantity', 0) or 0),
        'in_sync': res['found'] and abs(float(item.get('stock_quantity', 0) or 0) - res['available']) < 0.001,
    }


@router.put('/{catalog_id}/items/{item_id}/sync-fg-stock')
async def sync_item_stock_from_fg(catalog_id: str, item_id: str, request: Request):
    """Manual sync stok single catalog item dari master FG (auto-override, KEPUTUSAN 2b).

    Prioritas tautan (Fase 3b):
      1. variant_sku  → cocokkan by SKU ke master FG (jalur varian internal).
      2. fg_material_id / material_id → langsung by material FG.
    stock_quantity item Toko di-set = available FG (onhand - reserved).
    """
    await require_auth(request)
    db = get_db()

    item = await db.marketing_catalog_items.find_one({'id': item_id, 'catalog_id': catalog_id}, {'_id': 0})
    if not item:
        raise HTTPException(404, 'Item tidak ditemukan.')

    res = await _apply_fg_stock_sync(db, item)
    await _refresh_catalog_stats(db, catalog_id)

    return {
        'ok': True,
        'stock_quantity': res['new_stock'],
        'stock_status': res['stock_status'],
        'link_type': res['link_type'],
        'fg_material_id': res['fg_material_id'],
        'fg_code': res['fg_code'],
        'fg_onhand': res['onhand'],
        'fg_reserved': res['reserved'],
        'fg_available': res['available'],
    }



async def _resolve_rnd_hpp(db, item: dict):
    """Ambil HPP terkini dari RnD utk sebuah item katalog (KEP#2, item#1 refresh).

    Prioritas sumber tautan:
      1. item.model_id  → rahaza_models.hpp (di-set oleh propagasi RnD)
      2. item.fg_material_id / material_id → rahaza_materials.hpp
    Return: (hpp: float|None, source: str). None = tidak ada sumber tertaut.
    """
    model_id = item.get('model_id')
    if model_id:
        m = await db.rahaza_models.find_one({'id': model_id}, {'_id': 0, 'hpp': 1})
        if m and m.get('hpp') is not None:
            return float(m.get('hpp') or 0), 'rahaza_models'
    fg_id = item.get('fg_material_id') or item.get('material_id')
    if fg_id:
        f = await db.rahaza_materials.find_one({'id': fg_id}, {'_id': 0, 'hpp': 1})
        if f and f.get('hpp') is not None:
            return float(f.get('hpp') or 0), 'rahaza_materials'
    return None, 'no_source'


@router.post('/{catalog_id}/items/{item_id}/refresh-hpp')
async def refresh_item_hpp(catalog_id: str, item_id: str, request: Request):
    """Tarik-ulang HPP satu item katalog dari RnD (per-item)."""
    await require_auth(request)
    db = get_db()
    item = await db.marketing_catalog_items.find_one({'id': item_id, 'catalog_id': catalog_id}, {'_id': 0})
    if not item:
        raise HTTPException(404, 'Item tidak ditemukan.')
    hpp, source = await _resolve_rnd_hpp(db, item)
    if hpp is None:
        raise HTTPException(400, 'Item belum tertaut ke Model/FG dari RnD — HPP tidak bisa di-refresh otomatis.')
    await db.marketing_catalog_items.update_one(
        {'id': item_id},
        {'$set': {'hpp': hpp, 'hpp_source': 'rnd', 'hpp_updated_at': _now(), 'updated_at': _now()}},
    )
    item['hpp'] = hpp
    item['hpp_source'] = 'rnd'
    return {'ok': True, 'hpp': hpp, 'source': source, 'item': _s(item)}


@router.post('/{catalog_id}/refresh-hpp')
async def refresh_catalog_hpp_bulk(catalog_id: str, request: Request):
    """Tarik-ulang HPP SEMUA item katalog yang tertaut ke RnD (bulk)."""
    await require_auth(request)
    db = get_db()
    catalog = await db.marketing_catalogs.find_one({'id': catalog_id}, {'_id': 0, 'id': 1})
    if not catalog:
        raise HTTPException(404, 'Katalog tidak ditemukan.')
    items = await db.marketing_catalog_items.find({'catalog_id': catalog_id}, {'_id': 0}).to_list(5000)
    updated, skipped = 0, 0
    now = _now()
    for it in items:
        hpp, source = await _resolve_rnd_hpp(db, it)
        if hpp is None:
            skipped += 1
            continue
        await db.marketing_catalog_items.update_one(
            {'id': it['id']},
            {'$set': {'hpp': hpp, 'hpp_source': 'rnd', 'hpp_updated_at': now, 'updated_at': now}},
        )
        updated += 1
    return {'ok': True, 'updated': updated, 'skipped_no_source': skipped, 'total': len(items)}


@router.get('/{catalog_id}/items')
async def list_catalog_items(
    catalog_id: str,
    request: Request,
    search: Optional[str] = None,
    status: Optional[str] = None,  # in_stock | low_stock | out_of_stock
    category: Optional[str] = None,
    is_active: Optional[bool] = None,
    skip: int = 0,
    limit: int = 100,
):
    """List item dalam katalog dengan filter."""
    await require_auth(request)
    db = get_db()

    q: dict = {'catalog_id': catalog_id}
    if search:
        q['$or'] = [
            {'name': {'$regex': search, '$options': 'i'}},
            {'sku': {'$regex': search, '$options': 'i'}},
            {'tags': {'$regex': search, '$options': 'i'}},
        ]
    if status:
        q['stock_status'] = status
    if category:
        q['category'] = {'$regex': category, '$options': 'i'}
    if is_active is not None:
        q['is_active'] = is_active

    total = await db.marketing_catalog_items.count_documents(q)
    docs = await db.marketing_catalog_items.find(q, {'_id': 0}).sort('name', 1).skip(skip).limit(limit).to_list(500)
    return {'ok': True, 'items': [_s(d) for d in docs], 'total': total}


@router.put('/{catalog_id}/items/{item_id}')
async def update_catalog_item(catalog_id: str, item_id: str, data: CatalogItemUpdate, request: Request):
    """Update item data (termasuk harga, stok, dll)."""
    user = await require_auth(request)
    db = get_db()

    item = await db.marketing_catalog_items.find_one(
        {'id': item_id, 'catalog_id': catalog_id}, {'_id': 0}
    )
    if not item:
        raise HTTPException(404, 'Item tidak ditemukan.')

    patch = {k: v for k, v in data.dict().items() if v is not None}
    # KEPUTUSAN #2 — normalisasi harga (kanonik + legacy sync)
    patch.update(_pricing_write_fields(data.dict()))
    if patch.get('model_id'):
        _mdl = await db.rahaza_models.find_one({'id': patch['model_id'], 'active': {'$ne': False}})
        if not _mdl:
            raise HTTPException(400, f"model_id '{patch['model_id']}' tidak valid (rahaza_models — MKT-2)")
    # Fase 3b: validasi & auto-fill dari varian produksi internal
    if patch.get('variant_id'):
        _rv = await db.rahaza_model_variants.find_one({'id': patch['variant_id'], 'active': {'$ne': False}}, {'_id': 0})
        if not _rv:
            raise HTTPException(400, f"variant_id '{patch['variant_id']}' tidak valid (rahaza_model_variants — Fase 3b)")
        patch['variant_sku'] = _rv.get('sku', '')
        patch.setdefault('model_id', _rv.get('model_id'))
        patch.setdefault('variant_info', f"Warna: {_rv.get('color_name', '')}, Size: {_rv.get('size_code', '')}")
        if not patch.get('sku'):
            patch['sku'] = _rv.get('sku', '')
    if 'sku' in patch:
        patch['sku'] = patch['sku'].strip().upper()
    if 'name' in patch:
        patch['name'] = patch['name'].strip()

    # Recompute stock_status if stock fields changed
    new_qty = patch.get('stock_quantity', item.get('stock_quantity', 0))
    new_thresh = patch.get('stock_alert_threshold', item.get('stock_alert_threshold', 10))
    patch['stock_status'] = _stock_status(float(new_qty), float(new_thresh))
    patch['updated_at'] = _now()
    patch['updated_by'] = user.get('id', '')

    await db.marketing_catalog_items.update_one({'id': item_id}, {'$set': patch})
    await _refresh_catalog_stats(db, catalog_id)

    updated = await db.marketing_catalog_items.find_one({'id': item_id}, {'_id': 0})
    return {'ok': True, 'item': _s(updated)}


@router.delete('/{catalog_id}/items/{item_id}')
async def delete_catalog_item(catalog_id: str, item_id: str, request: Request):
    """Hapus item dari katalog."""
    await require_auth(request)
    db = get_db()

    res = await db.marketing_catalog_items.delete_one({'id': item_id, 'catalog_id': catalog_id})
    if res.deleted_count == 0:
        raise HTTPException(404, 'Item tidak ditemukan.')
    await _refresh_catalog_stats(db, catalog_id)
    return {'ok': True, 'message': 'Item dihapus.'}


# ═══════════════════════════════════════════════════════════════════════════════
# STOCK MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

