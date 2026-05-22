from sqlalchemy import Column, Integer, String, Numeric, DateTime, JSON, UniqueConstraint, Text, Boolean
from sqlalchemy.sql import func

from app.database import Base


class Expense(Base):
    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(Integer, nullable=False, index=True)

    external_order_id = Column(String(100), nullable=False)
    source = Column(String(50), nullable=False)

    merchant_name = Column(String(255), nullable=False)
    category = Column(String(50), nullable=False)

    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(10), nullable=False, default="INR")

    transaction_date = Column(DateTime, nullable=False, index=True)

    raw_payload = Column(JSON, nullable=False)

    notes = Column(String(500), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "source",
            "external_order_id",
            name="unique_user_source_order"
        ),
    )

class Budget(Base):
    __tablename__ = "budgets"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(Integer, nullable=False, index=True)

    month = Column(Integer, nullable=False)
    year = Column(Integer, nullable=False)

    # 'food' | 'grocery'
    category = Column(String(20), nullable=False, default="food")

    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(10), nullable=False, default="INR")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "month",
            "year",
            "category",
            name="unique_user_month_category_budget"
        ),
    )


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    whatsapp_number = Column(String(50), unique=True, nullable=False, index=True)

    food_access_token = Column(Text, nullable=True)
    food_token_expiry = Column(DateTime, nullable=True)
    im_access_token = Column(Text, nullable=True)
    im_token_expiry = Column(DateTime, nullable=True)

    # Temporary state during OAuth PKCE flow
    oauth_state = Column(String(100), nullable=True)
    oauth_code_verifier = Column(Text, nullable=True)
    oauth_pending_server = Column(String(10), nullable=True)  # 'food' or 'im'

    # new | food_auth_sent | im_auth_sent | budget_pending | active
    # new | food_auth_sent | im_auth_pending | im_auth_sent
    # | food_budget_pending | grocery_budget_pending | active
    setup_step = Column(String(30), nullable=False, default="new")

    # Track which months we've already sent threshold alerts (format: "2026-05")
    notified_50_month = Column(String(7), nullable=True)
    notified_80_month = Column(String(7), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())