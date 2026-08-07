"""
Canonical SSOT for internal product VARIANT identity & Finished-Goods (FG) materialization.

Single source of truth (user decision 2026-07-22):
  - Variant SSOT   : rahaza_model_variants   (model x color x size)
  - Canonical SKU  : {MODEL_CODE}-{COLOR_CODE}-{SIZE_CODE}  (UPPERCASE, NO "FG-" prefix)
  - FG identity    : rahaza_materials (type='fg') with code == variant.sku
  - Physical stock : rahaza_material_stock (per material_id per location)
  - "All Size"     : size code 'ALLSIZE'. COLOR is ALWAYS required (3-part SKU).

This module is the ONLY place allowed to build internal variant SKUs and to create/link
FG materials, so production / warehouse / marketing never diverge on SKU convention.

Kept dependency-light (only db passed in) to avoid circular imports. The WMS pending-inbound
helper is imported lazily inside the function that needs it.
"""
import re
import uuid
from datetime import datetime, timezone


def _u(s) -> str:
    return str(s or "").strip().upper()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def build_variant_sku(model_code, color_code, size_code) -> str:
    """Canonical SKU = {MODEL}-{COLOR}-{SIZE} (uppercase, non-empty parts joined by '-')."""
    parts = [_u(model_code), _u(color_code), _u(size_code)]
    return "-".join(p for p in parts if p)


def variant_sku(variant: dict) -> str:
    """Resolve the canonical SKU for a rahaza_model_variants doc (prefer stored sku)."""
    sku = _u(variant.get("sku"))
    if sku:
        return sku
    return build_variant_sku(
        variant.get("model_code"), variant.get("color_code"), variant.get("size_code")
    )


def fg_display_name(variant: dict, model: dict = None) -> str:
    model = model or {}
    model_name = variant.get("model_name") or model.get("name") or variant.get("model_code") or ""
    color_name = variant.get("color_name") or variant.get("color") or ""
    size_code = variant.get("size_code") or ""
    extra = " · ".join([x for x in [color_name, size_code] if x])
    return f"{model_name} [{extra}]" if extra else model_name


def _variant_linkage(variant: dict, model: dict = None) -> dict:
    """Explicit linkage fields carried onto the FG material so downstream consumers
    (FG matrix, marketing, reports) never rely on fragile code-string parsing."""
    model = model or {}
    color_display = variant.get("color_name") or variant.get("color") or ""
    return {
        "model_id": variant.get("model_id"),
        "model_code": variant.get("model_code") or model.get("code"),
        "model_name": variant.get("model_name") or model.get("name"),
        "size_id": variant.get("size_id"),
        "size_code": variant.get("size_code"),
        "color_id": variant.get("color_id"),
        "color_code": variant.get("color_code"),
        # `color` is the axis/label field read by fg-matrix & marketing → use human name
        "color": color_display,
        "color_name": color_display,
        "color_hex": variant.get("color_hex"),
        "variant_id": variant.get("id"),
        "category": model.get("category", ""),
        "hpp": float(model.get("hpp") or 0),
    }


async def ensure_fg_material(db, variant: dict, user: dict = None) -> dict:
    """Idempotently create (or link) the FG rahaza_materials doc whose code == variant.sku.

    - If an FG already exists with the same code (case-insensitive), backfill any MISSING
      linkage fields (never overwrite an existing non-null value) and return it.
    - Otherwise create a new FG (type='fg', unit='pcs', active=True, stock stays 0 until receipt).

    Returns the FG material document.
    """
    sku = variant_sku(variant)
    if not sku:
        raise ValueError("Varian tidak punya SKU yang bisa diresolusi (model/warna/size kosong).")

    model = None
    if variant.get("model_id"):
        model = await db.rahaza_models.find_one({"id": variant["model_id"]}, {"_id": 0})

    linkage = _variant_linkage(variant, model)

    existing = await db.rahaza_materials.find_one(
        {"type": "fg", "code": {"$regex": f"^{re.escape(sku)}$", "$options": "i"}},
        {"_id": 0},
    )
    if existing:
        patch = {k: v for k, v in linkage.items()
                 if v not in (None, "") and not existing.get(k)}
        # Always ensure the canonical `sku` alias is present for by-sku resolvers.
        if not existing.get("sku"):
            patch["sku"] = sku
        if patch:
            patch["updated_at"] = now_utc()
            await db.rahaza_materials.update_one({"id": existing["id"]}, {"$set": patch})
            existing = {**existing, **patch}
        return existing

    doc = {
        "id": str(uuid.uuid4()),
        "code": sku,
        "sku": sku,
        "name": fg_display_name(variant, model),
        "type": "fg",
        "unit": "pcs",
        "active": True,
        "min_stock_qty": 0,
        "weight_gram": float((model or {}).get("weight_gram") or 0),
        "notes": "Auto-created from master variant (SSOT)",
        "created_at": now_utc(),
        "updated_at": now_utc(),
        **linkage,
    }
    await db.rahaza_materials.insert_one(doc)
    return doc


async def create_fg_pending_inbound_for_variant(
    db,
    variant: dict,
    qty,
    *,
    source_type: str,
    source_id: str,
    source_ref: str = "",
    user: dict = None,
    notes: str = "",
) -> dict:
    """Canonical physical FG receipt for internal production.

    1) Ensure the FG master exists (code == variant.sku).
    2) Create a WMS PENDING INBOUND (warehouse scan-in adds the physical stock) —
       keeps warehouse control while making the identity per-variant (color+size).

    Returns { fg, pending }.
    """
    qty = float(qty or 0)
    fg = await ensure_fg_material(db, variant, user=user)
    if qty <= 0:
        return {"fg": fg, "pending": None}

    from routes.wms_receiving import helper_create_pending_inbound_fg

    created_by = (user or {}).get("name") or (user or {}).get("email") or "production"
    pending = await helper_create_pending_inbound_fg(
        db,
        material_id=fg["id"],
        material_code=fg["code"],
        material_name=fg["name"],
        qty=qty,
        unit="pcs",
        source_type=source_type,
        source_id=source_id or "",
        source_ref=source_ref or "",
        notes=notes or f"Output produksi {qty:g} pcs — scan-in gudang diperlukan",
        created_by=created_by,
    )
    return {"fg": fg, "pending": pending}


async def resolve_variant(db, *, variant_id=None, sku=None,
                          model_id=None, color_id=None, size_id=None) -> dict:
    """Resolve a rahaza_model_variants doc by (priority) id → sku → (model,color,size)."""
    if variant_id:
        v = await db.rahaza_model_variants.find_one({"id": variant_id}, {"_id": 0})
        if v:
            return v
    if sku:
        v = await db.rahaza_model_variants.find_one(
            {"sku": {"$regex": f"^{re.escape(_u(sku))}$", "$options": "i"}}, {"_id": 0}
        )
        if v:
            return v
    if model_id and color_id and size_id:
        v = await db.rahaza_model_variants.find_one(
            {"model_id": model_id, "color_id": color_id, "size_id": size_id}, {"_id": 0}
        )
        if v:
            return v
    return None


# ══════════════════════ Master colors / sizes (idempotent get-or-create) ═══════
async def ensure_color(db, *, name=None, code=None, hex_val=None) -> dict:
    """Idempotent get-or-create a rahaza_colors doc.

    Resolution order: explicit code → exact name → create with a UNIQUE code.
    Unique-code creation prevents different color names that derive the same base
    code (e.g. 'Polcadot hitam' & 'Polcadot putih' → 'POL') from collapsing into one.
    """
    name = (name or "").strip()
    explicit = (code or "").strip().upper().replace(" ", "")
    # 1) explicit code match
    if explicit:
        ex = await db.rahaza_colors.find_one({"code": explicit}, {"_id": 0})
        if ex:
            return ex
    # 2) exact name match (case-insensitive)
    if name:
        byname = await db.rahaza_colors.find_one(
            {"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}}, {"_id": 0}
        )
        if byname:
            return byname
    if not name and not explicit:
        return None
    # 3) create with a unique code (append numeric suffix on collision)
    base = explicit or re.sub(r"[^A-Z0-9]", "", name.upper())[:3] or "CLR"
    final = base
    i = 1
    while await db.rahaza_colors.find_one({"code": final}):
        i += 1
        final = f"{base}{i}"[:10]
    doc = {
        "id": str(uuid.uuid4()), "code": final, "name": name or final,
        "hex": hex_val or "#CCCCCC", "order_seq": 50, "active": True,
        "created_at": now_utc(), "updated_at": now_utc(),
    }
    await db.rahaza_colors.insert_one(doc)
    return doc


async def ensure_size(db, *, code=None, name=None, order_seq=50) -> dict:
    """Idempotent get-or-create a rahaza_sizes doc (match by code)."""
    code = (code or "").strip().upper()
    if not code:
        return None
    existing = await db.rahaza_sizes.find_one({"code": code}, {"_id": 0})
    if existing:
        return existing
    doc = {
        "id": str(uuid.uuid4()), "code": code, "name": name or code,
        "order_seq": order_seq, "active": True,
        "created_at": now_utc(), "updated_at": now_utc(),
    }
    await db.rahaza_sizes.insert_one(doc)
    return doc


async def promote_rnd_variants_to_master(db, style: dict, model: dict, user: dict = None) -> dict:
    """GAP-3: From dewi_rnd_variants(style_id) create canonical rahaza_model_variants (+FG).

    RnD variant granularity = {color, sizes:[...]}. We explode color × size into the
    canonical SSOT (one SKU per color×size) and materialize an empty FG per SKU.
    Idempotent: existing (model,color,size) combos are skipped (FG still ensured).
    """
    rnd_vars = await db.dewi_rnd_variants.find({"style_id": style["id"]}, {"_id": 0}).to_list(2000)
    created, skipped = [], []
    for rv in rnd_vars:
        color = await ensure_color(
            db, name=rv.get("color"), code=rv.get("color_code"), hex_val=rv.get("color_hex")
        )
        if not color:
            continue
        sizes = rv.get("sizes") or []
        for s in sizes:
            scode = s if isinstance(s, str) else (s.get("code") or s.get("size") or "")
            size = await ensure_size(db, code=scode)
            if not size:
                continue
            dup = await db.rahaza_model_variants.find_one(
                {"model_id": model["id"], "color_id": color["id"], "size_id": size["id"]}, {"_id": 0}
            )
            if dup:
                await ensure_fg_material(db, dup, user=user)
                skipped.append(dup.get("sku"))
                continue
            sku = build_variant_sku(model["code"], color["code"], size["code"])
            vdoc = {
                "id": str(uuid.uuid4()),
                "model_id": model["id"], "model_code": model["code"], "model_name": model["name"],
                "size_id": size["id"], "size_code": size["code"],
                "color_id": color["id"], "color_code": color["code"],
                "color_name": color["name"], "color_hex": color.get("hex"),
                "sku": sku, "barcode": "", "notes": "Dari RnD promote (GAP-3)",
                "active": True, "created_at": now_utc(), "updated_at": now_utc(),
            }
            await db.rahaza_model_variants.insert_one(vdoc)
            await ensure_fg_material(db, vdoc, user=user)
            created.append(sku)
    return {"created": created, "skipped": skipped,
            "created_count": len(created), "skipped_count": len(skipped)}
