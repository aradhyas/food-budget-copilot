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
    def upsert_budget(db: Session, budget_data: BudgetCreate) -> Budget:
        """Create or update a budget for a user/month/year/category."""
        existing = BudgetRepository.get_budget(
            db, budget_data.user_id, budget_data.month, budget_data.year, budget_data.category
        )
        if existing:
            existing.amount = budget_data.amount
            db.commit()
            db.refresh(existing)
            return existing
        return BudgetRepository.create_budget(db, budget_data)

    @staticmethod
    def get_budget(db: Session, user_id: int, month: int, year: int, category: str = "food") -> Budget | None:
        return (
            db.query(Budget)
            .filter(
                Budget.user_id == user_id,
                Budget.month == month,
                Budget.year == year,
                Budget.category == category,
            )
            .first()
        )

    @staticmethod
    def get_all_for_month(db: Session, user_id: int, month: int, year: int) -> list[Budget]:
        return (
            db.query(Budget)
            .filter(
                Budget.user_id == user_id,
                Budget.month == month,
                Budget.year == year,
            )
            .all()
        )
