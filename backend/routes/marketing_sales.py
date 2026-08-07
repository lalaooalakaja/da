# ruff: noqa: F401
"""
marketing_sales.py — Sales Data Management
Extracted from marketing.py (1757 LOC monolith)

Refactored: Session #11.19 Phase 3.2 Batch #3
Endpoints: POST /sales-data, GET /accounts/{account_id}/sales
"""
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel, Field
from database import get_db
from auth import require_auth, serialize_doc, log_activity
from routes.marketing_shared import _uid, _now, _get_user, _sanitize, SalesDataEntry, _recalculate_health_score

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/marketing', tags=['Marketing-Sales'])

@router.post("/sales-data")
async def create_sales_data(data: SalesDataEntry, request: Request):
    """
    Manual sales data entry for Phase 1.
    Phase 4 will replace this with smart import.
    
    IMPORTANT: revenue_type must be 'total' OR 'live' (separated)
    """
    await require_auth(request)
    db = get_db()
    
    # Validate account exists
    account = await db.marketing_platform_accounts.find_one({"id": data.account_id}, {"_id": 0})
    if not account:
        raise HTTPException(404, "Account not found")
    
    # Validate revenue_type
    if data.revenue_type not in ["total", "live"]:
        raise HTTPException(400, "revenue_type must be 'total' or 'live'")
    
    # Check duplicate entry (same account + date + revenue_type)
    existing = await db.marketing_sales_data.find_one({
        "account_id": data.account_id,
        "date": data.date,
        "revenue_type": data.revenue_type
    }, {"_id": 0})
    
    if existing:
        raise HTTPException(400, f"Sales data for {data.date} ({data.revenue_type}) already exists for this account")
    
    # Calculate AOV if not provided
    aov = data.aov
    if aov is None and data.orders > 0:
        aov = data.revenue / data.orders
    
    # Build sales entry with complete metrics
    sales_entry = {
        "id": _uid(),
        "account_id": data.account_id,
        "account_code": account["account_code"],
        "platform": account["platform"],
        "date": data.date,
        "revenue_type": data.revenue_type,
        "metrics": {
            "revenue": data.revenue,
            "orders": data.orders,
            "aov": aov or 0,
            "gmv": data.gmv or data.revenue,
            "conversion_rate": data.conversion_rate or 0
        },
        "fulfillment": {
            "fulfillment_rate": data.fulfillment_rate or 0,
            "cancellation_rate": data.cancellation_rate or 0,
            "return_rate": data.return_rate or 0,
            "late_shipment_rate": data.late_shipment_rate or 0
        },
        "customer_satisfaction": {
            "rating": data.rating or 0,
            "review_count": data.review_count or 0,
            "response_rate": data.response_rate or 0,
            "response_time_hours": data.response_time_hours or 0
        },
        "live_metrics": {
            "viewers": data.viewers or 0,
            "avg_viewers": data.avg_viewers or 0,
            "likes": data.likes or 0,
            "shares": data.shares or 0,
            "comments": data.comments or 0,
            "new_followers": data.new_followers or 0,
            "live_sessions": data.live_sessions or 0
        } if data.revenue_type == "live" else {},
        "import_history_id": None,  # Manual entry, no import
        "created_at": _now(),
        "created_by": _get_user(request).get("email", "system")
    }
    
    await db.marketing_sales_data.insert_one(sales_entry)
    
    # Update account health score after new data
    await _recalculate_health_score(db, data.account_id)
    
    await log_activity(
        (_get_user(request)).get("id", "system"),
        (_get_user(request)).get("name") or (_get_user(request)).get("email", "system"),
        "create",
        "marketing_sales_data",
        f"Added sales data: {account['account_name']} - {data.date} ({data.revenue_type})"
    )
    
    return serialize_doc({"message": "Sales data created", "entry": sales_entry})


@router.get("/accounts/{account_id}/sales")
async def get_account_sales_data(
    account_id: str,
    request: Request,
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
    revenue_type: Optional[str] = Query(None, description="total | live | all")
):
    """
    Get sales data for an account with date range filter.
    revenue_type='all' returns both total and live data.
    """
    await require_auth(request)
    db = get_db()
    
    account = await db.marketing_platform_accounts.find_one({"id": account_id}, {"_id": 0})
    if not account:
        raise HTTPException(404, "Account not found")
    
    query = {"account_id": account_id}
    
    # Date range filter
    if date_from or date_to:
        query["date"] = {}
        if date_from:
            query["date"]["$gte"] = date_from
        if date_to:
            query["date"]["$lte"] = date_to
    
    # Revenue type filter
    if revenue_type and revenue_type != "all":
        if revenue_type not in ["total", "live"]:
            raise HTTPException(400, "revenue_type must be 'total', 'live', or 'all'")
        query["revenue_type"] = revenue_type
    
    sales_data = await db.marketing_sales_data.find(query, {"_id": 0}).sort("date", -1).to_list(500)
    
    return serialize_doc(sales_data)



# ══════════════════════════════════════════════════════════════════════════════
# PHASE 7A: MARKETING SALES → AR INVOICE BATCH GENERATION
# ══════════════════════════════════════════════════════════════════════════════

class ARBatchRequest(BaseModel):
    date_from: str = Field(..., description="YYYY-MM-DD")
    date_to: str = Field(..., description="YYYY-MM-DD")
    account_id: Optional[str] = None
    platform: Optional[str] = None
    revenue_type: str = Field(default="total", description="total | live")
    grouping: str = Field(default="daily", description="daily | weekly | monthly | platform")
    customer_id: Optional[str] = None  # Default: generic "Marketplace Customer"
    notes: Optional[str] = ""


@router.post("/sales-data/generate-ar-batch")
async def generate_ar_batch_from_sales(data: ARBatchRequest, request: Request):
    """
    [DINONAKTIFKAN — KEPUTUSAN #1] Jalur otomatis Marketing Sales -> AR Finance
    telah dimatikan. Pendapatan marketplace kini dicatat Finance via Jurnal Manual
    (rahaza_journals). Input sales harian (POST /sales-data) tetap tersedia untuk
    dashboard marketing (analitik) dan TIDAK memicu AR/GL.

    Modul AR Finance (rahaza_finance) & Journal Entry (rahaza_journals) TIDAK
    terpengaruh. Endpoint ini sengaja dipertahankan (bukan dihapus) agar UI lama
    yang masih memanggilnya mendapat pesan jelas, bukan 404, dan TIDAK menulis
    apa pun ke rahaza_ar_invoices / GL.
    """
    # Tetap wajib auth: caller tak berwenang -> 401 (perilaku konsisten).
    await require_auth(request)
    raise HTTPException(
        status_code=410,
        detail={
            "code": "MARKETING_AR_DISABLED",
            "message": (
                "Fitur 'Buat Invoice AR dari Sales Marketing' telah dinonaktifkan "
                "(Keputusan #1). Pendapatan marketplace dicatat oleh Finance melalui "
                "Jurnal Manual (Manual Journal Entry). Input sales harian tetap "
                "tersedia untuk dashboard marketing."
            ),
        },
    )


async def _gen_ar_number(db):
    """Generate AR invoice number with date prefix (RC-5 fix: atomic counter)."""
    from utils.counters import gen_prefixed_number
    today = datetime.now(timezone.utc).date().strftime("%Y%m%d")
    return await gen_prefixed_number(db, "rahaza_ar_invoices", "invoice_number", f"AR-{today}-", 3)


# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD (Basic for Phase 1)
