"""
Repository layer — all database reads & writes plus analytics logic.

Every public function accepts a ``Session`` so callers (MCP tools *and* FastAPI
routes) share the same transactional model.
"""

from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy import func
from sqlmodel import Session, col, select

from .models import (
    AnalyticsResult,
    AnalyticsSummary,
    CuisineStats,
    DayDistribution,
    MonthlyTrend,
    Order,
    OrderCuisine,
    OrderItem,
    OrderOut,
    PeakHour,
    RestaurantStats,
    SyncResult,
    ItemOut,
)

logger = logging.getLogger(__name__)

_DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


# ---------------------------------------------------------------------------
# Write helpers
# ---------------------------------------------------------------------------

def upsert_orders(raw_orders: list[dict[str, Any]], session: Session) -> int:
    """
    Persist a batch of raw Swiggy API order dicts into SQLite.
    
    Uses UPSERT semantics (ON CONFLICT DO UPDATE) to handle duplicates.
    Parses and stores cuisines in the normalized order_cuisines table.
    
    Returns the count of *newly inserted* orders (duplicates are updated but not counted).
    """
    new_count = 0
    
    for raw in raw_orders:
        oid = str(raw.get("order_id", ""))
        if not oid:
            continue

        # Check if order already exists
        existing = session.get(Order, oid)
        is_new = existing is None

        # Parse order_time (Swiggy format: "YYYY-MM-DD HH:MM:SS" or similar)
        order_time_str = raw.get("order_time", "")
        order_time: datetime | None = None
        if order_time_str:
            try:
                # Replace 'T' with space if it's ISO, then take first 19 chars
                clean_time_str = order_time_str.replace("T", " ")[:19]
                order_time = datetime.strptime(clean_time_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                logger.warning(f"Failed to parse order_time: {order_time_str} for order {oid}")

        # Parse cuisines list
        cuisines = raw.get("restaurant_cuisine") or []
        
        # Create or update order
        if is_new:
            order = Order(
                order_id=oid,
                restaurant_id=str(raw.get("restaurant_id", "")),
                restaurant_name=raw.get("restaurant_name", ""),
                restaurant_locality=raw.get("restaurant_locality", ""),
                restaurant_city=raw.get("restaurant_city_name", ""),
                restaurant_cuisines=", ".join(cuisines),  # Keep denormalized for convenience
                order_time=order_time,
                order_total=float(raw.get("order_total", 0)),
                order_status=raw.get("order_status", "Delivered"),
                payment_method=raw.get("payment_method", ""),
                delivery_address=raw.get("delivery_address", {}).get("address", ""),
                order_discount=float(raw.get("order_discount", 0)),
                delivery_charge=float(raw.get("order_delivery_charge", 0)),
                gst=float(raw.get("order_tax", 0)),
                raw_json=json.dumps(raw),
            )
            session.add(order)
            new_count += 1
        else:
            # UPSERT: Update existing order with latest data
            existing.restaurant_id = str(raw.get("restaurant_id", ""))
            existing.restaurant_name = raw.get("restaurant_name", "")
            existing.restaurant_locality = raw.get("restaurant_locality", "")
            existing.restaurant_city = raw.get("restaurant_city_name", "")
            existing.restaurant_cuisines = ", ".join(cuisines)
            existing.order_time = order_time
            existing.order_total = float(raw.get("order_total", 0))
            existing.order_status = raw.get("order_status", "Delivered")
            existing.payment_method = raw.get("payment_method", "")
            existing.delivery_address = raw.get("delivery_address", {}).get("address", "")
            existing.order_discount = float(raw.get("order_discount", 0))
            existing.delivery_charge = float(raw.get("order_delivery_charge", 0))
            existing.gst = float(raw.get("order_tax", 0))
            existing.raw_json = json.dumps(raw)
            session.add(existing)

        # Handle order cuisines in normalized table
        # Delete existing cuisines for this order (to handle updates)
        if not is_new:
            stmt = select(OrderCuisine).where(OrderCuisine.order_id == oid)
            old_cuisines = session.exec(stmt).all()
            for old_cuisine in old_cuisines:
                session.delete(old_cuisine)
        
        # Insert cuisines into normalized table
        for cuisine in cuisines:
            cuisine_name = cuisine.strip()
            if cuisine_name:
                order_cuisine = OrderCuisine(
                    order_id=oid,
                    cuisine_name=cuisine_name,
                )
                session.add(order_cuisine)

        # Handle order items
        if is_new:
            # For new orders, insert all items
            for item_raw in raw.get("order_items") or []:
                item = OrderItem(
                    order_id=oid,
                    item_id=str(item_raw.get("item_id", "")),
                    name=item_raw.get("name", ""),
                    quantity=int(item_raw.get("quantity", 1)),
                    price=float(item_raw.get("total", 0)),
                    is_veg=item_raw.get("is_veg") in (True, 1, "1"),
                )
                session.add(item)
        else:
            # For updates, delete old items and insert new ones
            stmt = select(OrderItem).where(OrderItem.order_id == oid)
            old_items = session.exec(stmt).all()
            for old_item in old_items:
                session.delete(old_item)
            
            for item_raw in raw.get("order_items") or []:
                item = OrderItem(
                    order_id=oid,
                    item_id=str(item_raw.get("item_id", "")),
                    name=item_raw.get("name", ""),
                    quantity=int(item_raw.get("quantity", 1)),
                    price=float(item_raw.get("total", 0)),
                    is_veg=item_raw.get("is_veg") in (True, 1, "1"),
                )
                session.add(item)

    session.commit()
    return new_count


def get_sync_result(session: Session) -> SyncResult:
    """Build a SyncResult snapshot from current DB state."""
    total = _count_orders(session)
    first, last = _date_coverage(session)
    coverage = f"{first} to {last}" if first and last else "No data"
    return SyncResult(new_orders_fetched=0, total_orders_in_db=total, date_coverage=coverage)


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------

def get_orders(
    session: Session,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    restaurant_name: str | None = None,
    limit: int = 50,
) -> list[Order]:
    """
    Filtered & sorted order query.
    
    Implements date filtering using SQL BETWEEN on order_time.
    Implements restaurant_name filtering with case-insensitive LIKE.
    Returns Pydantic model instances (Order is a SQLModel which is also a Pydantic model).
    """
    stmt = select(Order)

    # Date filtering using BETWEEN clause when both dates are provided
    if start_date and end_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            stmt = stmt.where(col(Order.order_time).between(start_dt, end_dt))
        except ValueError:
            pass
    elif start_date:
        try:
            dt = datetime.strptime(start_date, "%Y-%m-%d")
            stmt = stmt.where(col(Order.order_time) >= dt)
        except ValueError:
            pass
    elif end_date:
        try:
            dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            stmt = stmt.where(col(Order.order_time) <= dt)
        except ValueError:
            pass
    
    # Case-insensitive LIKE for restaurant_name
    if restaurant_name:
        stmt = stmt.where(col(Order.restaurant_name).ilike(f"%{restaurant_name}%"))

    stmt = stmt.order_by(col(Order.order_time).desc()).limit(limit)
    return list(session.exec(stmt).all())


def get_orders_in_range(
    session: Session,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[Order]:
    """Return every order in an optional date range, newest first."""
    return _all_orders_in_range(session, start_date, end_date)


def search_orders(session: Session, query: str, *, limit: int = 20) -> list[Order]:
    """Case-insensitive search across restaurant name, cuisines, locality, AND item names."""
    pattern = f"%{query}%"
    
    # Subquery to find orders that have matching items
    item_matches = select(OrderItem.order_id).where(col(OrderItem.name).ilike(pattern))
    
    stmt = (
        select(Order)
        .where(
            col(Order.restaurant_name).ilike(pattern)
            | col(Order.restaurant_cuisines).ilike(pattern)
            | col(Order.restaurant_locality).ilike(pattern)
            | col(Order.order_id).in_(item_matches)
        )
        .order_by(col(Order.order_time).desc())
        .limit(limit)
    )
    return list(session.exec(stmt).all())


def get_restaurants(
    session: Session,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    min_orders: int = 1,
) -> list[RestaurantStats]:
    """Aggregate per-restaurant statistics."""
    orders = _all_orders_in_range(session, start_date, end_date)
    buckets: dict[str, dict[str, Any]] = {}

    for o in orders:
        name = o.restaurant_name or "Unknown"
        b = buckets.setdefault(name, {
            "total": 0.0,
            "count": 0,
            "cuisines": set(),
            "localities": set(),
            "first": o.order_time,
            "last": o.order_time,
        })
        b["count"] += 1
        b["total"] += o.order_total
        for c in o.cuisine_list:
            b["cuisines"].add(c)
        if o.restaurant_locality:
            b["localities"].add(o.restaurant_locality)
        if o.order_time:
            if b["first"] is None or o.order_time < b["first"]:
                b["first"] = o.order_time
            if b["last"] is None or o.order_time > b["last"]:
                b["last"] = o.order_time

    results: list[RestaurantStats] = []
    for name, b in buckets.items():
        if b["count"] < min_orders:
            continue
        results.append(RestaurantStats(
            name=name,
            order_count=b["count"],
            total_spent=round(b["total"], 2),
            avg_order_value=round(b["total"] / b["count"], 2) if b["count"] else 0,
            cuisines=sorted(b["cuisines"]),
            localities=sorted(b["localities"]),
            first_order=b["first"].strftime("%Y-%m-%d") if b["first"] else "",
            last_order=b["last"].strftime("%Y-%m-%d") if b["last"] else "",
        ))

    results.sort(key=lambda r: r.order_count, reverse=True)
    return results


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

def build_analytics(
    session: Session,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    analysis_type: str = "summary",
) -> AnalyticsResult:
    orders = _all_orders_in_range(session, start_date, end_date)

    if not orders:
        return AnalyticsResult(summary=AnalyticsSummary())

    total_spent = sum(o.order_total for o in orders)
    avg_val = round(total_spent / len(orders), 2) if orders else 0

    times = [o.order_time for o in orders if o.order_time]
    summary = AnalyticsSummary(
        total_orders=len(orders),
        total_spent=round(total_spent, 2),
        average_order_value=avg_val,
        first_order=min(times).strftime("%Y-%m-%d") if times else None,
        last_order=max(times).strftime("%Y-%m-%d") if times else None,
    )

    result = AnalyticsResult(summary=summary)

    if analysis_type == "spending":
        result.monthly_trends = _monthly_trends(orders)
    elif analysis_type == "timing":
        result.peak_hours = _peak_hours(orders)
        result.day_distribution = _day_distribution(orders)
    elif analysis_type == "restaurants":
        result.top_restaurants = get_restaurants(session, start_date=start_date, end_date=end_date)[:10]
    elif analysis_type == "cuisines":
        result.top_cuisines = _cuisine_breakdown(orders)

    return result


# ---------------------------------------------------------------------------
# Private analytics helpers
# ---------------------------------------------------------------------------

def _monthly_trends(orders: list[Order]) -> list[MonthlyTrend]:
    buckets: dict[str, dict[str, float | int]] = defaultdict(lambda: {"orders": 0, "spent": 0.0})
    for o in orders:
        if o.order_time:
            key = o.order_time.strftime("%Y-%m")
            buckets[key]["orders"] += 1
            buckets[key]["spent"] += o.order_total
    return sorted([
        MonthlyTrend(
            month=k,
            orders=int(v["orders"]),
            total_spent=round(v["spent"], 2),
            avg_order=round(v["spent"] / v["orders"], 2) if v["orders"] else 0,
        )
        for k, v in buckets.items()
    ], key=lambda m: m.month)


def _peak_hours(orders: list[Order]) -> list[PeakHour]:
    counter: Counter[int] = Counter()
    for o in orders:
        if o.order_time:
            counter[o.order_time.hour] += 1
    return [
        PeakHour(hour=f"{h:02d}:00", orders=c)
        for h, c in counter.most_common(5)
    ]


def _day_distribution(orders: list[Order]) -> list[DayDistribution]:
    counter: Counter[str] = Counter()
    for o in orders:
        if o.order_time:
            counter[_DAY_NAMES[o.order_time.weekday()]] += 1
    return [
        DayDistribution(day=d, orders=c)
        for d, c in counter.most_common()
    ]


def _cuisine_breakdown(orders: list[Order]) -> list[CuisineStats]:
    stats: dict[str, dict[str, float | int]] = defaultdict(lambda: {"orders": 0, "spent": 0.0})
    for o in orders:
        for cuisine in o.cuisine_list:
            stats[cuisine]["orders"] += 1
            stats[cuisine]["spent"] += o.order_total
    total = len(orders) or 1
    return sorted([
        CuisineStats(
            cuisine=k,
            orders=int(v["orders"]),
            total_spent=round(v["spent"], 2),
            avg_order=round(v["spent"] / v["orders"], 2) if v["orders"] else 0,
            percentage=round(v["orders"] / total * 100, 1),
        )
        for k, v in stats.items()
    ], key=lambda c: c.orders, reverse=True)


# ---------------------------------------------------------------------------
# Internal query helpers
# ---------------------------------------------------------------------------

def _all_orders_in_range(
    session: Session,
    start_date: str | None,
    end_date: str | None,
) -> list[Order]:
    """Unbounded query filtered only by optional date window."""
    stmt = select(Order)
    if start_date:
        try:
            dt = datetime.strptime(start_date, "%Y-%m-%d")
            stmt = stmt.where(col(Order.order_time) >= dt)
        except ValueError:
            pass
    if end_date:
        try:
            dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            stmt = stmt.where(col(Order.order_time) <= dt)
        except ValueError:
            pass
    stmt = stmt.order_by(col(Order.order_time).desc())
    return list(session.exec(stmt).all())


def _count_orders(session: Session) -> int:
    """Return total count of orders using efficient SQL COUNT."""
    stmt = select(func.count(Order.order_id))
    return session.exec(stmt).one()


def _date_coverage(session: Session) -> tuple[str | None, str | None]:
    """Return min and max order times using efficient SQL MIN/MAX."""
    stmt = select(func.min(Order.order_time), func.max(Order.order_time))
    min_time, max_time = session.exec(stmt).first() or (None, None)
    
    first = min_time.strftime("%Y-%m-%d") if min_time else None
    last = max_time.strftime("%Y-%m-%d") if max_time else None
    return first, last


# ---------------------------------------------------------------------------
# Convenience: Order → OrderOut
# ---------------------------------------------------------------------------

def to_order_out(order: Order, session: Session) -> OrderOut:
    # Query items directly since relationships are removed for SQLAlchemy 2.0 compatibility
    stmt = select(OrderItem).where(OrderItem.order_id == order.order_id)
    order_items = session.exec(stmt).all()
    
    items = [
        ItemOut(
            item_id=item.item_id,
            name=item.name,
            quantity=item.quantity,
            price=item.price,
            is_veg=item.is_veg,
        ) for item in order_items
    ]
    return OrderOut(
        order_id=order.order_id,
        restaurant_name=order.restaurant_name,
        restaurant_locality=order.restaurant_locality,
        restaurant_city=order.restaurant_city,
        cuisines=order.cuisine_list,
        order_time=order.order_time.strftime("%Y-%m-%d %H:%M:%S") if order.order_time else None,
        order_total=order.order_total,
        order_status=order.order_status,
        payment_method=order.payment_method,
        items=items,
    )
