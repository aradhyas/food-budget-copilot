from calendar import monthrange
from datetime import datetime
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Expense
from app.repositories.budget_repository import BudgetRepository
from app.schemas import BudgetStatus


class BudgetService:

    @staticmethod
    def get_budget_status(
        db: Session,
        user_id: int,
        month: int,
        year: int
    ) -> BudgetStatus:

        budget = BudgetRepository.get_budget(
            db=db,
            user_id=user_id,
            month=month,
            year=year
        )

        if not budget:
            raise HTTPException(
                status_code=404,
                detail="Budget not found for this month"
            )

        start_date = datetime(year, month, 1)

        last_day = monthrange(year, month)[1]
        end_date = datetime(year, month, last_day, 23, 59, 59)

        spent_so_far = (
            db.query(func.coalesce(func.sum(Expense.amount), 0))
            .filter(
                Expense.user_id == user_id,
                Expense.transaction_date >= start_date,
                Expense.transaction_date <= end_date
            )
            .scalar()
        )

        today = datetime.now()

        if today.year == year and today.month == month:
            days_elapsed = max(today.day, 1)
        else:
            days_elapsed = last_day

        avg_daily_spend = Decimal(spent_so_far) / Decimal(days_elapsed)
        projected_monthly_spend = avg_daily_spend * Decimal(last_day)

        remaining_amount = Decimal(budget.amount) - Decimal(spent_so_far)
        projected_over_budget_amount = max(
            Decimal("0"),
            projected_monthly_spend - Decimal(budget.amount)
        )

        return BudgetStatus(
            user_id=user_id,
            month=month,
            year=year,
            budget_amount=budget.amount,
            spent_so_far=Decimal(spent_so_far),
            remaining_amount=remaining_amount,
            projected_monthly_spend=projected_monthly_spend,
            projected_over_budget_amount=projected_over_budget_amount,
            is_likely_to_exceed=projected_monthly_spend > Decimal(budget.amount)
        )