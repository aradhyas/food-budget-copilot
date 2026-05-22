"""Lightweight direct MCP tool calls used by the scheduler (no AI layer)."""
import json
from decimal import Decimal

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from app.models import User


async def get_monthly_food_spend(food_token: str) -> tuple[Decimal, int]:
    """Returns (total_amount, order_count) for current month food orders."""
    async with streamablehttp_client(
        "https://mcp.swiggy.com/food",
        headers={"Authorization": f"Bearer {food_token}"},
    ) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("get_food_orders", {})
            raw = _extract_text(result)
            return _sum_orders(raw)


async def get_monthly_grocery_spend(im_token: str) -> tuple[Decimal, int]:
    """Returns (total_amount, order_count) for current month Instamart orders."""
    async with streamablehttp_client(
        "https://mcp.swiggy.com/im",
        headers={"Authorization": f"Bearer {im_token}"},
    ) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("get_orders", {})
            raw = _extract_text(result)
            return _sum_orders(raw)


async def get_food_coupons(food_token: str) -> list[dict]:
    """Returns list of available coupons."""
    async with streamablehttp_client(
        "https://mcp.swiggy.com/food",
        headers={"Authorization": f"Bearer {food_token}"},
    ) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("fetch_food_coupons", {})
            raw = _extract_text(result)
            try:
                data = json.loads(raw)
                if isinstance(data, list):
                    return data[:3]
                if isinstance(data, dict) and "coupons" in data:
                    return data["coupons"][:3]
            except Exception:
                pass
            return []


def _extract_text(result) -> str:
    for item in result.content:
        if hasattr(item, "text"):
            return item.text
    return ""


def _sum_orders(raw: str) -> tuple[Decimal, int]:
    """Parse order list and sum up order totals."""
    total = Decimal("0")
    count = 0
    try:
        data = json.loads(raw)
        orders = data if isinstance(data, list) else data.get("orders", [])
        for order in orders:
            amt = (
                order.get("order_total")
                or order.get("total")
                or order.get("amount")
                or order.get("bill_total")
                or 0
            )
            total += Decimal(str(amt))
            count += 1
    except Exception:
        pass
    return total, count
