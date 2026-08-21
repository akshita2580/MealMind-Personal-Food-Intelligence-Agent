from __future__ import annotations

from datetime import date

import pytest
from sqlmodel import SQLModel, Session, create_engine

from src.repository import upsert_orders
from src.services.insight_engine import (
    DataThresholds,
    build_food_insights_response,
    generate_food_insights,
    resolve_insight_period,
)


@pytest.fixture
def session():
    from sqlalchemy.pool import StaticPool
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    try:
        with Session(engine) as db_session:
            yield db_session
    finally:
        engine.dispose()


def _raw_order(
    idx: int,
    *,
    when: str,
    total: float = 300.0,
    restaurant: str = "Test Kitchen",
    cuisines: list[str] | None = None,
    item_name: str | None = None,
    discount: float = 0.0,
) -> dict:
    return {
        "order_id": f"order_{idx}",
        "order_time": when,
        "order_total": total,
        "restaurant_id": f"restaurant_{restaurant.lower().replace(' ', '_')}",
        "restaurant_name": restaurant,
        "restaurant_locality": "Indiranagar",
        "restaurant_city_name": "Bangalore",
        "restaurant_cuisine": cuisines or ["Indian"],
        "order_status": "Delivered",
        "payment_method": "Card",
        "delivery_address": {"address": "123 Test Street"},
        "order_discount": discount,
        "order_delivery_charge": 30.0,
        "order_tax": 20.0,
        "order_items": [
            {
                "item_id": f"item_{idx}",
                "name": item_name or f"Dish {idx}",
                "quantity": 1,
                "total": total,
                "is_veg": True,
            }
        ],
    }


def _seed_baseline_orders(session: Session) -> None:
    orders = []
    for idx in range(1, 21):
        is_february = idx > 10
        day = idx if idx <= 10 else idx - 10
        restaurant = "Domino's" if idx <= 8 else f"Restaurant {idx}"
        cuisines = ["Pizza", "Italian"] if idx <= 8 else ["North Indian"]
        item_name = "Chicken Biryani" if idx in {1, 2, 3, 4} else f"Dish {idx}"
        orders.append(
            _raw_order(
                idx,
                when=f"2024-{'02' if is_february else '01'}-{day:02d} 13:00:00",
                total=200.0 if not is_february else 300.0,
                restaurant=restaurant,
                cuisines=cuisines,
                item_name=item_name,
                discount=25.0 if idx <= 5 else 0.0,
            )
        )
    upsert_orders(orders, session, user_id=1)


def _types(insights) -> set[str]:
    return {insight.type for insight in insights}


def test_empty_database_returns_insufficient_data(session: Session) -> None:
    insights = generate_food_insights(session, user_id=1)

    assert len(insights) == 1
    assert insights[0].type == "INSUFFICIENT_DATA"
    assert insights[0].supporting_data["current_orders"] == 0


def test_insufficient_data_threshold(session: Session) -> None:
    orders = [
        _raw_order(idx, when=f"2024-01-0{idx} 12:00:00")
        for idx in range(1, DataThresholds.MIN_ORDERS_FOR_PATTERNS)
    ]
    upsert_orders(orders, session, user_id=1)

    insights = generate_food_insights(session, user_id=1)

    assert len(insights) == 1
    assert insights[0].type == "INSUFFICIENT_DATA"
    assert insights[0].value == DataThresholds.MIN_ORDERS_FOR_PATTERNS - 1


def test_spending_trend_and_date_filtering(session: Session) -> None:
    _seed_baseline_orders(session)

    all_insights = generate_food_insights(session, user_id=1)
    assert "SPENDING_TREND" in _types(all_insights)

    trend = next(insight for insight in all_insights if insight.type == "SPENDING_TREND")
    assert trend.value == 50.0
    assert trend.supporting_data["prev_month"] == "2024-01"
    assert trend.supporting_data["last_month"] == "2024-02"

    january = build_food_insights_response(
        session,
        start_date="2024-01-01",
        end_date="2024-01-31",
    )
    assert january.total_orders == 10
    assert january.period == {
        "start": "2024-01-01",
        "end": "2024-01-31",
        "label": "2024-01-01 to 2024-01-31",
    }
    total = next(insight for insight in january.insights if insight.type == "SPENDING_TOTAL")
    assert total.value == 2000.0


def test_restaurant_preference(session: Session) -> None:
    _seed_baseline_orders(session)

    insights = generate_food_insights(session, user_id=1)
    favorite = next(insight for insight in insights if insight.type == "FAVORITE_RESTAURANT")

    assert favorite.supporting_data["restaurant"] == "Domino's"
    assert favorite.value == 8
    assert favorite.supporting_data["percentage"] == 40.0
    assert favorite.supporting_data["avg_order_value"] == 200.0


def test_cuisine_preference_and_trend(session: Session) -> None:
    orders = []
    for idx in range(1, 17):
        is_february = idx > 8
        day = idx if idx <= 8 else idx - 8
        orders.append(
            _raw_order(
                idx,
                when=f"2024-{'02' if is_february else '01'}-{day:02d} 12:30:00",
                restaurant=f"Restaurant {idx}",
                cuisines=["Pizza"] if not is_february else ["Chinese"],
            )
        )
    upsert_orders(orders, session, user_id=1)

    insights = generate_food_insights(session, user_id=1)

    assert "FAVORITE_CUISINE" in _types(insights)
    trend = next(insight for insight in insights if insight.type == "CUISINE_TREND")
    assert trend.title == "Cuisine Preference Shift"
    assert trend.supporting_data["previous_month_top_cuisine"] == "Pizza"
    assert trend.supporting_data["last_month_top_cuisine"] == "Chinese"


def test_ordering_time_behavior(session: Session) -> None:
    orders = [
        _raw_order(idx, when=f"2024-01-{idx:02d} 13:00:00")
        for idx in range(1, 15)
    ]
    upsert_orders(orders, session, user_id=1)

    insights = generate_food_insights(session, user_id=1)

    common_hour = next(insight for insight in insights if insight.type == "COMMON_HOUR")
    meal_time = next(insight for insight in insights if insight.type == "MEAL_TIME_DISTRIBUTION")

    assert common_hour.value == 13
    assert common_hour.supporting_data["meal_period"] == "lunch"
    assert meal_time.supporting_data["dominant_meal"] == "lunch"


def test_repeat_items_and_natural_period_resolution(session: Session) -> None:
    _seed_baseline_orders(session)

    insights = generate_food_insights(session, user_id=1)
    favorite_item = next(insight for insight in insights if insight.type == "FAVORITE_ITEMS")

    assert favorite_item.supporting_data["item_name"] == "chicken biryani"
    assert favorite_item.value == 4

    period = resolve_insight_period(period="last month", today=date(2024, 3, 15))
    assert period.start_date == "2024-02-01"
    assert period.end_date == "2024-02-29"
    assert period.label == "last month"
