"""
Credits router — credit entries, payments, and ledger.
Preserves existing credit flow: add credit (customer name required),
record payment, mark fully paid, filter/search.
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional, List
from datetime import date

from app.models.credit import (
    CreditEntryCreate, PaymentRecord, MarkFullyPaid,
    CreditEntryResponse, CreditSummary,
)
from app.services.supabase_service import (
    get_supabase_admin, get_current_user, require_role, log_audit,
)

router = APIRouter(prefix="/credits", tags=["Credits"])


@router.get("/", response_model=List[CreditEntryResponse])
async def list_credits(
    status: Optional[str] = Query(None, description="Filter: Pending, Partial, Cleared"),
    search: Optional[str] = Query(None, description="Search by customer name"),
    credit_date: Optional[str] = Query(None, alias="date"),
    user: dict = Depends(get_current_user),
):
    """
    List all credit entries with optional filtering.
    Matches the existing renderCredit() filter behavior.
    """
    supabase = get_supabase_admin()
    query = supabase.table("credit_entries").select("*")

    if credit_date:
        query = query.eq("date", credit_date)

    if search:
        query = query.ilike("customer_name", f"%{search}%")

    query = query.order("created_at", desc=True)
    result = query.execute()
    entries = result.data or []

    # Enrich with computed fields
    enriched = []
    for entry in entries:
        amount = float(entry.get("amount", 0))
        received = float(entry.get("amount_received", 0))
        balance = amount - received

        if balance <= 0:
            entry_status = "Cleared"
        elif received > 0:
            entry_status = "Partial"
        else:
            entry_status = "Pending"

        # Apply status filter
        if status and status != "All" and entry_status != status:
            continue

        entry["balance"] = balance
        entry["status"] = entry_status

        # Parse payment_history from JSONB
        history = entry.get("payment_history", [])
        if isinstance(history, str):
            import json
            try:
                history = json.loads(history)
            except Exception:
                history = []
        entry["payment_history"] = history or []

        enriched.append(entry)

    return enriched


@router.get("/summary", response_model=CreditSummary)
async def get_credit_summary(user: dict = Depends(get_current_user)):
    """
    Get credit totals: total given, received, pending, overdue count.
    """
    supabase = get_supabase_admin()
    result = supabase.table("credit_entries").select("amount, amount_received").execute()
    entries = result.data or []

    total_given = sum(float(e.get("amount", 0)) for e in entries)
    total_received = sum(float(e.get("amount_received", 0)) for e in entries)
    total_pending = sum(
        max(0, float(e.get("amount", 0)) - float(e.get("amount_received", 0)))
        for e in entries
    )

    return CreditSummary(
        total_given=round(total_given, 2),
        total_received=round(total_received, 2),
        total_pending=round(total_pending, 2),
        overdue_count=0,  # TODO: implement overdue logic based on date
    )


@router.post("/", response_model=CreditEntryResponse)
async def create_credit(
    body: CreditEntryCreate,
    user: dict = Depends(get_current_user),
):
    """
    Add a new credit entry.
    Customer name is REQUIRED (preserved from existing logic).
    """
    supabase = get_supabase_admin()

    data = {
        "customer_name": body.customer_name,
        "amount": body.amount,
        "amount_received": 0,
        "pump_index": body.pump_index,
        "fuel_type": body.fuel_type,
        "litres": body.litres,
        "note": body.note or "",
        "date": str(body.date or date.today()),
        "payment_history": [],
    }

    result = supabase.table("credit_entries").insert(data).execute()

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create credit entry")

    entry = result.data[0]
    entry["balance"] = body.amount
    entry["status"] = "Pending"

    await log_audit(user["id"], "create", "credit_entries", entry["id"], {
        "customer": body.customer_name,
        "amount": body.amount,
    })

    return entry


@router.post("/{entry_id}/payment", response_model=CreditEntryResponse)
async def record_payment(
    entry_id: str,
    body: PaymentRecord,
    user: dict = Depends(get_current_user),
):
    """
    Record a payment received on a credit entry.
    Matches the existing savePayment() logic.
    """
    supabase = get_supabase_admin()

    # Fetch existing entry
    existing = supabase.table("credit_entries").select("*").eq("id", entry_id).single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Credit entry not found")

    entry = existing.data
    new_received = float(entry.get("amount_received", 0)) + body.amount

    # Update payment history
    history = entry.get("payment_history", [])
    if isinstance(history, str):
        import json
        try:
            history = json.loads(history)
        except Exception:
            history = []

    history.append({
        "date": str(body.date or date.today()),
        "amount": body.amount,
        "note": body.note or "",
    })

    update_data = {
        "amount_received": new_received,
        "payment_history": history,
    }

    result = supabase.table("credit_entries").update(update_data).eq("id", entry_id).execute()

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to update credit entry")

    updated = result.data[0]
    amount = float(updated.get("amount", 0))
    balance = amount - new_received
    updated["balance"] = balance
    updated["status"] = "Cleared" if balance <= 0 else ("Partial" if new_received > 0 else "Pending")
    updated["payment_history"] = history

    await log_audit(user["id"], "payment", "credit_entries", entry_id, {
        "amount": body.amount,
        "new_total_received": new_received,
    })

    return updated


@router.post("/{entry_id}/mark-paid", response_model=CreditEntryResponse)
async def mark_fully_paid(
    entry_id: str,
    body: MarkFullyPaid = MarkFullyPaid(),
    user: dict = Depends(get_current_user),
):
    """
    Mark a credit entry as fully paid.
    Sets amount_received = amount (clears the balance).
    """
    supabase = get_supabase_admin()

    existing = supabase.table("credit_entries").select("*").eq("id", entry_id).single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Credit entry not found")

    entry = existing.data
    amount = float(entry.get("amount", 0))
    current_received = float(entry.get("amount_received", 0))
    pending = amount - current_received

    if pending <= 0:
        raise HTTPException(status_code=400, detail="Already fully cleared")

    history = entry.get("payment_history", [])
    if isinstance(history, str):
        import json
        try:
            history = json.loads(history)
        except Exception:
            history = []

    history.append({
        "date": str(date.today()),
        "amount": pending,
        "note": body.note or "Marked fully paid",
    })

    update_data = {
        "amount_received": amount,
        "payment_history": history,
    }

    result = supabase.table("credit_entries").update(update_data).eq("id", entry_id).execute()

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to update credit entry")

    updated = result.data[0]
    updated["balance"] = 0
    updated["status"] = "Cleared"
    updated["payment_history"] = history

    await log_audit(user["id"], "mark_paid", "credit_entries", entry_id, {
        "amount_cleared": pending,
    })

    return updated


@router.get("/overdue")
async def get_overdue_entries(user: dict = Depends(get_current_user)):
    """
    Get credit entries that are overdue (pending for more than 30 days).
    """
    supabase = get_supabase_admin()
    result = supabase.table("credit_entries").select("*").execute()
    entries = result.data or []

    overdue = []
    today = date.today()

    for entry in entries:
        amount = float(entry.get("amount", 0))
        received = float(entry.get("amount_received", 0))
        balance = amount - received

        if balance > 0:
            entry_date = entry.get("date", "")
            if entry_date:
                try:
                    d = date.fromisoformat(entry_date)
                    days_old = (today - d).days
                    if days_old > 30:
                        entry["balance"] = balance
                        entry["days_overdue"] = days_old
                        overdue.append(entry)
                except Exception:
                    pass

    return overdue
