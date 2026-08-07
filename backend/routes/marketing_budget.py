"""
marketing_budget.py — Budget Marketing per Toko × Bulan × Kategori (KEPUTUSAN #5).

Tiap akun toko punya rencana budget per bulan yang dipecah per KATEGORI alokasi:
  ads · kol · livehost · sample · diskon
lalu di-compare dengan realisasi (spend) + ROI vs sales.

Sumber spend (grounded ke kode):
  - Ads / Sample / Diskon : input manual → marketing_spend_entries (KEPUTUSAN #5, ads=manual).
  - LiveHost : REAL → Σ total_pay shift 'calculated' (marketing_livehost_shifts) utk host
               yang assigned ke akun (marketing_livehosts.assigned_account_ids) + entri manual.
  - KOL/Kreator : KONFIGURABEL (KEPUTUSAN #5 = kombinasi) → fee (fixed rate) dan/atau
               komisi (% dari sales). Cost = Σ per kreator assigned ke akun, dihitung dari
               marketing_creator_sessions.revenue pada periode + entri manual.

Sales (ROI) : Σ marketing_sales_data.metrics.revenue (revenue_type='total') utk akun+periode.

Endpoints (prefix /api/marketing/budget):
  GET  /                         ?account_id=&period=YYYY-MM   → rencana budget
  PUT  /                         upsert rencana budget
  POST /spend                    catat spend manual
  GET  /spend                    ?account_id=&period=&category=
  DELETE /spend/{sid}
  GET  /kol-cost                 list kreator + cost_config
  GET  /kol-cost/{creator_id}
  PUT  /kol-cost/{creator_id}    set cost_config {fee_type, fixed_fee, commission_pct}
  GET  /summary                  ?account_id=&period=  → budget vs spend per kategori + ROI
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel, Field
from database import get_db
from auth import require_auth, serialize_doc

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/api/marketing/budget', tags=['Marketing-Budget'])

CATEGORIES = ['ads', 'kol', 'livehost', 'sample', 'diskon']
FEE_TYPES = ['none', 'fixed', 'commission', 'both']


def _uid():
    return str(uuid.uuid4())


def _now():
    return datetime.now(timezone.utc)


def _num(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(d)


def _empty_cat(default=0.0):
    return {c: float(default) for c in CATEGORIES}


# ── Pydantic ─────────────────────────────────────────────────────────────────
class BudgetUpsert(BaseModel):
    account_id: str
    period: str = Field(..., description="YYYY-MM")
    budget_by_category: dict = Field(default_factory=dict)
    notes: Optional[str] = ''


class SpendEntry(BaseModel):
    account_id: str
    period: str = Field(..., description="YYYY-MM")
    category: str
    amount: float = Field(..., ge=0)
    description: Optional[str] = ''
    ref_type: Optional[str] = ''   # e.g. 'ads_campaign', 'sample', 'promo'
    ref_id: Optional[str] = ''
    spend_date: Optional[str] = ''  # YYYY-MM-DD


class KolCostConfig(BaseModel):
    fee_type: str = Field('none', description="none | fixed | commission | both")
    fixed_fee: float = Field(0, ge=0)
    commission_pct: float = Field(0, ge=0, le=100)


def _valid_period(p: str):
    try:
        datetime.strptime(p, "%Y-%m")
    except Exception:
        raise HTTPException(400, "period harus format YYYY-MM")


# ── Cost helpers ───────────────────────────────────────────────────────────────
def _creator_cost(config: dict, revenue: float) -> float:
    """Hitung biaya kreator dari config (kombinasi fee + komisi)."""
    if not config:
        return 0.0
    ft = (config.get('fee_type') or 'none').lower()
    fixed = _num(config.get('fixed_fee'), 0)
    pct = _num(config.get('commission_pct'), 0)
    cost = 0.0
    if ft in ('fixed', 'both'):
        cost += fixed
    if ft in ('commission', 'both'):
        cost += revenue * pct / 100.0
    return round(cost, 2)


async def _creator_revenue(db, creator_id: str, account_id: str, period: str) -> float:
    rows = await db.marketing_creator_sessions.find(
        {'creator_id': creator_id, 'account_id': account_id,
         'date': {'$regex': f'^{period}'}},
        {'_id': 0, 'revenue': 1}
    ).to_list(2000)
    return round(sum(_num(r.get('revenue'), 0) for r in rows), 2)


async def _kol_auto_spend(db, account_id: str, period: str):
    """Biaya KOL otomatis: Σ kreator assigned ke akun × cost_config-nya."""
    creators = await db.marketing_kol_creators.find(
        {'assigned_account_ids': account_id}, {'_id': 0}
    ).to_list(500)
    total = 0.0
    detail = []
    for c in creators:
        cfg = c.get('cost_config') or {}
        if not cfg or (cfg.get('fee_type') or 'none') == 'none':
            continue
        rev = await _creator_revenue(db, c['id'], account_id, period)
        cost = _creator_cost(cfg, rev)
        if cost <= 0:
            continue
        total += cost
        detail.append({
            'creator_id': c['id'], 'creator_name': c.get('name', ''),
            'fee_type': cfg.get('fee_type'), 'fixed_fee': _num(cfg.get('fixed_fee'), 0),
            'commission_pct': _num(cfg.get('commission_pct'), 0),
            'revenue': rev, 'cost': cost,
        })
    return round(total, 2), detail


async def _livehost_auto_spend(db, account_id: str, period: str):
    """Biaya LiveHost REAL per akun (KEP#5, refinement item#2).

    Attribusi AKURAT berbasis `account_id` PER SHIFT (tiap shift LiveHost menyimpan
    account_id-nya sendiri — lih. marketing_livehost_shifts). Ini menggantikan cara
    lama via host.assigned_account_ids yang bisa dobel-hitung antar-akun bila 1 host
    ditugaskan ke banyak akun. Hanya shift 'calculated' yang dihitung.
    """
    shifts = await db.marketing_livehost_shifts.find(
        {'account_id': account_id, 'date': {'$regex': f'^{period}'},
         'payment_status': 'calculated'},
        {'_id': 0, 'host_id': 1, 'total_pay': 1, 'date': 1}
    ).to_list(10000)
    total = round(sum(_num(s.get('total_pay'), 0) for s in shifts), 2)
    by_host = {}
    for s in shifts:
        by_host[s.get('host_id')] = by_host.get(s.get('host_id'), 0) + _num(s.get('total_pay'), 0)
    detail = [{'host_id': hid, 'total_pay': round(v, 2)} for hid, v in by_host.items()]
    return total, detail


async def _manual_spend(db, account_id: str, period: str):
    rows = await db.marketing_spend_entries.find(
        {'account_id': account_id, 'period': period}, {'_id': 0}
    ).to_list(5000)
    by_cat = _empty_cat()
    for r in rows:
        cat = r.get('category')
        if cat in by_cat:
            by_cat[cat] += _num(r.get('amount'), 0)
    return {k: round(v, 2) for k, v in by_cat.items()}


async def _sales_revenue(db, account_id: str, period: str) -> float:
    """Total sales (revenue) akun pada periode utk ROI.

    Robust ke dua bentuk dokumen marketing_sales_data:
      - entry endpoint resmi: {revenue_type:'total'|'live', metrics:{revenue}}
      - seed/demo lama: {gross_sales, net_sales} tanpa revenue_type
    Entri 'live' di-skip agar tidak dobel-hitung dengan 'total'.
    """
    rows = await db.marketing_sales_data.find(
        {'account_id': account_id, 'date': {'$regex': f'^{period}'}},
        {'_id': 0, 'metrics': 1, 'revenue': 1, 'revenue_type': 1,
         'net_sales': 1, 'gross_sales': 1}
    ).to_list(10000)
    tot = 0.0
    for r in rows:
        if (r.get('revenue_type') or '') == 'live':
            continue
        m = r.get('metrics') or {}
        val = (m.get('revenue') if m.get('revenue') is not None else
               r.get('revenue') if r.get('revenue') is not None else
               r.get('net_sales') if r.get('net_sales') is not None else
               r.get('gross_sales'))
        tot += _num(val, 0)
    return round(tot, 2)


# ── BUDGET PLAN ────────────────────────────────────────────────────────────────
@router.get('')
async def get_budget(request: Request, account_id: str = Query(...), period: str = Query(...)):
    await require_auth(request)
    _valid_period(period)
    db = get_db()
    doc = await db.marketing_budgets.find_one({'account_id': account_id, 'period': period}, {'_id': 0})
    if not doc:
        return {'account_id': account_id, 'period': period,
                'budget_by_category': _empty_cat(), 'total_budget': 0.0, 'exists': False}
    bbc = {**_empty_cat(), **(doc.get('budget_by_category') or {})}
    doc['budget_by_category'] = {k: round(_num(v), 2) for k, v in bbc.items() if k in CATEGORIES}
    doc['total_budget'] = round(sum(doc['budget_by_category'].values()), 2)
    doc['exists'] = True
    return serialize_doc(doc)


@router.put('')
async def upsert_budget(data: BudgetUpsert, request: Request):
    user = await require_auth(request)
    _valid_period(data.period)
    db = get_db()
    acc = await db.marketing_platform_accounts.find_one({'id': data.account_id}, {'_id': 0})
    if not acc:
        raise HTTPException(404, 'Akun platform tidak ditemukan.')
    bbc = {c: round(_num((data.budget_by_category or {}).get(c), 0), 2) for c in CATEGORIES}
    now = _now()
    await db.marketing_budgets.update_one(
        {'account_id': data.account_id, 'period': data.period},
        {'$set': {'budget_by_category': bbc, 'notes': data.notes or '',
                  'account_name': acc.get('account_name', ''), 'updated_at': now,
                  'updated_by': user.get('id', '')},
         '$setOnInsert': {'id': _uid(), 'account_id': data.account_id,
                          'period': data.period, 'created_at': now}},
        upsert=True,
    )
    doc = await db.marketing_budgets.find_one({'account_id': data.account_id, 'period': data.period}, {'_id': 0})
    doc['total_budget'] = round(sum(bbc.values()), 2)
    return serialize_doc(doc)


# ── SPEND ENTRIES (manual) ──────────────────────────────────────────────────────
@router.post('/spend')
async def add_spend(data: SpendEntry, request: Request):
    user = await require_auth(request)
    _valid_period(data.period)
    if data.category not in CATEGORIES:
        raise HTTPException(400, f"category harus salah satu: {', '.join(CATEGORIES)}")
    db = get_db()
    doc = {
        'id': _uid(), 'account_id': data.account_id, 'period': data.period,
        'category': data.category, 'amount': round(_num(data.amount), 2),
        'description': (data.description or '')[:500], 'ref_type': data.ref_type or '',
        'ref_id': data.ref_id or '', 'spend_date': data.spend_date or '',
        'source': 'manual', 'created_at': _now(), 'created_by': user.get('id', ''),
    }
    await db.marketing_spend_entries.insert_one(doc)
    return {'ok': True, 'entry': serialize_doc(doc)}


@router.get('/spend')
async def list_spend(request: Request, account_id: str = Query(...), period: str = Query(...),
                     category: Optional[str] = None):
    await require_auth(request)
    db = get_db()
    q = {'account_id': account_id, 'period': period}
    if category:
        q['category'] = category
    rows = await db.marketing_spend_entries.find(q, {'_id': 0}).sort('created_at', -1).to_list(2000)
    return {'ok': True, 'entries': [serialize_doc(r) for r in rows], 'total': len(rows)}


@router.delete('/spend/{sid}')
async def delete_spend(sid: str, request: Request):
    await require_auth(request)
    db = get_db()
    res = await db.marketing_spend_entries.delete_one({'id': sid})
    if res.deleted_count == 0:
        raise HTTPException(404, 'Spend entry tidak ditemukan.')
    return {'ok': True}


# ── KOL COST CONFIG ──────────────────────────────────────────────────────────────
@router.get('/kol-cost')
async def list_kol_cost(request: Request, account_id: Optional[str] = None):
    await require_auth(request)
    db = get_db()
    q = {}
    if account_id:
        q['assigned_account_ids'] = account_id
    rows = await db.marketing_kol_creators.find(q, {'_id': 0}).to_list(500)
    out = []
    for c in rows:
        out.append({
            'creator_id': c['id'], 'name': c.get('name', ''),
            'creator_code': c.get('creator_code', ''),
            'assigned_account_ids': c.get('assigned_account_ids', []),
            'cost_config': c.get('cost_config') or {'fee_type': 'none', 'fixed_fee': 0, 'commission_pct': 0},
        })
    return {'ok': True, 'creators': out, 'total': len(out)}


@router.get('/kol-cost/{creator_id}')
async def get_kol_cost(creator_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    c = await db.marketing_kol_creators.find_one({'id': creator_id}, {'_id': 0})
    if not c:
        raise HTTPException(404, 'Kreator tidak ditemukan.')
    return {'creator_id': creator_id, 'name': c.get('name', ''),
            'cost_config': c.get('cost_config') or {'fee_type': 'none', 'fixed_fee': 0, 'commission_pct': 0}}


@router.put('/kol-cost/{creator_id}')
async def set_kol_cost(creator_id: str, data: KolCostConfig, request: Request):
    await require_auth(request)
    if data.fee_type not in FEE_TYPES:
        raise HTTPException(400, f"fee_type harus salah satu: {', '.join(FEE_TYPES)}")
    db = get_db()
    c = await db.marketing_kol_creators.find_one({'id': creator_id}, {'_id': 0})
    if not c:
        raise HTTPException(404, 'Kreator tidak ditemukan.')
    cfg = {'fee_type': data.fee_type, 'fixed_fee': round(_num(data.fixed_fee), 2),
           'commission_pct': round(_num(data.commission_pct), 2)}
    await db.marketing_kol_creators.update_one(
        {'id': creator_id}, {'$set': {'cost_config': cfg, 'updated_at': _now()}}
    )
    return {'ok': True, 'creator_id': creator_id, 'cost_config': cfg}


# ── SUMMARY (budget vs spend + ROI) ──────────────────────────────────────────────
@router.get('/summary')
async def budget_summary(request: Request, account_id: str = Query(...), period: str = Query(...)):
    await require_auth(request)
    _valid_period(period)
    db = get_db()

    budget_doc = await db.marketing_budgets.find_one({'account_id': account_id, 'period': period}, {'_id': 0})
    budget = {**_empty_cat(), **((budget_doc or {}).get('budget_by_category') or {})}

    manual = await _manual_spend(db, account_id, period)
    kol_auto, kol_detail = await _kol_auto_spend(db, account_id, period)
    lh_auto, lh_detail = await _livehost_auto_spend(db, account_id, period)

    spend = _empty_cat()
    for c in CATEGORIES:
        spend[c] = manual.get(c, 0.0)
    spend['kol'] = round(spend['kol'] + kol_auto, 2)
    spend['livehost'] = round(spend['livehost'] + lh_auto, 2)

    categories = []
    total_budget = total_spend = 0.0
    for c in CATEGORIES:
        b = round(_num(budget.get(c)), 2)
        s = round(_num(spend.get(c)), 2)
        remaining = round(b - s, 2)
        pct = round((s / b * 100) if b > 0 else (0 if s == 0 else 100), 2)
        categories.append({
            'category': c, 'budget': b, 'spend': s, 'remaining': remaining,
            'used_pct': pct, 'status': 'over' if s > b else 'under',
        })
        total_budget += b
        total_spend += s

    sales = await _sales_revenue(db, account_id, period)
    total_budget = round(total_budget, 2)
    total_spend = round(total_spend, 2)
    roi_pct = round(((sales - total_spend) / total_spend * 100) if total_spend > 0 else 0, 2)
    spend_of_sales_pct = round((total_spend / sales * 100) if sales > 0 else 0, 2)

    return {
        'account_id': account_id, 'period': period,
        'categories': categories,
        'total_budget': total_budget, 'total_spend': total_spend,
        'total_remaining': round(total_budget - total_spend, 2),
        'total_used_pct': round((total_spend / total_budget * 100) if total_budget > 0 else 0, 2),
        'sales': sales, 'roi_pct': roi_pct, 'spend_of_sales_pct': spend_of_sales_pct,
        'kol_detail': kol_detail, 'livehost_detail': lh_detail,
    }
