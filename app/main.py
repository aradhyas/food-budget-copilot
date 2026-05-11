from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db
from app.repositories.expense_repository import ExpenseRepository
from app.schemas import ExpenseCreate, ExpenseResponse

from datetime import datetime
from typing import Optional
from app.schemas import AnalyticsSummary
from app.services.analytics_service import AnalyticsService

from app.repositories.budget_repository import BudgetRepository
from app.schemas import BudgetCreate, BudgetResponse, BudgetStatus
from app.services.budget_service import BudgetService

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Food Budget Copilot")


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/expenses", response_model=ExpenseResponse)
def create_expense(
    expense_data: ExpenseCreate,
    db: Session = Depends(get_db)
):
    try:
        return ExpenseRepository.create_expense(
            db=db,
            expense_data=expense_data
        )

    except IntegrityError:
        raise HTTPException(
            status_code=409,
            detail="Expense already exists for this user"
        )

@app.get("/expenses", response_model=list[ExpenseResponse])
def list_expenses(
    user_id: int,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    category: Optional[str] = None,
    db: Session = Depends(get_db)
):
    return ExpenseRepository.list_expenses(
        db=db,
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
        category=category
    )

@app.get("/analytics/summary", response_model=AnalyticsSummary)
def get_analytics_summary(
    user_id: int,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: Session = Depends(get_db)
):
    return AnalyticsService.get_summary(
        db=db,
        user_id=user_id,
        start_date=start_date,
        end_date=end_date
    )

@app.post("/budgets", response_model=BudgetResponse)
def create_budget(
    budget_data: BudgetCreate,
    db: Session = Depends(get_db)
):
    try:
        return BudgetRepository.create_budget(
            db=db,
            budget_data=budget_data
        )

    except IntegrityError:
        raise HTTPException(
            status_code=409,
            detail="Budget already exists for this user, month, and year"
        )


@app.get("/budgets/status", response_model=BudgetStatus)
def get_budget_status(
    user_id: int,
    month: int,
    year: int,
    db: Session = Depends(get_db)
):
    return BudgetService.get_budget_status(
        db=db,
        user_id=user_id,
        month=month,
        year=year
    )