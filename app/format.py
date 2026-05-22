from decimal import Decimal


def money(amount) -> str:
    return f"₹{int(Decimal(str(amount))):,}"


def budget_bar(spent, total, length: int = 10) -> str:
    if not total or total == 0:
        return "░" * length
    pct = min(float(spent) / float(total), 1.0)
    filled = round(pct * length)
    bar = "▓" * filled + "░" * (length - filled)
    return f"{bar} {int(pct * 100)}%"


def split_summary(food_spent, food_budget, grocery_spent, grocery_budget) -> str:
    food_spent = Decimal(str(food_spent))
    food_budget = Decimal(str(food_budget)) if food_budget else Decimal("0")
    grocery_spent = Decimal(str(grocery_spent))
    grocery_budget = Decimal(str(grocery_budget)) if grocery_budget else Decimal("0")
    total_spent = food_spent + grocery_spent
    total_budget = food_budget + grocery_budget

    lines = ["📊 *Budget snapshot*\n"]

    if food_budget:
        lines.append(f"🍕 *Food delivery*")
        lines.append(f"   {money(food_spent)} / {money(food_budget)}")
        lines.append(f"   {budget_bar(food_spent, food_budget)}\n")

    if grocery_budget:
        lines.append(f"🛒 *Groceries*")
        lines.append(f"   {money(grocery_spent)} / {money(grocery_budget)}")
        lines.append(f"   {budget_bar(grocery_spent, grocery_budget)}\n")

    if food_budget and grocery_budget:
        lines.append(f"─────────────────")
        lines.append(f"Total: {money(total_spent)} / {money(total_budget)}")
        lines.append(f"{budget_bar(total_spent, total_budget)}")

    return "\n".join(lines)


def weekly_summary_card(
    food_spent, grocery_spent, order_count: int, top_restaurant: str = None
) -> str:
    total = Decimal(str(food_spent)) + Decimal(str(grocery_spent))
    lines = [
        "📅 *Weekly food recap*\n",
        f"🍕 Food delivery: *{money(food_spent)}*",
        f"🛒 Groceries: *{money(grocery_spent)}*",
        f"📦 Orders: {order_count}",
    ]
    if top_restaurant:
        lines.append(f"🏆 Top spot: {top_restaurant}")
    lines.append(f"\n💸 Total: *{money(total)}*")
    lines.append("\n_Reply *status* to see how you're tracking this month._")
    return "\n".join(lines)


def threshold_alert(pct: int, food_spent, grocery_spent, food_budget, grocery_budget, days_left: int) -> str:
    total_spent = Decimal(str(food_spent)) + Decimal(str(grocery_spent))
    total_budget = Decimal(str(food_budget or 0)) + Decimal(str(grocery_budget or 0))
    remaining = total_budget - total_spent

    if pct >= 80:
        emoji = "🚨"
        headline = f"You've used *{pct}%* of your budget"
        tip = "\n_Tip: one home-cooked meal saves ~₹300 🥗_"
    else:
        emoji = "📊"
        headline = f"You've hit *{pct}%* of your budget"
        tip = "\n_You've got room — but worth keeping an eye on it._"

    lines = [
        f"{emoji} *Budget check-in*\n",
        headline,
        f"Spent: *{money(total_spent)}* · Remaining: *{money(remaining)}*",
        f"Days left this month: {days_left}",
        f"\n{budget_bar(total_spent, total_budget)}",
        tip,
    ]
    return "\n".join(lines)
