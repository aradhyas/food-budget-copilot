import asyncio
import json
import logging
import os
from datetime import datetime

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from openai import AsyncOpenAI, RateLimitError
from sqlalchemy.orm import Session

from app.models import User

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are FoodBudget 🍱 — a witty, warm spending assistant connected to the user's Swiggy account via WhatsApp.

You have access to Swiggy Food and Instamart tools. Use them accurately.

## Personality
- Conversational, a little playful, never preachy about spending
- Use emojis naturally — not every line, but enough to feel alive
- End most responses with one short follow-up suggestion so the user knows what to ask next
  e.g. "Want to see your top restaurants? 🏆" or "Curious about last month? Just ask!"
- Celebrate wins: if they're under budget, say so with energy 🎉

## Core behaviour
- Responses via WhatsApp — SHORT (under 200 words), scannable, use line breaks
- WhatsApp markdown: *bold* for key numbers, _italic_ for tips
- Always show amounts as ₹X,XXX (e.g. ₹2,300)
- Never say "I cannot" — use the tools and figure it out

## Fetching orders — CRITICAL rules
- Call get_food_orders and get_orders with NO address parameter — ever. Passing an address errors out.
- If the user mentions an address (e.g. "orders at my home"), ignore it entirely.
- For date/time filters: you MAY pass date range parameters if the tool schema supports them.
  Try calling with a date range when the user asks for a specific period (e.g. yearly).
  If the tool doesn't accept date params, call it with no args and work with what you get.
- DATA LIMITATION — this is critical:
  The Swiggy MCP returns a fixed recent window of orders (roughly the last 15-30 days).
  It does NOT support filtering by month or year — every call returns the same recent dataset.

  NEVER present the same order list as data for two different months. That is fabrication.
  NEVER invent a monthly or yearly breakdown unless the order dates in the data actually
  span those months.

  If the user asks for yearly, multi-month, or historical data:
  1. Call get_food_orders once, look at the actual dates in the returned orders
  2. Tell the user honestly: "Swiggy's API only shows me your last ~15 orders.
     The oldest order I can see is from [date]. I can't go further back than that."
  3. If they want an estimate: calculate the average spend per order × estimated orders/month
     and be clear it's an estimate, not real data.

## When the user asks about spending
1. Call get_food_orders (no args) → sum up amounts for the period asked
2. Call get_orders (no args) → sum up Instamart amounts
3. Show breakdown like this:
   🍕 Food: *₹X,XXX* / ₹Y,YYY  ▓▓▓▓▓░░░░░ 60%
   🛒 Groceries: *₹X,XXX* / ₹Y,YYY  ▓▓▓░░░░░░░ 30%
   💸 Total: *₹X,XXX* / ₹Y,YYY
4. Add one honest, friendly insight

## Insights & patterns
- Surface the top restaurant and its monthly cost
- Spot trends: "You ordered 4 times this week vs 2 last week 📈"
- Frame habits warmly: "Your weekend Swiggy habit costs ~₹X/month 😄"

## Coupon awareness
- If spend looks high (>70% of budget) OR user asks about saving, call fetch_food_coupons
- Present as: "🎟️ You've got a [X]% off coupon for [restaurant] — perfect timing"

Today's date: {today}
"""

_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# In-memory conversation history per user (resets on server restart)
_history: dict[int, list] = {}
MAX_HISTORY_PAIRS = 5


def get_history(user_id: int) -> list:
    return _history.get(user_id, [])


def clear_history(user_id: int):
    _history.pop(user_id, None)


def update_history(user_id: int, user_msg: str, assistant_msg: str):
    history = _history.get(user_id, [])
    history.append({"role": "user", "content": user_msg})
    history.append({"role": "assistant", "content": assistant_msg})
    _history[user_id] = history[-(MAX_HISTORY_PAIRS * 2):]


# Tools where address params should never be passed
_ORDER_HISTORY_TOOLS = {"get_food_orders", "get_orders", "get_food_order_details", "track_food_order"}
_ADDRESS_PARAM_KEYS = {"address_id", "address", "delivery_address", "addressId", "lat", "lng", "latitude", "longitude"}


def _sanitize_schema(tool_name: str, schema: dict) -> dict:
    """Strip address-related params from order history tools so the model can't use them."""
    if tool_name not in _ORDER_HISTORY_TOOLS:
        return schema
    if not schema or "properties" not in schema:
        return schema

    props = {k: v for k, v in schema["properties"].items() if k not in _ADDRESS_PARAM_KEYS}
    required = [r for r in schema.get("required", []) if r not in _ADDRESS_PARAM_KEYS]
    return {**schema, "properties": props, "required": required}


async def run_agent(user: User, user_message: str, db: Session) -> str:
    if not user.food_access_token or not user.im_access_token:
        return "Your Swiggy account isn't fully connected yet. Please complete setup first."

    system = SYSTEM_PROMPT.format(today=datetime.now().strftime("%d %b %Y"))
    history = get_history(user.id)
    messages = [{"role": "system", "content": system}] + history + [
        {"role": "user", "content": user_message}
    ]

    async with streamablehttp_client(
        "https://mcp.swiggy.com/food",
        headers={"Authorization": f"Bearer {user.food_access_token}"},
    ) as (food_read, food_write, _):
        async with ClientSession(food_read, food_write) as food_session:
            await food_session.initialize()

            async with streamablehttp_client(
                "https://mcp.swiggy.com/im",
                headers={"Authorization": f"Bearer {user.im_access_token}"},
            ) as (im_read, im_write, _):
                async with ClientSession(im_read, im_write) as im_session:
                    await im_session.initialize()

                    food_tools_resp = await food_session.list_tools()
                    im_tools_resp = await im_session.list_tools()

                    tool_sessions: dict[str, ClientSession] = {}
                    openai_tools = []

                    for tool in food_tools_resp.tools:
                        tool_sessions[tool.name] = food_session
                        openai_tools.append({
                            "type": "function",
                            "function": {
                                "name": tool.name,
                                "description": tool.description or "",
                                "parameters": _sanitize_schema(tool.name, tool.inputSchema),
                            },
                        })

                    for tool in im_tools_resp.tools:
                        tool_sessions[tool.name] = im_session
                        openai_tools.append({
                            "type": "function",
                            "function": {
                                "name": tool.name,
                                "description": tool.description or "",
                                "parameters": _sanitize_schema(tool.name, tool.inputSchema),
                            },
                        })

                    reply = await _tool_loop(messages, openai_tools, tool_sessions)

    update_history(user.id, user_message, reply)
    return reply


async def _call_with_retry(messages: list, tools: list, retries: int = 3):
    for attempt in range(retries):
        try:
            return await _client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                tools=tools,
                tool_choice="auto",
            )
        except RateLimitError as e:
            if attempt == retries - 1:
                raise
            wait = 2 ** attempt  # 1s, 2s, 4s
            logger.warning("Rate limit hit, retrying in %ds", wait)
            await asyncio.sleep(wait)


async def _tool_loop(
    messages: list,
    tools: list,
    tool_sessions: dict[str, ClientSession],
) -> str:
    while True:
        response = await _call_with_retry(messages, tools)

        message = response.choices[0].message

        if not message.tool_calls:
            return message.content or "Sorry, I couldn't process that."

        # Append assistant message with tool calls
        messages = messages + [message]

        # Execute each tool call
        tool_results = []
        for tc in message.tool_calls:
            session = tool_sessions.get(tc.function.name)
            if session:
                args = json.loads(tc.function.arguments)
                result = await session.call_tool(tc.function.name, args)
                content = json.dumps([c.model_dump() for c in result.content])
            else:
                content = json.dumps({"error": f"Unknown tool: {tc.function.name}"})

            tool_results.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": content,
            })

        messages = messages + tool_results
