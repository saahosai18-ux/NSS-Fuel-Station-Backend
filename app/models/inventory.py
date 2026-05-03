"""
Pydantic v2 models for Inventory.
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import date


class InventoryCreate(BaseModel):
    """Schema for creating/updating inventory record."""
    fuel_type: str = Field(pattern="^(HSD|MS)$")
    date: Optional[date] = None
    opening_stock: float = Field(ge=0)
    received_qty: float = Field(ge=0, default=0)
    sold_qty: float = Field(ge=0, default=0)
    closing_stock: Optional[float] = None
    threshold: float = Field(ge=0, default=500)


class InventoryUpdate(BaseModel):
    """Schema for updating inventory."""
    opening_stock: Optional[float] = None
    received_qty: Optional[float] = None
    sold_qty: Optional[float] = None
    closing_stock: Optional[float] = None
    threshold: Optional[float] = None


class InventoryResponse(BaseModel):
    """Inventory response schema."""
    id: str
    fuel_type: str
    date: Optional[str] = None
    opening_stock: float = 0
    received_qty: float = 0
    sold_qty: float = 0
    closing_stock: float = 0
    threshold: float = 500
    created_at: Optional[str] = None

    model_config = {"from_attributes": True}


class LowStockAlert(BaseModel):
    """Low stock alert."""
    fuel_type: str
    current_stock: float
    threshold: float
    deficit: float
    message: str
