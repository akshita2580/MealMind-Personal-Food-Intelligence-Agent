"""
FastMCP tool definitions for the Swiggy MCP server.

Each tool mirrors the original Node.js implementation but returns its
result as markdown-formatted text (the MCP convention for LLM consumption).

Cookies are accepted *only* by ``sync_orders`` as a runtime argument and
are never persisted to disk or database.
"""

import asyncio
from contextlib import contextmanager
import logging
from collections.abc import Generator
from typing import Any

from dotenv import load_dotenv
from fastmcp import FastMCP

from . import fetcher, repository
from .database import get_session
from .models import Order

# Load environment variables from .env file (requirement 13.3)
try:
    load_dotenv()
except Exception:
    pass  # .env file is optional

logger = logging.getLogger(__name__)

mcp = FastMCP(
    name="swiggy-orders",
    instructions=(
        "Swiggy Orders MCP Server — query your Swiggy food-delivery "
        "history, get analytics, and search past orders."
    ),
)


# -----------------------------------------------------------------------
# Tool 1 — sync_orders
# -----------------------------------------------------------------------

@mcp.tool()
def sync_orders(*, user_id: int) -> str:
    """
    Fetch orders from the Swiggy API and store them in the local database.

    Args:
        user_id: The authenticated user ID

    Returns:
        Markdown summary of the sync result.
    """
    from .models import SwiggyConnection
    from .security import decrypt_token
    from . import swiggy_mcp_client
    from sqlmodel import select

    try:
        with _session_scope() as session:
            conn = session.exec(select(SwiggyConnection).where(SwiggyConnection.user_id == user_id)).first()
            if not conn or conn.status != "CONNECTED" or not conn.access_token:
                return _format_error("Sync Failed", "No valid Swiggy connection found. Please connect your account first.")
                
            access_token = decrypt_token(conn.access_token)
            
        # Get addresses
        addresses = _run_async(swiggy_mcp_client.get_addresses, access_token)
        if not addresses:
            return _format_error("Sync Failed", "No supported Swiggy data is currently available (no addresses found).")
            
        address_id = None
        for addr in addresses:
            if isinstance(addr, dict):
                address_id = addr.get("id") or addr.get("addressId") or addr.get("address_id")
                if address_id:
                    break
                    
        if not address_id:
            return _format_error("Sync Failed", "No supported Swiggy data is currently available (no address ID).")
            
        # Get orders
        raw_orders = _run_async(swiggy_mcp_client.get_food_orders, access_token, str(address_id))
        if not raw_orders:
            return _format_error("Sync Failed", "No supported Swiggy data is currently available (no orders found).")

        with _session_scope() as session:
            new_count = repository.upsert_orders(raw_orders, session, user_id=user_id)
            result = repository.get_sync_result(session, user_id=user_id)
            result.new_orders_fetched = new_count

        return (
            "# Sync Complete\n\n"
            f"**New Orders Fetched**: {result.new_orders_fetched}\n"
            f"**Total Orders in Storage**: {result.total_orders_in_db}\n"
            f"**Date Coverage**: {result.date_coverage}\n\n"
            "Your Swiggy order data has been synchronised successfully!"
        )
    except Exception as exc:
        logger.exception("Unexpected MCP sync error: %s", type(exc).__name__)
        err_msg = str(exc).lower()
        if "http 401" in err_msg or "http 419" in err_msg:
            return _format_error("Authentication Error", "Your Swiggy connection was rejected (HTTP 401). Please reconnect.")
        return _format_error("Sync Failed", "An unexpected error occurred while syncing orders.")


# -----------------------------------------------------------------------
# Tool 2 — get_orders
# -----------------------------------------------------------------------

@mcp.tool()
def get_orders(
    start_date: str | None = None,
    end_date: str | None = None,
    restaurant_name: str | None = None,
    limit: int = 50,
    *,
    user_id: int,
) -> str:
    """
    Retrieve orders from local storage with optional filters.

    Args:
        start_date: Start date YYYY-MM-DD (optional).
        end_date: End date YYYY-MM-DD (optional).
        restaurant_name: Filter by restaurant name substring (optional).
        limit: Max orders to return (default 50).

    Returns:
        Markdown-formatted order list.
    """
    try:
        with _session_scope() as session:
            orders = repository.get_orders(
                session,
                user_id=user_id,
                start_date=start_date,
                end_date=end_date,
                restaurant_name=restaurant_name,
                limit=limit,
            )
            
            if not orders:
                return "No real Swiggy order data is currently available."
                
            total_spent = sum(o.order_total for o in orders)
            lines = _format_order_list(orders)

        return (
            "# Orders Retrieved\n\n"
            f"**Showing**: {len(orders)} orders\n"
            f"**Total Spent**: ₹{total_spent:.2f}\n"
            f"**Date Range**: {start_date or 'All'} to {end_date or 'All'}\n"
            + (f"**Restaurant Filter**: {restaurant_name}\n" if restaurant_name else "")
            + f"\n## Orders\n\n{lines}\n\n*Sorted by date (newest first)*"
        )
    except Exception as exc:
        logger.exception("MCP get_orders failed: %s", type(exc).__name__)
        return _format_error("Orders Query Failed", "Unable to retrieve orders right now.")


# -----------------------------------------------------------------------
# Tool 3 — get_restaurants
# -----------------------------------------------------------------------

@mcp.tool()
def get_restaurants(
    start_date: str | None = None,
    end_date: str | None = None,
    min_orders: int = 1,
    *,
    user_id: int,
) -> str:
    """
    List all restaurants with order counts and spending stats.

    Args:
        start_date: YYYY-MM-DD (optional).
        end_date: YYYY-MM-DD (optional).
        min_orders: Minimum orders to include a restaurant (default 1).

    Returns:
        Markdown-formatted restaurant list sorted by order count.
    """
    try:
        with _session_scope() as session:
            restaurants = repository.get_restaurants(session, user_id=user_id, start_date=start_date, end_date=end_date, min_orders=min_orders)
            
            if not restaurants:
                return "No real Swiggy order data is currently available."

            lines: list[str] = []
            for i, r in enumerate(restaurants, 1):
                cuisines = ", ".join(r.cuisines[:3]) + ("…" if len(r.cuisines) > 3 else "")
                localities = ", ".join(r.localities[:2]) + ("…" if len(r.localities) > 2 else "")
                lines.append(
                    f"{i}. **{r.name}**\n"
                    f"   📊 {r.order_count} orders • ₹{r.total_spent} total • ₹{r.avg_order_value} avg\n"
                    f"   🍽️ {cuisines}\n"
                    f"   📍 {localities}\n"
                    f"   📅 {r.first_order} → {r.last_order}\n"
                )

            return (
                f"# Restaurants List\n\n"
                f"**Total Restaurants**: {len(restaurants)}\n"
                f"**Minimum Orders**: {min_orders}\n"
                f"**Date Range**: {start_date or 'All'} to {end_date or 'All'}\n\n"
                f"## Restaurants (sorted by order count)\n\n"
                + "\n".join(lines)
            )
    except Exception as exc:
        logger.exception("MCP get_restaurants failed: %s", type(exc).__name__)
        return _format_error("Restaurant Query Failed", "Unable to retrieve restaurants right now.")



# -----------------------------------------------------------------------
# Tool 4 — get_analytics
# -----------------------------------------------------------------------

@mcp.tool()
def get_analytics(
    start_date: str | None = None,
    end_date: str | None = None,
    analysis_type: str = "summary",
    *,
    user_id: int,
) -> str:
    """
    Generate analytics from your stored Swiggy orders.

    Args:
        start_date: YYYY-MM-DD (optional).
        end_date: YYYY-MM-DD (optional).
        analysis_type: One of summary, spending, timing, restaurants, cuisines.

    Returns:
        Markdown-formatted analytics report.
    """
    try:
        with _session_scope() as session:
            result = repository.build_analytics(
                session,
                user_id=user_id,
                start_date=start_date,
                end_date=end_date,
                analysis_type=analysis_type,
            )
            
            if result.summary.total_orders == 0:
                return "No real Swiggy order data is currently available."
    except Exception as exc:
        logger.exception("MCP get_analytics failed: %s", type(exc).__name__)
        return _format_error("Analytics Failed", "Unable to generate analytics right now.")

    s = result.summary
    text = (
        f"# Analytics Report\n\n"
        f"**Analysis Type**: {analysis_type}\n"
        f"**Date Range**: {start_date or 'All'} to {end_date or 'All'}\n"
        f"**Orders Analysed**: {s.total_orders}\n\n"
        f"## Summary\n"
        f"- **Total Orders**: {s.total_orders}\n"
        f"- **Total Spent**: ₹{s.total_spent}\n"
        f"- **Average Order**: ₹{s.average_order_value}\n"
        f"- **Date Range**: {s.first_order or 'N/A'} to {s.last_order or 'N/A'}\n\n"
    )

    if result.monthly_trends:
        text += "## Monthly Spending Trends\n"
        for m in result.monthly_trends:
            text += f"- **{m.month}**: {m.orders} orders • ₹{m.total_spent} • ₹{m.avg_order} avg\n"
        text += "\n"

    if result.peak_hours:
        text += "## Peak Ordering Hours\n"
        for h in result.peak_hours:
            text += f"- **{h.hour}**: {h.orders} orders\n"
        text += "\n"

    if result.day_distribution:
        text += "## Day Distribution\n"
        for d in result.day_distribution:
            text += f"- **{d.day}**: {d.orders} orders\n"
        text += "\n"

    if result.top_restaurants:
        text += "## Top Restaurants\n"
        for i, r in enumerate(result.top_restaurants, 1):
            text += f"{i}. **{r.name}**: {r.order_count} orders • ₹{r.total_spent}\n"
        text += "\n"

    if result.top_cuisines:
        text += "## Top Cuisines\n"
        for i, c in enumerate(result.top_cuisines, 1):
            text += f"{i}. **{c.cuisine}**: {c.orders} orders ({c.percentage}%) • ₹{c.total_spent}\n"
        text += "\n"

    return text


# -----------------------------------------------------------------------
# Tool 5 — search_orders
# -----------------------------------------------------------------------

@mcp.tool()
def search_orders(
    query: str,
    limit: int = 20,
    *,
    user_id: int,
) -> str:
    """
    Search orders by restaurant name, cuisine, location, or item name.

    Args:
        query: Search term.
        limit: Max results to return (default 20).

    Returns:
        Markdown search results.
    """
    try:
        with _session_scope() as session:
            orders = repository.search_orders(session, query, user_id=user_id, limit=limit)
            lines = _format_order_list(orders)

        return (
            "# Search Results\n\n"
            f"**Query**: \"{query}\"\n"
            f"**Found**: {len(orders)} orders\n\n"
            f"## Results\n\n{lines}\n\n"
            "*Search performed across restaurant names, items, cuisines, and locations*"
        )
    except Exception as exc:
        logger.exception("MCP search_orders failed: %s", type(exc).__name__)
        return _format_error("Search Failed", "Unable to search orders right now.")


# -----------------------------------------------------------------------
# Tool 6 — get_food_insights
# -----------------------------------------------------------------------

@mcp.tool()
def get_food_insights(
    period: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    *,
    user_id: int,
) -> str:
    """
    Generate personalized food intelligence insights from your order history.

    Analyzes spending patterns, ordering behavior, restaurant loyalty,
    cuisine preferences, and repeat items to provide actionable insights
    about your food ordering habits.

    Args:
        start_date: Start date YYYY-MM-DD (optional).
        end_date: End date YYYY-MM-DD (optional).
        period: Natural period such as today, this week, or last month (optional).

    Returns:
        Markdown-formatted insights report with personalized recommendations.
    """
    from .services.insight_engine import build_food_insights_response

    try:
        with _session_scope() as session:
            response = build_food_insights_response(
                session,
                user_id=user_id,
                start_date=start_date,
                end_date=end_date,
                period=period,
            )
            insights = response.insights
    except Exception as exc:
        logger.exception("MCP get_food_insights failed: %s", type(exc).__name__)
        return _format_error("Insights Failed", "Unable to generate food insights right now.")

    period_label = response.period.get("label") or f"{start_date or 'All'} to {end_date or 'All'}"

    if response.total_orders == 0:
        return "No real Swiggy order data is currently available."

    if not insights:
        return (
            f"# Food Intelligence Insights\n\n"
            f"**Date Range**: {period_label}\n\n"
            f"No insights available yet. Sync more orders to enable analysis.\n"
        )

    # Check if insufficient data
    if len(insights) == 1 and insights[0].type == "INSUFFICIENT_DATA":
        insight = insights[0]
        return (
            f"# Food Intelligence Insights\n\n"
            f"**Date Range**: {period_label}\n"
            f"**Orders Analysed**: {response.total_orders}\n\n"
            f"## {insight.title}\n\n"
            f"{insight.message}\n"
        )

    # Group insights by category for better readability
    spending_insights = [i for i in insights if i.type.startswith("SPENDING_") or i.type == "RECORDED_SAVINGS"]
    behavior_insights = [i for i in insights if i.type in ("ORDER_FREQUENCY", "COMMON_DAY", "COMMON_HOUR", "WEEKDAY_WEEKEND", "MEAL_TIME_DISTRIBUTION", "LATE_NIGHT_ORDERING")]
    loyalty_insights = [i for i in insights if i.type in ("FAVORITE_RESTAURANT", "RESTAURANT_LOYALTY", "RESTAURANT_DIVERSITY")]
    cuisine_insights = [i for i in insights if i.type in ("FAVORITE_CUISINE", "CUISINE_DIVERSITY", "CUISINE_TREND")]
    food_insights = [i for i in insights if i.type in ("REPEAT_FOOD", "FAVORITE_ITEMS")]

    text = (
        f"# 🍽️ Food Intelligence Insights\n\n"
        f"**Date Range**: {period_label}\n"
        f"**Orders Analysed**: {response.total_orders}\n"
        f"**Total Insights**: {len(insights)}\n\n"
    )

    # Spending insights
    if spending_insights:
        text += "## 💰 Spending Patterns\n\n"
        for insight in spending_insights:
            emoji = _insight_emoji(insight.severity)
            text += f"{emoji} **{insight.title}**\n"
            text += f"   {insight.message}\n\n"

    # Behavior insights
    if behavior_insights:
        text += "## 📊 Ordering Behavior\n\n"
        for insight in behavior_insights:
            emoji = _insight_emoji(insight.severity)
            text += f"{emoji} **{insight.title}**\n"
            text += f"   {insight.message}\n\n"

    # Loyalty insights
    if loyalty_insights:
        text += "## ❤️ Restaurant Loyalty\n\n"
        for insight in loyalty_insights:
            emoji = _insight_emoji(insight.severity)
            text += f"{emoji} **{insight.title}**\n"
            text += f"   {insight.message}\n\n"

    # Cuisine insights
    if cuisine_insights:
        text += "## 🌶️ Cuisine Preferences\n\n"
        for insight in cuisine_insights:
            emoji = _insight_emoji(insight.severity)
            text += f"{emoji} **{insight.title}**\n"
            text += f"   {insight.message}\n\n"

    # Food item insights
    if food_insights:
        text += "## 🍔 Favorite Foods\n\n"
        for insight in food_insights:
            emoji = _insight_emoji(insight.severity)
            text += f"{emoji} **{insight.title}**\n"
            text += f"   {insight.message}\n\n"

    text += "*Insights are generated from your local order data and are updated with each sync.*\n"

    return text


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------

@contextmanager
def _session_scope() -> Generator[Any, None, None]:
    """Support both contextmanager sessions and generator fixtures in tests."""
    session_factory_result = get_session()
    if hasattr(session_factory_result, "__enter__"):
        with session_factory_result as session:
            yield session
        return

    try:
        session = next(session_factory_result)
    except StopIteration as exc:
        raise RuntimeError("Session generator did not yield a session") from exc

    try:
        yield session
    finally:
        try:
            next(session_factory_result)
        except StopIteration:
            pass


def _run_async(async_func: Any, *args: Any, **kwargs: Any) -> Any:
    """Run an async fetcher call from a synchronous MCP tool."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(async_func(*args, **kwargs))

    raise RuntimeError("sync_orders cannot be called synchronously inside a running event loop")


def _format_error(title: str, message: str) -> str:
    return f"# {title}\n\n**Error**: {message}\n"


def _format_order_list(orders: list[Order]) -> str:
    """Render a list of Order models as numbered markdown entries."""
    parts: list[str] = []
    for i, o in enumerate(orders, 1):
        cuisines = o.cuisine_list
        item_names = [f"{item.quantity}x {item.name}" for item in o.items] if o.items else []
        items_str = ", ".join(item_names) if item_names else "Unknown"
        parts.append(
            f"{i}. **{o.restaurant_name or 'Unknown'}**\n"
            f"   📅 {o.order_time.strftime('%b %d %Y, %H:%M') if o.order_time else 'Unknown'}\n"
            f"   💰 ₹{o.order_total}\n"
            f"   📍 {o.restaurant_locality or o.restaurant_city or 'Unknown'}\n"
            f"   📦 {items_str}\n"
        )
    return "\n".join(parts) if parts else "*No orders found.*"


def _insight_emoji(severity: str) -> str:
    """Map insight severity to an appropriate emoji."""
    severity_map = {
        "INFO": "ℹ️",
        "SUCCESS": "✅",
        "WARNING": "⚠️",
        "ALERT": "🚨",
    }
    return severity_map.get(severity, "ℹ️")
