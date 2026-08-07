"""Tagihan CMT (AP jasa jahit) — endpoint BACA untuk pintu "Invoice".

Kenapa file ini ada (audit IA 2026-07-26, docs/PROPOSAL_IA_PRODUKSI.md §2):
    Alur uang produksi (internal maupun maklon) yang keluar ke vendor CMT SUDAH jalan
    di backend:
        Terima FG dari CMT (approve `cmt_receipts`)
          → production_maklon_bridge.mature_ap_from_cmt_receipt()
          → dokumen `dewi_cmt_payments` status draft
          → POST /api/dewi/maklon/finance/cmt-payments/{id}/post-ap
          → jurnal `cmt_ap_invoice` (Dr Biaya Jasa CMT / Cr Hutang Vendor)
    TAPI tidak ada satu pun layar yang menampilkan daftar `dewi_cmt_payments`
    (dibuktikan: nol pemanggil di frontend). Jadi tagihan yang sudah matang tidak
    pernah terlihat oleh pengguna.

File ini HANYA membaca + mengelompokkan. **Posting ke GL tetap memakai endpoint yang
sudah ada** (`/api/dewi/maklon/finance/cmt-payments/{id}/post-ap`) — sengaja tidak
dibuat handler kedua supaya logika jurnal tidak terduplikasi.

Pemisahan data (permintaan owner): Portal Produksi hanya melihat tagihan domain
INTERNAL, Portal Maklon hanya domain MAKLON.
    - punya `po_id`  → domain diambil dari `production_pos.business_type`
    - punya `job_ids`→ CMT-flow (DA menjahitkan produk DA sendiri) ⇒ INTERNAL
    - keduanya kosong→ 'unknown' (hanya muncul saat scope=all)
"""
from fastapi import APIRouter, Request, HTTPException

from database import get_db
from auth import require_auth, serialize_doc
from routes.production_rbac import deny_klien
from core.pagination import _paginate_params, _paginated_envelope

router = APIRouter(prefix="/api/production/cmt-billing", tags=["production-cmt-billing"])

# status yang dianggap masih menjadi kewajiban (outstanding)
_OPEN_STATUS = ('draft', 'submitted', 'approved', 'pending')


def _amount(p: dict) -> float:
    """Nilai tagihan bersih. Dokumen dari 2 penulis memakai nama field berbeda:
    bridge menulis `net_amount`, seeder CMT-flow menulis `total_amount`."""
    for k in ('net_amount', 'total_amount', 'subtotal'):
        v = p.get(k)
        if v not in (None, ''):
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
    return 0.0


async def _domain_map(db, payments: list) -> dict:
    """payment_id -> 'internal' | 'maklon' | 'unknown'."""
    po_ids = list({p.get('po_id') for p in payments if p.get('po_id')})
    bt_by_po = {}
    if po_ids:
        pos = await db.production_pos.find(
            {'id': {'$in': po_ids}}, {'_id': 0, 'id': 1, 'business_type': 1}
        ).to_list(None)
        bt_by_po = {p['id']: ('internal' if p.get('business_type') == 'internal' else 'maklon')
                    for p in pos}
    out = {}
    for p in payments:
        if p.get('po_id'):
            out[p['id']] = bt_by_po.get(p['po_id'], 'unknown')
        elif p.get('job_ids'):
            # CMT-flow: DA menjahitkan produk DA sendiri lewat mitra CMT ⇒ internal
            out[p['id']] = 'internal'
        else:
            out[p['id']] = 'unknown'
    return out


def _enrich(p: dict, domain: str) -> dict:
    return {
        **serialize_doc(p),
        'business_type': domain,
        'amount': _amount(p),
        'penalty': float(p.get('total_penalty', 0) or 0),
        'gl_posted': bool(p.get('gl_je_id')),
    }


async def _load(db, request: Request):
    """Ambil + filter + kelompokkan tagihan sesuai query param."""
    sp = request.query_params
    scope = (sp.get('business_type') or 'all').lower()
    if scope not in ('internal', 'maklon', 'all'):
        scope = 'all'

    q = {}
    if sp.get('status'):
        q['status'] = sp['status']
    if sp.get('partner_id'):
        q['cmt_partner_id'] = sp['partner_id']
    search = (sp.get('search') or '').strip()
    if search:
        q['$or'] = [
            {'payment_code': {'$regex': search, '$options': 'i'}},
            {'cmt_name': {'$regex': search, '$options': 'i'}},
            {'po_number': {'$regex': search, '$options': 'i'}},
            {'source_receipt_code': {'$regex': search, '$options': 'i'}},
        ]

    payments = await db.dewi_cmt_payments.find(q, {'_id': 0}).sort('created_at', -1).to_list(5000)
    domains = await _domain_map(db, payments)
    rows = [_enrich(p, domains.get(p['id'], 'unknown')) for p in payments]
    if scope != 'all':
        rows = [r for r in rows if r['business_type'] == scope]
    return scope, rows


@router.get("")
async def list_cmt_billing(request: Request):
    """Daftar tagihan CMT (paginasi standar repo)."""
    user = await require_auth(request)
    deny_klien(user)
    db = get_db()
    scope, rows = await _load(db, request)
    page, per_page, skip, wants = _paginate_params(request.query_params)
    if wants:
        return _paginated_envelope(rows[skip:skip + per_page], len(rows), page, per_page)
    return {'items': rows, 'total': len(rows), 'scope': scope}


@router.get("/summary")
async def cmt_billing_summary(request: Request):
    """KPI untuk header pintu Invoice."""
    user = await require_auth(request)
    deny_klien(user)
    db = get_db()
    scope, rows = await _load(db, request)

    def _sum(pred):
        return round(sum(r['amount'] for r in rows if pred(r)), 2)

    st = lambda r: (r.get('status') or '').lower()  # noqa: E731
    return {
        'scope': scope,
        'total_bills': len(rows),
        'draft': len([r for r in rows if st(r) == 'draft']),
        'approved': len([r for r in rows if st(r) == 'approved']),
        'paid': len([r for r in rows if st(r) == 'paid']),
        'not_posted': len([r for r in rows if not r['gl_posted'] and st(r) != 'cancelled']),
        'variance_flagged': len([r for r in rows if r.get('variance_flagged')]),
        'total_amount': _sum(lambda r: st(r) != 'cancelled'),
        'outstanding_amount': _sum(lambda r: st(r) in _OPEN_STATUS),
        'paid_amount': _sum(lambda r: st(r) == 'paid'),
        'total_pcs': sum(int(r.get('total_pcs', 0) or 0) for r in rows if st(r) != 'cancelled'),
    }


@router.get("/{payment_id}")
async def get_cmt_billing(payment_id: str, request: Request):
    """Detail 1 tagihan + rincian per baris + info jurnal GL."""
    user = await require_auth(request)
    deny_klien(user)
    db = get_db()
    p = await db.dewi_cmt_payments.find_one({'id': payment_id}, {'_id': 0})
    if not p:
        raise HTTPException(404, 'Tagihan CMT tidak ditemukan')
    domains = await _domain_map(db, [p])
    row = _enrich(p, domains.get(payment_id, 'unknown'))

    je = None
    if p.get('gl_je_id'):
        je = await db.rahaza_journal_entries.find_one({'id': p['gl_je_id']}, {'_id': 0})
        if je:
            lines = await db.rahaza_journal_lines.find(
                {'je_id': p['gl_je_id']}, {'_id': 0}).to_list(50)
            je = {**serialize_doc(je), 'lines': serialize_doc(lines)}

    receipt = None
    if p.get('source_receipt_id'):
        receipt = await db.cmt_receipts.find_one({'id': p['source_receipt_id']}, {'_id': 0})

    return {'bill': row, 'journal': je, 'receipt': serialize_doc(receipt) if receipt else None}
