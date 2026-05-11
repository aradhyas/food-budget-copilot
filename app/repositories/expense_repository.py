from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Expense
from app.schemas import ExpenseCreate
from typing import Optional
from datetime import datetime


class ExpenseRepository:

    @staticmethod
    def create_expense(db: Session, expense_data: ExpenseCreate):
        expense = Expense(**expense_data.model_dump())

        try:
            db.add(expense)
            db.commit()
            db.refresh(expense)
            return expense

        except IntegrityError:
            db.rollback()
            raise

    @staticmethod
    def list_expenses(
        db: Session,
        user_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        category: Optional[str] = None
    ):
        query = db.query(Expense).filter(Expense.user_id == user_id)

        if start_date:
            query = query.filter(Expense.transaction_date >= start_date)

        if end_date:
            query = query.filter(Expense.transaction_date <= end_date)

        if category:
            query = query.filter(Expense.category == category)

        return query.order_by(Expense.transaction_date.desc()).all()