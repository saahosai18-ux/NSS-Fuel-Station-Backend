"""
Pydantic v2 models for Reports (shift submissions).
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date, time, datetime
from enum import Enum


class ShiftType(str, Enum):
    DAY = "day"
    NIGHT = "night"


class ReportStatus(str, Enum):
    DRAFT = "draft"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ShiftCreditEntry(BaseModel):
    customer_name: str = Field(alias="name")
    amount: float = Field(ge=0)


class ShiftExpenseEntry(BaseModel):
    description: str
    amount: float = Field(ge=0)


class VarianceStatus(str, Enum):
    PERFECT = "PERFECT"
    SHORTAGE = "SHORTAGE"
    EXCESS = "EXCESS"


class ReportCreate(BaseModel):
    """Schema for creating a new report (DSM submitting shift data)."""
    pump_id: str
    shift: ShiftType = ShiftType.DAY
    report_date: date = Field(alias="date")
    # Vtot readings
    open_n1: float = Field(ge=0)
    open_n2: float = Field(ge=0)
    open_n3: float = Field(ge=0)
    open_n4: float = Field(ge=0)
    close_n1: float = Field(ge=0)
    close_n2: float = Field(ge=0)
    close_n3: float = Field(ge=0)
    close_n4: float = Field(ge=0)
    # Payments
    cash: float = 0
    upi: float = 0
    pine: float = 0
    otp: float = 0
    credit_given: float = Field(default=0, alias="credit_total")
    # Deductions
    expenses: float = 0
    testing_amt: float = 0
    bp_rewards: float = 0
    # Stock
    open_hsd: float = 0
    load_hsd: float = 0
    test_hsd: float = 0
    open_ms: float = 0
    load_ms: float = 0
    test_ms: float = 0
    # Staff
    dsm_name: Optional[str] = None
    manager_name: Optional[str] = None
    # Credits array
    credit_entries: List[ShiftCreditEntry] = []
    expense_entries: List[ShiftExpenseEntry] = []
    # Times
    shift_start: Optional[str] = "08:00"
    shift_end: Optional[str] = "17:00"

    model_config = {"populate_by_name": True}


class ReportUpdate(BaseModel):
    """Schema for editing a report (Manager editing collection values)."""
    cash: Optional[float] = None
    upi: Optional[float] = None
    pine: Optional[float] = None
    otp: Optional[float] = None
    credit_given: Optional[float] = None
    expenses: Optional[float] = None
    testing_amt: Optional[float] = None
    bp_rewards: Optional[float] = None
    edit_reason: str = Field(min_length=1)
    edit_notes: Optional[str] = None


class ReportSubmit(BaseModel):
    """Schema for submitting a draft report (changes status to pending)."""
    pass


class ReportApproval(BaseModel):
    """Schema for approving/rejecting a report."""
    action: str = Field(pattern="^(approve|reject)$")
    rejection_reason: Optional[str] = None
    hsd_price: Optional[float] = None
    ms_price: Optional[float] = None


class ReportResponse(BaseModel):
    """Full report response schema."""
    id: str
    dsm_id: Optional[str] = None
    pump_id: Optional[str] = None
    shift: str = "day"
    date: Optional[str] = None
    # Vtot
    open_n1: float = 0
    open_n2: float = 0
    open_n3: float = 0
    open_n4: float = 0
    close_n1: float = 0
    close_n2: float = 0
    close_n3: float = 0
    close_n4: float = 0
    # Calculated
    hsd_sold: float = 0
    ms_sold: float = 0
    hsd_net: float = 0
    ms_net: float = 0
    hsd_price: float = 0
    ms_price: float = 0
    hsd_sales: float = 0
    ms_sales: float = 0
    total_sales: float = 0
    expected_sales: float = 0
    # Payments
    cash: float = 0
    upi: float = 0
    pine: float = 0
    otp: float = 0
    card: float = 0
    credit_total: float = 0
    gross_collected: float = 0
    # Deductions
    expenses: float = 0
    testing_amt: float = 0
    bp_rewards: float = 0
    net_collected: float = 0
    # Variance
    variance: float = 0
    variance_status: str = "PERFECT"
    cash_in_hand: float = 0
    # Stock
    open_hsd: float = 0
    load_hsd: float = 0
    test_hsd: float = 0
    close_hsd: float = 0
    open_ms: float = 0
    load_ms: float = 0
    test_ms: float = 0
    close_ms: float = 0
    # Staff
    dsm_name: Optional[str] = None
    manager_name: Optional[str] = None
    shift_start: Optional[str] = None
    shift_end: Optional[str] = None
    # Status
    status: str = "draft"
    rejection_reason: Optional[str] = None
    approved_by: Optional[str] = None
    submitted_at: Optional[str] = None
    approved_at: Optional[str] = None
    synced_to_sheets: bool = False
    is_edited: bool = False
    edit_count: int = 0
    last_edited_by: Optional[str] = None
    last_edited_at: Optional[str] = None
    created_at: Optional[str] = None
    credit_entries: List[ShiftCreditEntry] = []
    expense_entries: List[ShiftExpenseEntry] = []

    model_config = {"from_attributes": True}
