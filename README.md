# FoodBudget 🍱

A WhatsApp bot that connects to your Swiggy account and helps you track food + grocery spending — and nudges you before you go over budget.

Built on [Swiggy MCP](https://mcp.swiggy.com/builders/docs/) as part of the Swiggy Builders Club.

---

## What it does

- Tracks **Swiggy Food** and **Instamart** spending in one place with split budgets
- Answers natural language questions: *"how much have I spent this month?"*, *"which restaurant do I order from most?"*
- Sends a **proactive alert** when you hit 50% and 80% of your monthly budget
- Attaches **live coupon suggestions** at the 80% mark
- **Weekly digest** every Sunday + **monthly recap** on the 1st
- Honest about data limits — won't fabricate multi-month breakdowns

## Stack

- **FastAPI** — webhook server
- **Twilio** — WhatsApp messaging
- **Swiggy MCP** — Food + Instamart data via OAuth 2.1 PKCE
- **GPT-4o-mini** — natural language agent with tool loop
- **APScheduler** — proactive alerts
- **PostgreSQL** — user accounts, budgets, expenses

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/aradhyas/food-budget-copilot.git
cd food-budget-copilot
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Fill in `.env`:

```
DATABASE_URL=postgresql://user@localhost:5432/food_budget_db
OPENAI_API_KEY=sk-...
TWILIO_ACCOUNT_SID=ACxxxxx
TWILIO_AUTH_TOKEN=xxxxx
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886
APP_BASE_URL=https://your-ngrok-url.ngrok-free.app
SWIGGY_CLIENT_ID=mcp-remote
```

### 3. Set up the database

```bash
python -c "from app.database import Base, engine; Base.metadata.create_all(bind=engine)"
```

### 4. Expose localhost (dev)

```bash
ngrok http 8000
```

Copy the ngrok URL into `APP_BASE_URL` in `.env`.

### 5. Set Twilio webhook

In [Twilio Console](https://console.twilio.com) → Messaging → Sandbox Settings:
- **When a message comes in:** `https://your-ngrok-url/webhook/whatsapp` (HTTP POST)

### 6. Run

```bash
uvicorn app.main:app --reload
```

---

## User flow

1. User texts the bot → receives Swiggy Food OAuth link
2. Connects Swiggy Food → receives Instamart OAuth link
3. Connects Instamart → sets food + grocery budgets
4. Bot is active — questions answered, alerts sent automatically

**Commands:**
- `status` — quick budget snapshot
- `set food budget 3000` — update food budget
- `set grocery budget 2000` — update grocery budget
- `clear` — reset conversation history
- `reconnect` — re-link Swiggy account
- `help` — show all commands

---

## Automated messages

| When | Message |
|------|---------|
| Daily 9am | Budget threshold alert (50% or 80%) + coupons at 80% |
| Every Sunday 9am | Weekly spending digest |
| 1st of month 9am | Last month recap + budget reset reminder |

---

## Notes

- Swiggy MCP tokens expire every 5 days — users will need to reconnect via `reconnect`
- The MCP order history window is ~15 orders; yearly estimates are extrapolated
- Production Swiggy credentials required for multi-user deployment (apply at [mcp.swiggy.com/builders](https://mcp.swiggy.com/builders/))
