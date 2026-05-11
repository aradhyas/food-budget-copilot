from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional, List

from pydantic import BaseModel, Field


class ExpenseCreate(BaseModel):
    user_id: int
    external_order_id: str
    source: str
    merchant_name: str
    category: str
    amount: Decimal = Field(gt=0)
    currency: str = "INR"
    transaction_date: datetime
    raw_payload: Dict[str, Any]
    notes: Optional[str] = None


class ExpenseResponse(ExpenseCreate):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class CategorySpend(BaseModel):
    category: str
    total_amount: Decimal


class MerchantSpend(BaseModel):
    merchant_name: str
    total_amount: Decimal


class AnalyticsSummary(BaseModel):
    user_id: int
    total_spend: Decimal
    transaction_count: int
    category_breakdown: List[CategorySpend]
    top_merchants: List[MerchantSpend]

class BudgetCreate(BaseModel):
    user_id: int
    month: int = Field(ge=1, le=12)
    year: int
    amount: Decimal = Field(gt=0)
    currency: str = "INR"


class BudgetResponse(BudgetCreate):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class BudgetStatus(BaseModel):
    user_id: int
    month: int
    year: int
    budget_amount: Decimal
    spent_so_far: Decimal
    remaining_amount: Decimal
    projected_monthly_spend: Decimal
    projected_over_budget_amount: Decimal
    is_likely_to_exceed: bool