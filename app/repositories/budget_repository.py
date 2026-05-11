from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Budget
from app.schemas import BudgetCreate


class BudgetRepository:

    @staticmethod
    def create_budget(db: Session, budget_data: BudgetCreate):
        budget = Budget(**budget_data.model_dump())

        try:
            db.add(budget)
            db.commit()
            db.refresh(budget)
            return budget

        except IntegrityError:
            db.rollback()
            raise

    @staticmethod
    def get_budget(db: Session, user_id: int, month: int, year: int):
        return (
            db.query(Budget)
            .filter(
                Budget.user_id == user_id,
                Budget.month == month,
                Budget.year == year
            )
            .first()
        )