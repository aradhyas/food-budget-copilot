from calendar import monthrange
from datetime import datetime
from decimal import Decimal

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app import format as fmt
from app.models import User
from app.repositories.budget_repository import BudgetRepository
from app.swiggy_client import get_food_coupons, get_monthly_food_spend, get_monthly_grocery_spend
from app.whatsapp import send_message

scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")


def start_scheduler(session_factory):
    scheduler.add_job(
        daily_budget_check,
        CronTrigger(hour=9, minute=0, timezone="Asia/Kolkata"),
        args=[session_factory],
        id="daily_budget_check",
        replace_existing=True,
    )
    scheduler.add_job(
        weekly_digest,
        CronTrigger(day_of_week="sun", hour=9, minute=0, timezone="Asia/Kolkata"),
        args=[session_factory],
        id="weekly_digest",
        replace_existing=True,
    )
    scheduler.add_job(
        monthly_recap,
        CronTrigger(day=1, hour=9, minute=0, timezone="Asia/Kolkata"),
        args=[session_factory],
        id="monthly_recap",
        replace_existing=True,
    )
    scheduler.start()


async def daily_budget_check(session_factory):
    db = session_factory()
    try:
        users = db.query(User).filter(User.setup_step == "active").all()
        now = datetime.now()
        month_key = now.strftime("%Y-%m")
        days_left = monthrange(now.year, now.month)[1] - now.day

        for user in users:
            try:
                await _check_thresholds(user, db, now, month_key, days_left)
            except Exception:
                pass
    finally:
        db.close()


async def _check_thresholds(user: User, db, now: datetime, month_key: str, days_left: int):
    food_budget = BudgetRepository.get_budget(db, user.id, now.month, now.year, "food")
    grocery_budget = BudgetRepository.get_budget(db, user.id, now.month, now.year, "grocery")

    if not food_budget and not grocery_budget:
        return

    food_spent, _ = await get_monthly_food_spend(user.food_access_token)
    grocery_spent, _ = await get_monthly_grocery_spend(user.im_access_token)

    food_amt = food_budget.amount if food_budget else Decimal("0")
    grocery_amt = grocery_budget.amount if grocery_budget else Decimal("0")
    total_budget = food_amt + grocery_amt
    total_spent = food_spent + grocery_spent

    if total_budget == 0:
        return

    pct = int((total_spent / total_budget) * 100)

    if pct >= 80 and user.notified_80_month != month_key:
        msg = fmt.threshold_alert(80, food_spent, grocery_spent, food_amt, grocery_amt, days_left)

        # Attach coupon nudge if user has tokens
        try:
            coupons = await get_food_coupons(user.food_access_token)
            if coupons:
                coupon_lines = ["\n🎟️ *You have active coupons — use them wisely:*"]
                for c in coupons[:2]:
                    code = c.get("code") or c.get("coupon_code", "")
                    desc = c.get("description") or c.get("title", "")
                    if code:
                        coupon_lines.append(f"  • *{code}* — {desc}")
                msg += "\n".join(coupon_lines)
        except Exception:
            pass

        send_message(user.whatsapp_number, msg)
        user.notified_80_month = month_key
        db.commit()

    elif pct >= 50 and user.notified_50_month != month_key and user.notified_80_month != month_key:
        msg = fmt.threshold_alert(50, food_spent, grocery_spent, food_amt, grocery_amt, days_left)
        send_message(user.whatsapp_number, msg)
        user.notified_50_month = month_key
        db.commit()


async def weekly_digest(session_factory):
    db = session_factory()
    try:
        users = db.query(User).filter(User.setup_step == "active").all()
        now = datetime.now()

        for user in users:
            try:
                food_spent, food_count = await get_monthly_food_spend(user.food_access_token)
                grocery_spent, grocery_count = await get_monthly_grocery_spend(user.im_access_token)

                msg = fmt.weekly_summary_card(
                    food_spent=food_spent,
                    grocery_spent=grocery_spent,
                    order_count=food_count + grocery_count,
                )

                food_budget = BudgetRepository.get_budget(db, user.id, now.month, now.year, "food")
                grocery_budget = BudgetRepository.get_budget(db, user.id, now.month, now.year, "grocery")

                if food_budget or grocery_budget:
                    food_amt = food_budget.amount if food_budget else Decimal("0")
                    grocery_amt = grocery_budget.amount if grocery_budget else Decimal("0")
                    msg += "\n\n" + fmt.split_summary(food_spent, food_amt, grocery_spent, grocery_amt)

                send_message(user.whatsapp_number, msg)
            except Exception:
                pass
    finally:
        db.close()


async def monthly_recap(session_factory):
    db = session_factory()
    try:
        users = db.query(User).filter(User.setup_step == "active").all()
        now = datetime.now()
        # Recap is for the previous month
        prev_month = now.month - 1 or 12
        prev_year = now.year if now.month > 1 else now.year - 1

        for user in users:
            try:
                food_spent, food_count = await get_monthly_food_spend(user.food_access_token)
                grocery_spent, grocery_count = await get_monthly_grocery_spend(user.im_access_token)
                total = food_spent + grocery_spent

                food_budget = BudgetRepository.get_budget(db, user.id, prev_month, prev_year, "food")
                grocery_budget = BudgetRepository.get_budget(db, user.id, prev_month, prev_year, "grocery")
                food_amt = food_budget.amount if food_budget else Decimal("0")
                grocery_amt = grocery_budget.amount if grocery_budget else Decimal("0")
                total_budget = food_amt + grocery_amt

                month_name = datetime(prev_year, prev_month, 1).strftime("%B")
                verdict = "under budget 🎉" if total <= total_budget else f"over by {fmt.money(total - total_budget)} 😬"

                msg = (
                    f"🗓️ *{month_name} wrapped up!*\n\n"
                    f"🍕 Food delivery: *{fmt.money(food_spent)}* ({food_count} orders)\n"
                    f"🛒 Groceries: *{fmt.money(grocery_spent)}* ({grocery_count} orders)\n"
                    f"💸 Total: *{fmt.money(total)}* — {verdict}\n\n"
                    f"New month, fresh start 🌱\n"
                    f"Your budgets carry over automatically.\n"
                    f"_Reply *set food budget 3000* to adjust anytime._"
                )
                send_message(user.whatsapp_number, msg)

                # Reset alert flags for new month
                user.notified_50_month = None
                user.notified_80_month = None
                db.commit()
            except Exception:
                pass
    finally:
        db.close()
