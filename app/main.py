import os
from datetime import datetime
from typing import Optional

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db
from app.repositories.budget_repository import BudgetRepository
from app.repositories.expense_repository import ExpenseRepository
from app.repositories.user_repository import UserRepository
from app.schemas import (
    AnalyticsSummary,
    BudgetCreate,
    BudgetResponse,
    BudgetStatus,
    ExpenseCreate,
    ExpenseResponse,
)
from app.services.analytics_service import AnalyticsService
from app.services.budget_service import BudgetService
from app.database import SessionLocal
from app.scheduler import start_scheduler
from app.swiggy_auth import exchange_code
from app.whatsapp import handle_message, send_message

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Food Budget Copilot")


@app.on_event("startup")
async def startup():
    start_scheduler(SessionLocal)

APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")


@app.get("/health")
def health_check():
    return {"status": "ok"}


# ── WhatsApp webhook ────────────────────────────────────────────────────────

@app.post("/webhook/whatsapp")
async def whatsapp_webhook(
    Body: str = Form(default=""),
    From: str = Form(default=""),
    db: Session = Depends(get_db),
):
    reply = await handle_message(from_number=From, body=Body, db=db)
    send_message(to=From, body=reply)
    # Return empty TwiML so Twilio doesn't also send a default response
    return HTMLResponse(content='<?xml version="1.0"?><Response></Response>', media_type="text/xml")


# ── Swiggy OAuth callback ───────────────────────────────────────────────────

@app.get("/auth/swiggy/callback")
async def swiggy_oauth_callback(
    code: str,
    state: str,
    db: Session = Depends(get_db),
):
    user = UserRepository.get_by_oauth_state(db, state)
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state.")

    server = user.oauth_pending_server
    callback_url = f"{APP_BASE_URL}/auth/swiggy/callback"

    try:
        access_token, expiry = await exchange_code(server, code, user.oauth_code_verifier, callback_url)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Token exchange failed: {e}")

    UserRepository.save_token(db, user, server, access_token, expiry)

    # Prompt next step via WhatsApp
    if user.setup_step == "im_auth_pending":
        from app.whatsapp import _start_im_auth
        msg = await _start_im_auth(user, db)
    elif user.setup_step == "budget_pending":
        msg = "Both accounts connected! What's your monthly food + grocery budget?\n\nJust reply with a number, e.g. *3000*"
    else:
        msg = "Connected! You can now ask me about your Swiggy spending."

    send_message(to=user.whatsapp_number, body=msg)

    return HTMLResponse(
        content="<h2>Connected! Head back to WhatsApp to continue setup.</h2>",
        status_code=200,
    )


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