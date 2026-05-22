import os
import re
from calendar import monthrange
from datetime import datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session
from twilio.rest import Client as TwilioClient

from app import format as fmt
from app.agent import clear_history, run_agent
from app.models import User
from app.repositories.budget_repository import BudgetRepository
from app.repositories.user_repository import UserRepository
from app.schemas import BudgetCreate
from app.swiggy_auth import build_auth_url

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER")
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")

_twilio = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

HELP_TEXT = (
    "🍱 *FoodBudget — what I can do*\n\n"
    "Just ask naturally:\n"
    "• _How much have I spent this month?_\n"
    "• _Which restaurant do I order from most?_\n"
    "• _Am I on track with my budget?_\n"
    "• _What coupons do I have?_\n\n"
    "⚙️ *Commands:*\n"
    "• *status* — quick budget snapshot\n"
    "• *set food budget 3000* — update food budget\n"
    "• *set grocery budget 2000* — update grocery budget\n"
    "• *clear* — reset conversation\n"
    "• *reconnect* — re-link Swiggy account"
)


def send_message(to: str, body: str):
    _twilio.messages.create(body=body, from_=TWILIO_WHATSAPP_NUMBER, to=to)


async def handle_message(from_number: str, body: str, db: Session) -> str:
    body = body.strip()
    user = UserRepository.get_by_whatsapp(db, from_number)

    if user is None:
        user = UserRepository.create(db, from_number)

    step = user.setup_step
    lower = body.lower()

    # Global commands that work at any step
    if lower in ("help", "/help"):
        return HELP_TEXT

    if lower in ("restart", "reconnect", "/restart"):
        user.setup_step = "new"
        db.commit()
        return await _start_food_auth(user, db)

    # Setup flow
    if step == "new":
        return await _start_food_auth(user, db)

    if step == "food_auth_sent":
        return "Still waiting for you to connect Swiggy Food.\nTap the link I sent, or reply *reconnect* for a new one."

    if step == "im_auth_pending":
        return await _start_im_auth(user, db)

    if step == "im_auth_sent":
        return "Still waiting for Swiggy Instamart.\nTap the link I sent, or reply *reconnect* for a new one."

    if step == "food_budget_pending":
        return await _handle_food_budget(user, body, db)

    if step == "grocery_budget_pending":
        return await _handle_grocery_budget(user, body, db)

    # Active user
    if lower in ("clear", "/clear", "reset chat"):
        clear_history(user.id)
        return "Chat history cleared. Fresh start!"

    if lower in ("status", "budget", "/status"):
        return await _quick_status(user, db)

    if lower.startswith("set food budget") or lower.startswith("food budget"):
        return await _update_budget(user, body, "food", db)

    if lower.startswith("set grocery budget") or lower.startswith("grocery budget"):
        return await _update_budget(user, body, "grocery", db)

    if lower.startswith("set budget"):
        return await _update_budget(user, body, "food", db)

    # Everything else → AI agent
    try:
        return await run_agent(user, body, db)
    except Exception as e:
        import logging, traceback
        logging.getLogger(__name__).error("Agent error: %s\n%s", e, traceback.format_exc())
        return f"Something went wrong: {e}\n\nTry again or reply *help* for commands."


# ── Setup flow ──────────────────────────────────────────────────────────────

async def _start_food_auth(user: User, db: Session) -> str:
    callback_url = f"{APP_BASE_URL}/auth/swiggy/callback"
    try:
        auth_url, state, verifier = await build_auth_url("food", callback_url)
    except Exception as e:
        return f"Couldn't reach Swiggy right now ({e}). Try again in a moment."

    UserRepository.set_oauth_pending(db, user, "food", state, verifier)
    return (
        "👋 Hey! Welcome to *FoodBudget* 🍱\n\n"
        "I connect to your Swiggy account and help you track food + grocery spending — "
        "and nudge you before you go over budget.\n\n"
        "Let's get you set up in 2 quick steps.\n\n"
        f"*Step 1 of 2 — Connect Swiggy Food* 🍕\n"
        f"{auth_url}\n\n"
        "_Tap the link, log in with Swiggy, and come back here._"
    )


async def _start_im_auth(user: User, db: Session) -> str:
    callback_url = f"{APP_BASE_URL}/auth/swiggy/callback"
    try:
        auth_url, state, verifier = await build_auth_url("im", callback_url)
    except Exception as e:
        return f"Couldn't reach Swiggy right now ({e}). Try again in a moment."

    UserRepository.set_oauth_pending(db, user, "im", state, verifier)
    return (
        "✅ Swiggy Food connected!\n\n"
        f"*Step 2 of 2 — Connect Instamart* 🛒\n"
        f"{auth_url}\n\n"
        "_Almost there — tap the link to connect your groceries._"
    )


async def _handle_food_budget(user: User, body: str, db: Session) -> str:
    amount = _parse_amount(body)
    if amount is None:
        return (
            "🎉 Both accounts connected! You're all linked up.\n\n"
            "Last step — let's set your monthly budgets.\n\n"
            "🍕 *How much do you want to spend on food delivery per month?*\n"
            "_Reply with a number, e.g. *2500*_"
        )

    now = datetime.now()
    BudgetRepository.upsert_budget(
        db, BudgetCreate(user_id=user.id, month=now.month, year=now.year, category="food", amount=amount)
    )
    user.setup_step = "grocery_budget_pending"
    db.commit()

    return (
        f"🍕 Food budget set: *{fmt.money(amount)}/month* ✅\n\n"
        "🛒 *Now, how much for groceries (Instamart)?*\n"
        "_Reply with a number, e.g. *1500*_"
    )


async def _handle_grocery_budget(user: User, body: str, db: Session) -> str:
    amount = _parse_amount(body)
    if amount is None:
        return (
            "*How much do you want to spend on groceries (Instamart) per month?*\n"
            "Reply with a number, e.g. *1500*"
        )

    now = datetime.now()
    BudgetRepository.upsert_budget(
        db, BudgetCreate(user_id=user.id, month=now.month, year=now.year, category="grocery", amount=amount)
    )
    UserRepository.set_active(db, user)

    food_budget = BudgetRepository.get_budget(db, user.id, now.month, now.year, "food")
    food_amt = food_budget.amount if food_budget else Decimal("0")

    return (
        f"🛒 Grocery budget: *{fmt.money(amount)}/month* ✅\n\n"
        f"🎯 Total monthly budget: *{fmt.money(food_amt + amount)}*\n\n"
        "You're all set! Here's what you can ask me:\n"
        "• _How much have I spent this month?_\n"
        "• _Which restaurant do I order from most?_\n"
        "• _Am I on track with my budget?_\n"
        "• _What coupons do I have?_\n\n"
        "📊 I'll ping you when you hit 50% and 80% of your budget — no surprises."
    )


# ── Active user helpers ─────────────────────────────────────────────────────

async def _quick_status(user: User, db: Session) -> str:
    try:
        reply = await run_agent(
            user,
            "Give me a budget snapshot: total food delivery spend and grocery spend this month vs my budgets. "
            "Format it clearly with amounts and percentage used.",
            db,
        )
        return reply
    except Exception as e:
        return f"Couldn't fetch status: {e}"


async def _update_budget(user: User, body: str, category: str, db: Session) -> str:
    amount = _parse_amount(body)
    if amount is None:
        label = "food delivery" if category == "food" else "grocery"
        return f"Couldn't read the amount. Try: *set {category} budget 3000*"

    now = datetime.now()
    BudgetRepository.upsert_budget(
        db, BudgetCreate(user_id=user.id, month=now.month, year=now.year, category=category, amount=amount)
    )

    label = "🍕 Food delivery" if category == "food" else "🛒 Grocery"
    return f"{label} budget updated to *{fmt.money(amount)}* for {now.strftime('%B %Y')}."


def _parse_amount(text: str) -> Decimal | None:
    cleaned = text.replace("₹", "").replace(",", "")
    match = re.search(r"\d+(?:\.\d+)?", cleaned)
    if match:
        try:
            return Decimal(match.group())
        except InvalidOperation:
            return None
    return None
