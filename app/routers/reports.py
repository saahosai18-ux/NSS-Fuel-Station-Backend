"""
Reports router — CRUD for shift reports with full lifecycle:
  draft → pending → approved/rejected
Includes variance calculation, edit tracking, and approval workflow.
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional, List
from datetime import date, datetime

from app.models.report import (
    ReportCreate, ReportUpdate, ReportApproval, ReportResponse,
)
from app.services.supabase_service import (
    get_supabase_admin, get_current_user, require_role, log_audit,
)
from app.services.sheets_service import sync_all_on_approval
from app.services.notification_service import (
    notify_report_submitted, notify_report_approved, notify_report_rejected,
)
from app.utils.variance import calculate_shift, validate_closing_readings

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get("/", response_model=List[ReportResponse])
async def list_reports(
    report_date: Optional[str] = Query(None, alias="date"),
    pump_id: Optional[str] = None,
    status: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """
    List reports. DSM sees only their own; Manager/Owner sees all.
    """
    supabase = get_supabase_admin()
    query = supabase.table("reports").select("*")

    # DSM: filter to own reports only
    if user["role"] == "dsm":
        query = query.eq("dsm_id", user["id"])

    if report_date:
        query = query.eq("date", report_date)
    if pump_id:
        query = query.eq("pump_id", pump_id)
    if status:
        query = query.eq("status", status)

    query = query.order("created_at", desc=True)
    result = query.execute()
    reports = result.data or []

    # Fetch credits for all returned reports
    if reports:
        report_ids = [r["id"] for r in reports]
        credits_res = supabase.table("credit_entries").select("*").in_("report_id", report_ids).execute()
        credits_by_report = {}
        for c in (credits_res.data or []):
            rid = c["report_id"]
            if rid not in credits_by_report:
                credits_by_report[rid] = []
            # Map DB fields to Pydantic alias
            credits_by_report[rid].append({
                "name": c["customer_name"],
                "amount": c["amount"]
            })
        
        for r in reports:
            r["credit_entries"] = credits_by_report.get(r["id"], [])

    return reports


@router.get("/{report_id}", response_model=ReportResponse)
async def get_report(
    report_id: str,
    user: dict = Depends(get_current_user),
):
    """Get a single report by ID."""
    supabase = get_supabase_admin()
    result = supabase.table("reports").select("*").eq("id", report_id).single().execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Report not found")

    report = result.data

    # Fetch credits
    credits_res = supabase.table("credit_entries").select("*").eq("report_id", report_id).execute()
    report["credit_entries"] = []
    for c in (credits_res.data or []):
        report["credit_entries"].append({
            "name": c["customer_name"],
            "amount": c["amount"]
        })

    # DSM can only see their own
    if user["role"] == "dsm" and report.get("dsm_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")

    return report


@router.post("/", response_model=ReportResponse)
async def create_report(
    body: ReportCreate,
    user: dict = Depends(get_current_user),
):
    """
    Create a new shift report.
    Automatically calculates all derived values (litres, sales, variance).
    """
    if not user.get("is_approved", False) and user["role"] == "dsm":
        raise HTTPException(status_code=403, detail="Account is pending approval. You cannot submit reports.")

    supabase = get_supabase_admin()

    # Validate closing >= opening
    validation = validate_closing_readings(
        body.open_n1, body.open_n2, body.open_n3, body.open_n4,
        body.close_n1, body.close_n2, body.close_n3, body.close_n4,
    )
    if not validation["valid"]:
        raise HTTPException(status_code=400, detail=validation["errors"])

    # Get current fuel prices
    hsd_price_row = supabase.table("fuel_prices").select("price_per_litre").eq("fuel_type", "HSD").order("effective_from", desc=True).limit(1).execute()
    ms_price_row = supabase.table("fuel_prices").select("price_per_litre").eq("fuel_type", "MS").order("effective_from", desc=True).limit(1).execute()

    hsd_price = float(hsd_price_row.data[0]["price_per_litre"]) if hsd_price_row.data else 91.29
    ms_price = float(ms_price_row.data[0]["price_per_litre"]) if ms_price_row.data else 103.24

    # Calculate shift values (exact port of existing JavaScript logic)
    calc = calculate_shift(
        open_n1=body.open_n1, open_n2=body.open_n2,
        open_n3=body.open_n3, open_n4=body.open_n4,
        close_n1=body.close_n1, close_n2=body.close_n2,
        close_n3=body.close_n3, close_n4=body.close_n4,
        hsd_price=hsd_price, ms_price=ms_price,
        cash=body.cash, upi=body.upi, pine=body.pine,
        otp=body.otp, credit_given=body.credit_given,
        expenses=body.expenses, testing_amt=body.testing_amt,
        bp_rewards=body.bp_rewards,
        test_hsd=body.test_hsd, test_ms=body.test_ms,
        open_hsd=body.open_hsd, load_hsd=body.load_hsd,
        open_ms=body.open_ms, load_ms=body.load_ms,
    )

    # Build report record
    report_data = {
        "dsm_id": user["id"],
        "pump_id": str(body.pump_id),  # Stored as TEXT now
        "shift": body.shift,
        "date": str(body.report_date),
        # Vtot readings
        "open_n1": body.open_n1, "open_n2": body.open_n2,
        "open_n3": body.open_n3, "open_n4": body.open_n4,
        "close_n1": body.close_n1, "close_n2": body.close_n2,
        "close_n3": body.close_n3, "close_n4": body.close_n4,
        # Calculated
        "hsd_sold": calc["hsd_sold"], "ms_sold": calc["ms_sold"],
        "hsd_net": calc["hsd_net"], "ms_net": calc["ms_net"],
        "hsd_price": hsd_price, "ms_price": ms_price,
        "hsd_sales": calc["hsd_sales"], "ms_sales": calc["ms_sales"],
        "total_sales": calc["total_sales"],
        "expected_sales": calc["expected_sales"],
        # Payments
        "cash": body.cash, "upi": body.upi,
        "pine": body.pine, "otp": body.otp,
        "credit_total": body.credit_given,
        "gross_collected": calc["gross_collected"],
        # Deductions
        "expenses": body.expenses, "testing_amt": body.testing_amt,
        "bp_rewards": body.bp_rewards,
        "net_collected": calc["net_collected"],
        # Variance
        "variance": calc["variance"],
        "variance_status": calc["variance_status"],
        "cash_in_hand": calc["cash_in_hand"],
        # Stock
        "open_hsd": body.open_hsd, "load_hsd": body.load_hsd,
        "test_hsd": body.test_hsd, "close_hsd": calc["close_hsd"],
        "open_ms": body.open_ms, "load_ms": body.load_ms,
        "test_ms": body.test_ms, "close_ms": calc["close_ms"],
        # Staff
        "dsm_name": body.dsm_name or user["name"],
        "manager_name": body.manager_name,
        # Status
        "status": "pending",
        "submitted_at": datetime.utcnow().isoformat(),
    }

    result = supabase.table("reports").insert(report_data).execute()

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create report")

    report = result.data[0]

    # Insert credit entries
    if body.credit_entries:
        credits_to_insert = []
        for c in body.credit_entries:
            credits_to_insert.append({
                "report_id": report["id"],
                "customer_name": c.customer_name,
                "amount": c.amount,
                "amount_received": 0,
                "date": str(body.report_date),
                "pump_index": int(body.pump_id) if body.pump_id.isdigit() else 1,
                "fuel_type": "HSD",
                "litres": 0
            })
        supabase.table("credit_entries").insert(credits_to_insert).execute()

    # Audit log
    await log_audit(user["id"], "create", "reports", report["id"], {"status": "pending"})

    # Notify managers
    await notify_report_submitted(
        dsm_name=body.dsm_name or user["name"],
        pump_name=body.pump_id,
        report_date=str(body.report_date),
    )

    return report


@router.put("/{report_id}", response_model=ReportResponse)
async def update_report(
    report_id: str,
    body: ReportUpdate,
    user: dict = Depends(require_role("manager", "owner")),
):
    """
    Edit a report's collection values.
    Only managers/owners can edit. Locked after approval.
    All edits are logged to audit_log.
    """
    supabase = get_supabase_admin()

    # Fetch existing report
    existing = supabase.table("reports").select("*").eq("id", report_id).single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Report not found")

    report = existing.data

    # Report lock after approval — no edits allowed
    if report["status"] == "approved":
        raise HTTPException(
            status_code=400,
            detail="Report is approved and locked. No edits allowed."
        )

    # Capture old values for audit
    old_values = {
        "cash": report["cash"], "upi": report["upi"],
        "credit_total": report["credit_total"],
        "expenses": report["expenses"],
    }

    # Apply updates
    update_data = {}
    if body.cash is not None:
        update_data["cash"] = body.cash
    if body.upi is not None:
        update_data["upi"] = body.upi
    if body.pine is not None:
        update_data["pine"] = body.pine
    if body.otp is not None:
        update_data["otp"] = body.otp
    if body.credit_given is not None:
        update_data["credit_total"] = body.credit_given
    if body.expenses is not None:
        update_data["expenses"] = body.expenses
    if body.testing_amt is not None:
        update_data["testing_amt"] = body.testing_amt
    if body.bp_rewards is not None:
        update_data["bp_rewards"] = body.bp_rewards

    # Merge with existing values
    merged = {**report, **update_data}

    # Recalculate
    calc = calculate_shift(
        open_n1=float(merged["open_n1"]), open_n2=float(merged["open_n2"]),
        open_n3=float(merged["open_n3"]), open_n4=float(merged["open_n4"]),
        close_n1=float(merged["close_n1"]), close_n2=float(merged["close_n2"]),
        close_n3=float(merged["close_n3"]), close_n4=float(merged["close_n4"]),
        hsd_price=float(merged["hsd_price"]), ms_price=float(merged["ms_price"]),
        cash=float(merged.get("cash", 0)), upi=float(merged.get("upi", 0)),
        pine=float(merged.get("pine", 0)), otp=float(merged.get("otp", 0)),
        credit_given=float(merged.get("credit_total", 0)),
        expenses=float(merged.get("expenses", 0)),
        testing_amt=float(merged.get("testing_amt", 0)),
        bp_rewards=float(merged.get("bp_rewards", 0)),
        test_hsd=float(merged.get("test_hsd", 0)),
        test_ms=float(merged.get("test_ms", 0)),
        open_hsd=float(merged.get("open_hsd", 0)),
        load_hsd=float(merged.get("load_hsd", 0)),
        open_ms=float(merged.get("open_ms", 0)),
        load_ms=float(merged.get("load_ms", 0)),
    )

    update_data.update({
        "gross_collected": calc["gross_collected"],
        "net_collected": calc["net_collected"],
        "variance": calc["variance"],
        "variance_status": calc["variance_status"],
        "cash_in_hand": calc["cash_in_hand"],
        "close_hsd": calc["close_hsd"],
        "close_ms": calc["close_ms"],
        "is_edited": True,
        "edit_count": (report.get("edit_count") or 0) + 1,
        "last_edited_by": user["role"],
        "last_edited_at": datetime.utcnow().isoformat(),
    })

    result = supabase.table("reports").update(update_data).eq("id", report_id).execute()

    # Audit log
    await log_audit(user["id"], "edit", "reports", report_id, {
        "reason": body.edit_reason,
        "notes": body.edit_notes,
        "old_values": old_values,
        "new_values": {k: update_data.get(k) for k in old_values},
    })

    return result.data[0] if result.data else report


@router.post("/{report_id}/approve", response_model=ReportResponse)
async def approve_or_reject_report(
    report_id: str,
    body: ReportApproval,
    user: dict = Depends(require_role("manager", "owner")),
):
    """
    Approve or reject a report.
    On approval:
    - Status → approved, locked for edits
    - Syncs to Google Sheets (FUEL SALES, CREDIT LEDGER, INVENTORY)
    - Deducts inventory
    - Sends notification to DSM
    """
    supabase = get_supabase_admin()

    existing = supabase.table("reports").select("*").eq("id", report_id).single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Report not found")

    report = existing.data

    if report["status"] not in ("pending", "draft"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot {body.action} a report with status '{report['status']}'"
        )

    if body.action == "approve":
        update_data = {
            "status": "approved",
            "approved_by": user["id"],
            "approved_at": datetime.utcnow().isoformat(),
        }

        result = supabase.table("reports").update(update_data).eq("id", report_id).execute()
        updated = result.data[0] if result.data else report

        # Sync to Google Sheets
        try:
            # Get credit entries for this report
            credits_result = supabase.table("credit_entries").select("*").eq("report_id", report_id).execute()
            credit_entries = credits_result.data or []

            # Use a simple string for pump_name instead of querying the pumps table
            # since pump_id is now a string and not a UUID.
            pump_name = f"Pump {report['pump_id']}"

            sync_report = {**updated, "pump_name": pump_name}
            sync_result = await sync_all_on_approval(sync_report, credit_entries)

            if sync_result.get("synced"):
                supabase.table("reports").update({"synced_to_sheets": True}).eq("id", report_id).execute()
                updated["synced_to_sheets"] = True
            else:
                print(f"Sheets sync failed with errors: {sync_result.get('errors')}")
        except Exception as e:
            print(f"Sheets sync exception: {e}")
            # Don't fail the approval if sync fails

        # Update inventory — deduct sold quantity
        try:
            for fuel_type, sold_qty in [("HSD", float(report.get("hsd_net", 0))), ("MS", float(report.get("ms_net", 0)))]:
                if sold_qty > 0:
                    inv_result = supabase.table("inventory").select("*").eq("fuel_type", fuel_type).order("created_at", desc=True).limit(1).execute()
                    if inv_result.data:
                        inv = inv_result.data[0]
                        new_closing = float(inv.get("closing_stock", 0)) - sold_qty
                        supabase.table("inventory").update({
                            "sold_qty": float(inv.get("sold_qty", 0)) + sold_qty,
                            "closing_stock": new_closing,
                        }).eq("id", inv["id"]).execute()
        except Exception as e:
            print(f"Inventory update error: {e}")

        # Audit log
        await log_audit(user["id"], "approve", "reports", report_id)

        # Notify DSM
        pname = f"Pump {report['pump_id']}"
        await notify_report_approved(pname, report.get("date", ""), report.get("dsm_id", ""))

        return updated

    elif body.action == "reject":
        if not body.rejection_reason:
            raise HTTPException(status_code=400, detail="Rejection reason is required")

        update_data = {
            "status": "rejected",
            "rejection_reason": body.rejection_reason,
        }

        result = supabase.table("reports").update(update_data).eq("id", report_id).execute()

        # Audit log
        await log_audit(user["id"], "reject", "reports", report_id, {
            "reason": body.rejection_reason,
        })

        # Notify DSM
        pump_result3 = supabase.table("pumps").select("display_name").eq("id", report["pump_id"]).single().execute()
        pname = pump_result3.data.get("display_name", "") if pump_result3.data else ""
        await notify_report_rejected(pname, report.get("date", ""), report.get("dsm_id", ""), body.rejection_reason)

        return result.data[0] if result.data else report

@router.delete("/{report_id}")
async def delete_report(
    report_id: str,
    user: dict = Depends(require_role("manager", "owner")),
):
    """Delete a report permanently (usually during testing)."""
    supabase = get_supabase_admin()
    
    # Check if report exists
    existing = supabase.table("reports").select("*").eq("id", report_id).single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Report not found")
        
    # Delete associated credit entries first
    supabase.table("credit_entries").delete().eq("report_id", report_id).execute()
    
    # Delete report
    supabase.table("reports").delete().eq("id", report_id).execute()
    
    return {"success": True, "message": "Report deleted successfully"}



@router.get("/summary/{report_date}")
async def get_daily_summary(
    report_date: str,
    user: dict = Depends(get_current_user),
):
    """
    Get daily summary aggregating all approved reports for a date.
    Mirrors the existing buildDailySummary() function.
    """
    supabase = get_supabase_admin()
    result = supabase.table("reports").select("*").eq("date", report_date).execute()
    reports = result.data or []

    summary = {
        "date": report_date,
        "total_sales": 0,
        "cash_in_hand": 0,
        "profit": 0,
        "hsd_litres": 0,
        "ms_litres": 0,
        "shifts_done": len(reports),
        "difference": 0,
    }

    # Get margins for profit calc
    hsd_margin_row = supabase.table("fuel_prices").select("margin_per_litre").eq("fuel_type", "HSD").order("effective_from", desc=True).limit(1).execute()
    ms_margin_row = supabase.table("fuel_prices").select("margin_per_litre").eq("fuel_type", "MS").order("effective_from", desc=True).limit(1).execute()
    hsd_margin = float(hsd_margin_row.data[0]["margin_per_litre"]) if hsd_margin_row.data else 2.5
    ms_margin = float(ms_margin_row.data[0]["margin_per_litre"]) if ms_margin_row.data else 3.0

    for report in reports:
        summary["total_sales"] += float(report.get("total_sales", 0))
        summary["cash_in_hand"] += float(report.get("cash_in_hand", 0))
        hsd_net = float(report.get("hsd_net", 0))
        ms_net = float(report.get("ms_net", 0))
        summary["profit"] += (hsd_net * hsd_margin) + (ms_net * ms_margin)
        summary["hsd_litres"] += hsd_net
        summary["ms_litres"] += ms_net
        summary["difference"] += float(report.get("variance", 0))

    summary["daily_avg"] = summary["total_sales"] / max(summary["shifts_done"], 1)

    # Credit data for the day
    credits_result = supabase.table("credit_entries").select("*").eq("date", report_date).execute()
    credits = credits_result.data or []
    summary["credit_given"] = sum(float(c.get("amount", 0)) for c in credits)
    summary["credit_received"] = sum(float(c.get("amount_received", 0)) for c in credits)

    # Total pending credit (all time)
    all_credits = supabase.table("credit_entries").select("amount, amount_received").execute()
    summary["pending_credit"] = sum(
        max(0, float(c.get("amount", 0)) - float(c.get("amount_received", 0)))
        for c in (all_credits.data or [])
    )

    return summary

@router.get("/sheets/dashboard")
async def get_sheets_dashboard_data(
    user: dict = Depends(require_role("manager", "owner"))
):
    """
    Fetch the DASHBOARD tab data from Google Sheets directly.
    Only accessible by manager/owner.
    """
    from app.services.sheets_service import get_dashboard_data
    try:
        data = get_dashboard_data()
        return {"status": "success", "data": data.get("values", [])}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
