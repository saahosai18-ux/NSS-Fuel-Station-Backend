"""
Pydantic v2 models for Credit entries and ledger.
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date


class CreditEntryCreate(BaseModel):
    """Schema for creating a credit entry (requires customer name)."""
    customer_name: str = Field(min_length=1, description="Customer name is required")
    amount: float = Field(gt=0)
    pump_index: int = Field(ge=1, le=3, default=1)
    fuel_type: str = Field(default="HSD", pattern="^(HSD|MS)$")
    litres: float = Field(ge=0, default=0)
    note: Optional[str] = None
    date: Optional[date] = None


class PaymentRecord(BaseModel):
    """Schema for recording a payment on a credit entry."""
    amount: float = Field(gt=0)
    date: Optional[date] = None
    note: Optional[str] = None


class MarkFullyPaid(BaseModel):
    """Schema for marking a credit entry as fully paid."""
    note: Optional[str] = "Marked fully paid"


class PaymentHistoryItem(BaseModel):
    """A single payment record in history."""
    date: str
    amount: float
    note: str = ""


class CreditEntryResponse(BaseModel):
    """Credit entry response schema."""
    id: str
    report_id: Optional[str] = None
    customer_id: Optional[str] = None
    customer_name: str
    amount: float = 0
    amount_received: float = 0
    balance: float = 0
    pump_index: int = 1
    fuel_type: str = "HSD"
    litres: float = 0
    note: Optional[str] = None
    date: Optional[str] = None
    status: str = "Pending"
    payment_history: List[PaymentHistoryItem] = []
    created_at: Optional[str] = None

    model_config = {"from_attributes": True}


class CreditSummary(BaseModel):
    """Credit summary totals."""
    total_given: float = 0
    total_received: float = 0
    total_pending: float = 0
    overdue_count: int = 0


class CreditLedgerResponse(BaseModel):
    """Credit ledger response."""
    id: str
    customer_id: Optional[str] = None
    customer_name: str
    date: Optional[str] = None
    credit_given: float = 0
    payment_received: float = 0
    balance: float = 0
    is_overdue: bool = False
    created_at: Optional[str] = None

    model_config = {"from_attributes": True}
