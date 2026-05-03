"""
Inventory router — stock tracking for HSD and MS fuels.
Deducts on report approval, low stock alerts.
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional, List
from datetime import date

from app.models.inventory import (
    InventoryCreate, InventoryUpdate, InventoryResponse, LowStockAlert,
)
from app.services.supabase_service import (
    get_supabase_admin, get_current_user, require_role, log_audit,
)
from app.services.notification_service import notify_low_stock

router = APIRouter(prefix="/inventory", tags=["Inventory"])


@router.get("/", response_model=List[InventoryResponse])
async def list_inventory(
    fuel_type: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """Get all inventory records, optionally filtered by fuel type."""
    supabase = get_supabase_admin()
    query = supabase.table("inventory").select("*")

    if fuel_type:
        query = query.eq("fuel_type", fuel_type)

    query = query.order("created_at", desc=True)
    result = query.execute()
    return result.data or []


@router.get("/current")
async def get_current_stock(user: dict = Depends(get_current_user)):
    """
    Get current stock levels for HSD and MS.
    Returns the latest inventory record for each fuel type.
    """
    supabase = get_supabase_admin()

    stocks = {}
    for fuel_type in ["HSD", "MS"]:
        result = supabase.table("inventory").select("*").eq(
            "fuel_type", fuel_type
        ).order("created_at", desc=True).limit(1).execute()

        if result.data:
            stocks[fuel_type] = result.data[0]
        else:
            stocks[fuel_type] = {
                "fuel_type": fuel_type,
                "opening_stock": 0,
                "received_qty": 0,
                "sold_qty": 0,
                "closing_stock": 0,
                "threshold": 500,
            }

    return stocks


@router.post("/", response_model=InventoryResponse)
async def create_inventory(
    body: InventoryCreate,
    user: dict = Depends(require_role("manager", "owner")),
):
    """Create a new inventory record."""
    supabase = get_supabase_admin()

    closing = body.closing_stock
    if closing is None:
        closing = body.opening_stock + body.received_qty - body.sold_qty

    data = {
        "fuel_type": body.fuel_type,
        "date": str(body.date or date.today()),
        "opening_stock": body.opening_stock,
        "received_qty": body.received_qty,
        "sold_qty": body.sold_qty,
        "closing_stock": closing,
        "threshold": body.threshold,
    }

    result = supabase.table("inventory").insert(data).execute()

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create inventory record")

    record = result.data[0]

    # Check low stock alert
    if closing < body.threshold:
        await notify_low_stock(body.fuel_type, closing, body.threshold)

    await log_audit(user["id"], "create", "inventory", record["id"])

    return record


@router.put("/{inventory_id}", response_model=InventoryResponse)
async def update_inventory(
    inventory_id: str,
    body: InventoryUpdate,
    user: dict = Depends(require_role("manager", "owner")),
):
    """Update an inventory record."""
    supabase = get_supabase_admin()

    update_data = {}
    if body.opening_stock is not None:
        update_data["opening_stock"] = body.opening_stock
    if body.received_qty is not None:
        update_data["received_qty"] = body.received_qty
    if body.sold_qty is not None:
        update_data["sold_qty"] = body.sold_qty
    if body.closing_stock is not None:
        update_data["closing_stock"] = body.closing_stock
    if body.threshold is not None:
        update_data["threshold"] = body.threshold

    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = supabase.table("inventory").update(update_data).eq("id", inventory_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Inventory record not found")

    await log_audit(user["id"], "update", "inventory", inventory_id)

    return result.data[0]


@router.get("/alerts", response_model=List[LowStockAlert])
async def get_low_stock_alerts(user: dict = Depends(get_current_user)):
    """
    Check for low stock levels.
    Returns alerts for any fuel type below its threshold.
    """
    supabase = get_supabase_admin()
    alerts = []

    for fuel_type in ["HSD", "MS"]:
        result = supabase.table("inventory").select("*").eq(
            "fuel_type", fuel_type
        ).order("created_at", desc=True).limit(1).execute()

        if result.data:
            record = result.data[0]
            closing = float(record.get("closing_stock", 0))
            threshold = float(record.get("threshold", 500))

            if closing < threshold:
                alerts.append(LowStockAlert(
                    fuel_type=fuel_type,
                    current_stock=closing,
                    threshold=threshold,
                    deficit=threshold - closing,
                    message=f"{fuel_type} stock at {closing:.0f}L — below threshold of {threshold:.0f}L",
                ))

    return alerts
