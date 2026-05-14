"""
Sync router — manual sync trigger and status for Google Sheets.
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Optional

from app.services.supabase_service import (
    get_supabase_admin, get_current_user, require_role, log_audit,
)
from app.services.sheets_service import (
    sync_all_on_approval
)

router = APIRouter(prefix="/sync", tags=["Sync"])


@router.post("/sheets/{report_id}")
async def sync_report_to_sheets(
    report_id: str,
    user: dict = Depends(require_role("manager", "owner")),
):
    """
    Manually trigger Google Sheets sync for a specific report.
    Normally this happens automatically on approval, but this endpoint
    allows retrying if the initial sync failed.
    """
    supabase = get_supabase_admin()

    # Fetch report
    result = supabase.table("reports").select("*").eq("id", report_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Report not found")

    report = result.data

    if report["status"] != "approved":
        raise HTTPException(
            status_code=400,
            detail="Only approved reports can be synced to Google Sheets"
        )

    # Get pump name
    pump_name = f"Pump {report['pump_id']}"

    # Get credit entries
    credits_result = supabase.table("credit_entries").select("*").eq(
        "report_id", report_id
    ).execute()

    sync_report = {**report, "pump_name": pump_name}
    sync_result = await sync_all_on_approval(sync_report, credits_result.data or [])

    if sync_result.get("synced"):
        supabase.table("reports").update({"synced_to_sheets": True}).eq("id", report_id).execute()

    await log_audit(user["id"], "manual_sync", "reports", report_id, sync_result)

    return sync_result


@router.post("/sheets/setup-headers")
async def setup_sheet_headers(
    user: dict = Depends(require_role("owner")),
):
    """
    Initialize Google Sheets with header rows.
    Call once after creating the spreadsheet.
    """
    try:
        # ensure_sheet_headers() is removed because we use predefined Excel template
        return {"status": "ok", "message": "Headers are pre-configured in the Excel template"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_sync_status(user: dict = Depends(get_current_user)):
    """
    Get sync status — count of unsynced approved reports.
    """
    supabase = get_supabase_admin()

    # Count approved but not synced
    result = supabase.table("reports").select(
        "id", count="exact"
    ).eq("status", "approved").eq("synced_to_sheets", False).execute()

    unsynced_count = result.count or 0

    # Count total approved
    total = supabase.table("reports").select(
        "id", count="exact"
    ).eq("status", "approved").execute()

    total_approved = total.count or 0

    return {
        "unsynced_count": unsynced_count,
        "total_approved": total_approved,
        "synced_count": total_approved - unsynced_count,
        "all_synced": unsynced_count == 0,
    }
