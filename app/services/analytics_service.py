from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Expense
from app.schemas import AnalyticsSummary, CategorySpend, MerchantSpend


class AnalyticsService:

    @staticmethod
    def get_summary(
        db: Session,
        user_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> AnalyticsSummary:

        base_query = db.query(Expense).filter(Expense.user_id == user_id)

        if start_date:
            base_query = base_query.filter(Expense.transaction_date >= start_date)

        if end_date:
            base_query = base_query.filter(Expense.transaction_date <= end_date)

        total_spend = (
            base_query
            .with_entities(func.coalesce(func.sum(Expense.amount), 0))
            .scalar()
        )

        transaction_count = base_query.count()

        category_rows = (
            base_query
            .with_entities(
                Expense.category,
                func.sum(Expense.amount).label("total_amount")
            )
            .group_by(Expense.category)
            .order_by(func.sum(Expense.amount).desc())
            .all()
        )

        merchant_rows = (
            base_query
            .with_entities(
                Expense.merchant_name,
                func.sum(Expense.amount).label("total_amount")
            )
            .group_by(Expense.merchant_name)
            .order_by(func.sum(Expense.amount).desc())
            .limit(5)
            .all()
        )

        return AnalyticsSummary(
            user_id=user_id,
            total_spend=Decimal(total_spend),
            transaction_count=transaction_count,
            category_breakdown=[
                CategorySpend(
                    category=row.category,
                    total_amount=row.total_amount
                )
                for row in category_rows
            ],
            top_merchants=[
                MerchantSpend(
                    merchant_name=row.merchant_name,
                    total_amount=row.total_amount
                )
                for row in merchant_rows
            ]
        )