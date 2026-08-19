"""
Food Intelligence / Insight Engine

Analyzes locally stored Swiggy order data to generate personalized,
actionable insights about food ordering behavior, spending patterns,
and preferences.

This module is designed to be:
- Deterministic and explainable (no black-box AI)
- Data-quality aware (enforces minimum thresholds)
- Reusable across MCP tools, REST APIs, and future features
- Foundation for the future proactive lunchtime assistant

Architecture:
    Database → Repository → Insight Engine → MCP/REST → Future AI/Frontend

The Insight Engine NEVER:
- Directly calls Swiggy API
- Requires or stores cookies
- Makes network requests
- Accesses external services

It ONLY analyzes existing local order data.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field
from sqlmodel import Session

from .. import repository
from ..models import InsightResponse, InsightsListResponse, Order

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Minimum Data Thresholds
# ---------------------------------------------------------------------------

class DataThresholds:
    """
    Minimum data requirements for generating reliable insights.
    
    These thresholds prevent misleading conclusions from insufficient data.
    """
    
    # Minimum orders required for pattern-based insights
    MIN_ORDERS_FOR_PATTERNS = 10
    
    # Minimum orders required for spending trends
    MIN_ORDERS_FOR_TRENDS = 5
    
    # Minimum orders required for restaurant loyalty
    MIN_ORDERS_FOR_LOYALTY = 8
    
    # Minimum orders required for cuisine preferences
    MIN_ORDERS_FOR_CUISINE = 7
    
    # Minimum orders required for day-of-week patterns
    MIN_ORDERS_FOR_DAY_PATTERN = 14  # At least 2 weeks
    
    # Minimum orders required for hour-of-day patterns
    MIN_ORDERS_FOR_HOUR_PATTERN = 10
    
    # Minimum orders required for late-night insights
    MIN_ORDERS_FOR_LATE_NIGHT = 5
    
    # Minimum orders per restaurant for loyalty insights
    MIN_ORDERS_PER_RESTAURANT = 3
    
    # Minimum orders with items for repeat food insights
    MIN_ORDERS_FOR_REPEAT_ITEMS = 8
    
    # Minimum occurrences of an item to be considered "repeated"
    MIN_ITEM_OCCURRENCES = 3
    
    # Months needed for trend comparison
    MIN_MONTHS_FOR_COMPARISON = 2

    # Minimum discounted orders before reporting savings patterns
    MIN_DISCOUNTED_ORDERS = 3


# ---------------------------------------------------------------------------
# Insight Types and Severity
# ---------------------------------------------------------------------------

class InsightType(str, Enum):
    """Categories of insights that can be generated."""
    
    # Spending insights
    SPENDING_TOTAL = "SPENDING_TOTAL"
    SPENDING_AVERAGE = "SPENDING_AVERAGE"
    SPENDING_TREND = "SPENDING_TREND"
    SPENDING_PEAK_MONTH = "SPENDING_PEAK_MONTH"
    SPENDING_LOW_MONTH = "SPENDING_LOW_MONTH"
    RECORDED_SAVINGS = "RECORDED_SAVINGS"
    
    # Ordering behavior
    ORDER_FREQUENCY = "ORDER_FREQUENCY"
    COMMON_DAY = "COMMON_DAY"
    COMMON_HOUR = "COMMON_HOUR"
    WEEKDAY_WEEKEND = "WEEKDAY_WEEKEND"
    MEAL_TIME_DISTRIBUTION = "MEAL_TIME_DISTRIBUTION"
    LATE_NIGHT_ORDERING = "LATE_NIGHT_ORDERING"
    
    # Restaurant loyalty
    FAVORITE_RESTAURANT = "FAVORITE_RESTAURANT"
    RESTAURANT_LOYALTY = "RESTAURANT_LOYALTY"
    RESTAURANT_DIVERSITY = "RESTAURANT_DIVERSITY"
    
    # Cuisine preferences
    FAVORITE_CUISINE = "FAVORITE_CUISINE"
    CUISINE_DIVERSITY = "CUISINE_DIVERSITY"
    CUISINE_TREND = "CUISINE_TREND"
    
    # Repeat food items
    REPEAT_FOOD = "REPEAT_FOOD"
    FAVORITE_ITEMS = "FAVORITE_ITEMS"
    
    # Data quality
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass(frozen=True)
class ResolvedInsightPeriod:
    """Canonical date range used by the insight engine and interfaces."""

    start_date: str | None
    end_date: str | None
    label: str
    requested_period: str | None = None


_NATURAL_PERIODS = {
    "today",
    "yesterday",
    "this week",
    "last week",
    "this month",
    "last month",
}


def resolve_insight_period(
    start_date: str | None = None,
    end_date: str | None = None,
    period: str | None = None,
    *,
    today: date | None = None,
) -> ResolvedInsightPeriod:
    """
    Resolve explicit dates or supported natural periods to YYYY-MM-DD strings.

    Supported natural periods: today, yesterday, this week, last week,
    this month, last month. Explicit start/end dates must use YYYY-MM-DD.
    """
    reference = today or date.today()

    if period and (start_date or end_date):
        raise ValueError("Use either period or start_date/end_date, not both")

    requested_period = period
    if start_date and not end_date and start_date.strip().lower() in _NATURAL_PERIODS:
        requested_period = start_date
        start_date = None

    if requested_period:
        start, end = _resolve_natural_period(requested_period, reference)
        label = requested_period.strip().lower()
        return ResolvedInsightPeriod(
            start_date=start.isoformat(),
            end_date=end.isoformat(),
            label=label,
            requested_period=label,
        )

    start = _parse_iso_date(start_date, "start_date") if start_date else None
    end = _parse_iso_date(end_date, "end_date") if end_date else None

    if start and end and start > end:
        raise ValueError("start_date must be on or before end_date")

    return ResolvedInsightPeriod(
        start_date=start.isoformat() if start else None,
        end_date=end.isoformat() if end else None,
        label=_format_period(start.isoformat() if start else None, end.isoformat() if end else None),
    )


def _resolve_natural_period(period: str, reference: date) -> tuple[date, date]:
    normalized = period.strip().lower()
    if normalized not in _NATURAL_PERIODS:
        supported = ", ".join(sorted(_NATURAL_PERIODS))
        raise ValueError(f"Unsupported period '{period}'. Supported periods: {supported}")

    if normalized == "today":
        return reference, reference
    if normalized == "yesterday":
        yesterday = reference - timedelta(days=1)
        return yesterday, yesterday
    if normalized == "this week":
        start = reference - timedelta(days=reference.weekday())
        return start, reference
    if normalized == "last week":
        this_week_start = reference - timedelta(days=reference.weekday())
        start = this_week_start - timedelta(days=7)
        end = this_week_start - timedelta(days=1)
        return start, end
    if normalized == "this month":
        return reference.replace(day=1), reference

    first_this_month = reference.replace(day=1)
    last_prev_month = first_this_month - timedelta(days=1)
    first_prev_month = last_prev_month.replace(day=1)
    return first_prev_month, last_prev_month


def _parse_iso_date(value: str, param_name: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(
            f"Invalid date format for {param_name}: expected YYYY-MM-DD, got '{value}'"
        ) from exc


def _format_period(start_date: str | None, end_date: str | None) -> str:
    """Format a date range for insight messages."""
    if start_date and end_date:
        return f"{start_date} to {end_date}"
    if start_date:
        return f"from {start_date}"
    if end_date:
        return f"until {end_date}"
    return "all-time"


class InsightSeverity(str, Enum):
    """Severity/importance level of an insight."""
    
    INFO = "INFO"           # Informational, neutral
    SUCCESS = "SUCCESS"     # Positive behavior
    WARNING = "WARNING"     # Potential concern
    ALERT = "ALERT"         # Significant pattern requiring attention


# ---------------------------------------------------------------------------
# Insight Data Model
# ---------------------------------------------------------------------------

class Insight(BaseModel):
    """
    Structured insight object returned by the Insight Engine.
    
    Designed to be:
    - Type-safe (Pydantic validated)
    - Serializable (for REST API JSON responses)
    - Readable (for MCP markdown responses)
    - Extensible (supporting_data for context)
    - Future-proof (suitable for notifications, dashboards, AI prompts)
    """
    
    type: InsightType = Field(..., description="Type of insight")
    severity: InsightSeverity = Field(..., description="Importance level")
    title: str = Field(..., description="Short summary (< 60 chars)")
    message: str = Field(..., description="Detailed explanation")
    value: float | int | str | None = Field(None, description="Primary metric")
    unit: str | None = Field(None, description="Unit of measurement (%, orders, ₹, etc.)")
    period: str | None = Field(None, description="Time period (monthly, weekly, all-time)")
    supporting_data: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context for future use"
    )
    
    class Config:
        use_enum_values = True


# ---------------------------------------------------------------------------
# Insight Engine Core
# ---------------------------------------------------------------------------

class InsightEngine:
    """
    Main insight generation engine.
    
    Analyzes order data and generates structured insights using
    deterministic, explainable algorithms.
    """
    
    def __init__(self, session: Session, user_id: int | None = None):
        """
        Initialize the insight engine with a database session.
        
        Args:
            session: SQLModel session for database access
            user_id: FoodIQ user ID to scope insights to (required for user-facing calls)
        """
        self.session = session
        self.user_id = user_id
    
    def generate_all_insights(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        period: str | None = None,
        *,
        today: date | None = None,
    ) -> list[Insight]:
        """
        Generate all applicable insights for the given date range.
        
        Args:
            start_date: Start date YYYY-MM-DD (optional)
            end_date: End date YYYY-MM-DD (optional)
            period: Natural period such as "this month" (optional)
        
        Returns:
            List of Insight objects, empty if insufficient data
        """
        insights: list[Insight] = []
        resolved_period = resolve_insight_period(start_date, end_date, period, today=today)
        
        # Get all orders in range (reuse existing repository method)
        orders = repository.get_orders_in_range(
            self.session,
            user_id=self.user_id,
            start_date=resolved_period.start_date,
            end_date=resolved_period.end_date,
        )
        
        # Check minimum data threshold
        if len(orders) < DataThresholds.MIN_ORDERS_FOR_PATTERNS:
            return [self._insufficient_data_insight(len(orders))]
        
        # Generate insights by category
        insights.extend(self._generate_spending_insights(orders, resolved_period))
        insights.extend(self._generate_behavior_insights(orders))
        insights.extend(self._generate_loyalty_insights(orders, resolved_period.label))
        insights.extend(self._generate_cuisine_insights(orders, resolved_period.label))
        insights.extend(self._generate_repeat_food_insights(orders, resolved_period.label))
        insights.extend(self._generate_late_night_insights(orders, resolved_period.label))
        
        return insights
    
    def _find_lowest_spending_month(self, orders: list[Order]) -> Insight | None:
        """Find the lowest spending month when multiple months exist."""
        monthly_data = repository._monthly_trends(orders)

        if len(monthly_data) < DataThresholds.MIN_MONTHS_FOR_COMPARISON:
            return None

        low = min(monthly_data, key=lambda m: m.total_spent)

        return Insight(
            type=InsightType.SPENDING_LOW_MONTH,
            severity=InsightSeverity.INFO,
            title="Lowest Spending Month",
            message=(
                f"You spent the least in {low.month} with INR {low.total_spent:.2f} "
                f"across {low.orders} orders."
            ),
            value=round(low.total_spent, 2),
            unit="INR",
            period=low.month,
            supporting_data={
                "month": low.month,
                "orders": low.orders,
                "avg_order": low.avg_order,
            },
        )

    # -----------------------------------------------------------------------
    # Spending Insights
    # -----------------------------------------------------------------------
    
    def _generate_spending_insights(
        self,
        orders: list[Order],
        period: ResolvedInsightPeriod,
    ) -> list[Insight]:
        """Generate spending-related insights."""
        insights: list[Insight] = []
        
        if len(orders) < DataThresholds.MIN_ORDERS_FOR_TRENDS:
            return insights
        
        total_spent = sum(o.order_total for o in orders)
        avg_order = total_spent / len(orders) if orders else 0
        
        # Total spending
        insights.append(Insight(
            type=InsightType.SPENDING_TOTAL,
            severity=InsightSeverity.INFO,
            title="Total Food Spending",
            message=f"You've spent ₹{total_spent:.2f} on {len(orders)} orders.",
            value=round(total_spent, 2),
            unit="₹",
            period=period.label,
            supporting_data={
                "order_count": len(orders),
                "start_date": period.start_date,
                "end_date": period.end_date,
            }
        ))
        
        # Average order value
        insights.append(Insight(
            type=InsightType.SPENDING_AVERAGE,
            severity=InsightSeverity.INFO,
            title="Average Order Value",
            message=f"Your average order value is ₹{avg_order:.2f}.",
            value=round(avg_order, 2),
            unit="₹",
            period=period.label,
            supporting_data={"total_orders": len(orders)}
        ))
        
        savings_insight = self._calculate_recorded_savings(orders, period.label)
        if savings_insight:
            insights.append(savings_insight)
        
        # Spending trend (if enough historical data)
        trend_insight = self._calculate_spending_trend(orders)
        if trend_insight:
            insights.append(trend_insight)
        
        # Peak spending month
        peak_month_insight = self._find_peak_spending_month(orders)
        if peak_month_insight:
            insights.append(peak_month_insight)
        
        low_month_insight = self._find_lowest_spending_month(orders)
        if low_month_insight:
            insights.append(low_month_insight)
        
        return insights
    
    def _calculate_spending_trend(self, orders: list[Order]) -> Insight | None:
        """Calculate spending trend by comparing periods."""
        # Reuse existing monthly_trends calculation
        monthly_data = repository._monthly_trends(orders)
        
        if len(monthly_data) < DataThresholds.MIN_MONTHS_FOR_COMPARISON:
            return None
        
        # Compare last month vs previous month
        if len(monthly_data) >= 2:
            last_month = monthly_data[-1]
            prev_month = monthly_data[-2]
            
            change = last_month.total_spent - prev_month.total_spent
            pct_change = (change / prev_month.total_spent * 100) if prev_month.total_spent > 0 else 0
            
            if abs(pct_change) < 5:  # Less than 5% change is stable
                return Insight(
                    type=InsightType.SPENDING_TREND,
                    severity=InsightSeverity.INFO,
                    title="Stable Spending",
                    message=f"Your spending remained stable at ~₹{last_month.total_spent:.0f}/month.",
                    value=round(pct_change, 1),
                    unit="%",
                    period="monthly",
                    supporting_data={
                        "last_month": last_month.month,
                        "last_month_spent": last_month.total_spent,
                        "prev_month": prev_month.month,
                        "prev_month_spent": prev_month.total_spent,
                    }
                )
            elif pct_change > 0:
                severity = InsightSeverity.WARNING if pct_change > 25 else InsightSeverity.INFO
                return Insight(
                    type=InsightType.SPENDING_TREND,
                    severity=severity,
                    title="Spending Increased",
                    message=f"Your food spending increased by {abs(pct_change):.0f}% compared to the previous month.",
                    value=round(pct_change, 1),
                    unit="%",
                    period="monthly",
                    supporting_data={
                        "last_month": last_month.month,
                        "last_month_spent": last_month.total_spent,
                        "prev_month": prev_month.month,
                        "prev_month_spent": prev_month.total_spent,
                    }
                )
            else:  # Negative change
                return Insight(
                    type=InsightType.SPENDING_TREND,
                    severity=InsightSeverity.SUCCESS,
                    title="Spending Decreased",
                    message=f"Your food spending decreased by {abs(pct_change):.0f}% compared to the previous month.",
                    value=round(pct_change, 1),
                    unit="%",
                    period="monthly",
                    supporting_data={
                        "last_month": last_month.month,
                        "last_month_spent": last_month.total_spent,
                        "prev_month": prev_month.month,
                        "prev_month_spent": prev_month.total_spent,
                    }
                )
        
        return None

    def _calculate_recorded_savings(
        self,
        orders: list[Order],
        period_label: str,
    ) -> Insight | None:
        """Report savings only when recorded discount data is present."""
        discounted_orders = [o for o in orders if (o.order_discount or 0) > 0]
        if len(discounted_orders) < DataThresholds.MIN_DISCOUNTED_ORDERS:
            return None

        total_saved = sum(o.order_discount for o in discounted_orders)
        pct_orders_discounted = len(discounted_orders) / len(orders) * 100 if orders else 0

        return Insight(
            type=InsightType.RECORDED_SAVINGS,
            severity=InsightSeverity.SUCCESS,
            title="Recorded Order Savings",
            message=(
                f"Discount data is present for {len(discounted_orders)} orders; "
                f"recorded savings total INR {total_saved:.2f}."
            ),
            value=round(total_saved, 2),
            unit="INR",
            period=period_label,
            supporting_data={
                "discounted_orders": len(discounted_orders),
                "discounted_order_percentage": round(pct_orders_discounted, 1),
            },
        )
    
    def _find_peak_spending_month(self, orders: list[Order]) -> Insight | None:
        """Find the month with highest spending."""
        monthly_data = repository._monthly_trends(orders)
        
        if not monthly_data:
            return None
        
        peak = max(monthly_data, key=lambda m: m.total_spent)
        
        return Insight(
            type=InsightType.SPENDING_PEAK_MONTH,
            severity=InsightSeverity.INFO,
            title="Highest Spending Month",
            message=f"You spent the most in {peak.month} with ₹{peak.total_spent:.2f} across {peak.orders} orders.",
            value=round(peak.total_spent, 2),
            unit="₹",
            period=peak.month,
            supporting_data={
                "month": peak.month,
                "orders": peak.orders,
                "avg_order": peak.avg_order,
            }
        )
    
    # -----------------------------------------------------------------------
    # Ordering Behavior Insights
    # -----------------------------------------------------------------------
    
    def _generate_behavior_insights(self, orders: list[Order]) -> list[Insight]:
        """Generate ordering behavior insights."""
        insights: list[Insight] = []
        
        if len(orders) < DataThresholds.MIN_ORDERS_FOR_PATTERNS:
            return insights
        
        # Order frequency
        orders_with_time = [o for o in orders if o.order_time]
        if orders_with_time and len(orders_with_time) >= 2:
            first_date = min(o.order_time for o in orders_with_time)
            last_date = max(o.order_time for o in orders_with_time)
            days_span = (last_date - first_date).days + 1
            orders_per_week = (len(orders) / days_span * 7) if days_span > 0 else 0
            
            insights.append(Insight(
                type=InsightType.ORDER_FREQUENCY,
                severity=InsightSeverity.INFO,
                title="Ordering Frequency",
                message=f"You order food approximately {orders_per_week:.1f} times per week.",
                value=round(orders_per_week, 1),
                unit="orders/week",
                period=self._format_date_range(first_date, last_date),
                supporting_data={
                    "total_orders": len(orders),
                    "days_span": days_span,
                    "orders_per_day": round(len(orders) / days_span, 2) if days_span > 0 else 0,
                }
            ))
        
        # Most common day
        if len(orders) >= DataThresholds.MIN_ORDERS_FOR_DAY_PATTERN:
            day_insight = self._find_common_day(orders)
            if day_insight:
                insights.append(day_insight)
        
        # Most common hour
        if len(orders) >= DataThresholds.MIN_ORDERS_FOR_HOUR_PATTERN:
            hour_insight = self._find_common_hour(orders)
            if hour_insight:
                insights.append(hour_insight)
        
        # Weekday vs weekend
        weekend_insight = self._analyze_weekday_weekend(orders)
        if weekend_insight:
            insights.append(weekend_insight)
        
        # Meal time distribution
        meal_insight = self._analyze_meal_times(orders)
        if meal_insight:
            insights.append(meal_insight)
        
        return insights
    
    def _find_common_day(self, orders: list[Order]) -> Insight | None:
        """Find the most common day of week for ordering."""
        _DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        
        day_counter: Counter[str] = Counter()
        for o in orders:
            if o.order_time:
                day_counter[_DAY_NAMES[o.order_time.weekday()]] += 1
        
        if not day_counter:
            return None
        
        most_common_day, count = day_counter.most_common(1)[0]
        percentage = (count / len(orders) * 100) if orders else 0
        
        return Insight(
            type=InsightType.COMMON_DAY,
            severity=InsightSeverity.INFO,
            title=f"You Order Most on {most_common_day}s",
            message=f"{most_common_day} is your most common ordering day with {count} orders ({percentage:.0f}%).",
            value=count,
            unit="orders",
            period="weekly",
            supporting_data={
                "day": most_common_day,
                "percentage": round(percentage, 1),
                "all_days": {day: count for day, count in day_counter.items()},
            }
        )
    
    def _find_common_hour(self, orders: list[Order]) -> Insight | None:
        """Find the most common hour of day for ordering."""
        hour_counter: Counter[int] = Counter()
        for o in orders:
            if o.order_time:
                hour_counter[o.order_time.hour] += 1
        
        if not hour_counter:
            return None
        
        most_common_hour, count = hour_counter.most_common(1)[0]
        percentage = (count / len(orders) * 100) if orders else 0
        
        # Determine meal period
        if 6 <= most_common_hour < 11:
            meal_period = "breakfast"
        elif 11 <= most_common_hour < 16:
            meal_period = "lunch"
        elif 16 <= most_common_hour < 21:
            meal_period = "dinner"
        else:
            meal_period = "late-night"
        
        return Insight(
            type=InsightType.COMMON_HOUR,
            severity=InsightSeverity.INFO,
            title=f"Peak Ordering Hour: {most_common_hour:02d}:00",
            message=f"You order most frequently around {most_common_hour:02d}:00 ({meal_period}) with {count} orders ({percentage:.0f}%).",
            value=most_common_hour,
            unit="hour",
            period="daily",
            supporting_data={
                "hour": most_common_hour,
                "count": count,
                "percentage": round(percentage, 1),
                "meal_period": meal_period,
            }
        )
    
    def _analyze_weekday_weekend(self, orders: list[Order]) -> Insight | None:
        """Analyze weekday vs weekend ordering patterns."""
        weekday_count = 0
        weekend_count = 0
        
        for o in orders:
            if o.order_time:
                # 5=Saturday, 6=Sunday
                if o.order_time.weekday() in (5, 6):
                    weekend_count += 1
                else:
                    weekday_count += 1
        
        total = weekday_count + weekend_count
        if total == 0:
            return None
        
        weekend_pct = (weekend_count / total * 100)
        weekday_pct = (weekday_count / total * 100)
        
        if weekend_pct > 60:
            return Insight(
                type=InsightType.WEEKDAY_WEEKEND,
                severity=InsightSeverity.INFO,
                title="Weekend Ordering Pattern",
                message=f"You place {weekend_pct:.0f}% of your orders on weekends.",
                value=round(weekend_pct, 1),
                unit="%",
                period="weekly",
                supporting_data={
                    "weekend_orders": weekend_count,
                    "weekday_orders": weekday_count,
                    "weekend_percentage": round(weekend_pct, 1),
                    "weekday_percentage": round(weekday_pct, 1),
                }
            )
        elif weekday_pct > 60:
            return Insight(
                type=InsightType.WEEKDAY_WEEKEND,
                severity=InsightSeverity.INFO,
                title="Weekday Ordering Pattern",
                message=f"You place {weekday_pct:.0f}% of your orders on weekdays.",
                value=round(weekday_pct, 1),
                unit="%",
                period="weekly",
                supporting_data={
                    "weekend_orders": weekend_count,
                    "weekday_orders": weekday_count,
                    "weekend_percentage": round(weekend_pct, 1),
                    "weekday_percentage": round(weekday_pct, 1),
                }
            )
        else:
            return Insight(
                type=InsightType.WEEKDAY_WEEKEND,
                severity=InsightSeverity.INFO,
                title="Balanced Weekday/Weekend Ordering",
                message=f"Your orders are fairly balanced: {weekday_pct:.0f}% weekdays, {weekend_pct:.0f}% weekends.",
                value=50,
                unit="%",
                period="weekly",
                supporting_data={
                    "weekend_orders": weekend_count,
                    "weekday_orders": weekday_count,
                    "weekend_percentage": round(weekend_pct, 1),
                    "weekday_percentage": round(weekday_pct, 1),
                }
            )
    
    def _analyze_meal_times(self, orders: list[Order]) -> Insight | None:
        """Analyze breakfast, lunch, dinner, and late-night ordering distribution."""
        breakfast = 0  # 6-11
        lunch = 0      # 11-16
        dinner = 0     # 16-21
        late_night = 0 # 21-6
        
        for o in orders:
            if o.order_time:
                hour = o.order_time.hour
                if 6 <= hour < 11:
                    breakfast += 1
                elif 11 <= hour < 16:
                    lunch += 1
                elif 16 <= hour < 21:
                    dinner += 1
                else:
                    late_night += 1
        
        total = breakfast + lunch + dinner + late_night
        if total == 0:
            return None
        
        # Find dominant meal time
        meal_counts = {
            "breakfast": breakfast,
            "lunch": lunch,
            "dinner": dinner,
            "late-night": late_night,
        }
        
        dominant_meal = max(meal_counts, key=meal_counts.get)
        dominant_count = meal_counts[dominant_meal]
        dominant_pct = (dominant_count / total * 100) if total > 0 else 0
        
        return Insight(
            type=InsightType.MEAL_TIME_DISTRIBUTION,
            severity=InsightSeverity.INFO,
            title=f"Most Orders During {dominant_meal.title()}",
            message=(
                f"You order most during {dominant_meal} ({dominant_pct:.0f}%): "
                f"breakfast {breakfast}, lunch {lunch}, dinner {dinner}, late-night {late_night}."
            ),
            value=dominant_count,
            unit="orders",
            period="daily",
            supporting_data={
                "breakfast": breakfast,
                "lunch": lunch,
                "dinner": dinner,
                "late_night": late_night,
                "dominant_meal": dominant_meal,
                "dominant_percentage": round(dominant_pct, 1),
            }
        )
    
    # -----------------------------------------------------------------------
    # Restaurant Loyalty Insights
    # -----------------------------------------------------------------------
    
    def _generate_loyalty_insights(
        self,
        orders: list[Order],
        period_label: str,
    ) -> list[Insight]:
        """Generate restaurant loyalty insights."""
        insights: list[Insight] = []
        
        if len(orders) < DataThresholds.MIN_ORDERS_FOR_LOYALTY:
            return insights
        
        # Count orders per restaurant
        restaurant_counter: Counter[str] = Counter()
        for o in orders:
            if o.restaurant_name:
                restaurant_counter[o.restaurant_name] += 1
        
        if not restaurant_counter:
            return insights
        
        # Favorite restaurant
        fav_restaurant, fav_count = restaurant_counter.most_common(1)[0]
        fav_percentage = (fav_count / len(orders) * 100) if orders else 0
        
        insights.append(Insight(
            type=InsightType.FAVORITE_RESTAURANT,
            severity=InsightSeverity.INFO,
            title=f"Favorite: {fav_restaurant}",
            message=f"{fav_restaurant} is your most ordered restaurant with {fav_count} orders ({fav_percentage:.0f}%).",
            value=fav_count,
            unit="orders",
            period=period_label,
            supporting_data={
                "restaurant": fav_restaurant,
                "order_count": fav_count,
                "percentage": round(fav_percentage, 1),
                "avg_order_value": round(
                    sum(o.order_total for o in orders if o.restaurant_name == fav_restaurant) / fav_count,
                    2,
                ),
            }
        ))
        
        # Restaurant loyalty (repeat orders from same restaurant)
        repeat_restaurants = [r for r, c in restaurant_counter.items() if c >= DataThresholds.MIN_ORDERS_PER_RESTAURANT]
        loyalty_pct = (len(repeat_restaurants) / len(restaurant_counter) * 100) if restaurant_counter else 0
        
        if loyalty_pct > 50:
            insights.append(Insight(
                type=InsightType.RESTAURANT_LOYALTY,
                severity=InsightSeverity.SUCCESS,
                title="High Restaurant Loyalty",
                message=f"You have strong loyalty with {len(repeat_restaurants)} restaurants (ordered 3+ times each).",
                value=len(repeat_restaurants),
                unit="restaurants",
                period=period_label,
                supporting_data={
                    "repeat_restaurants": len(repeat_restaurants),
                    "total_restaurants": len(restaurant_counter),
                    "loyalty_percentage": round(loyalty_pct, 1),
                }
            ))
        
        # Restaurant diversity
        unique_restaurants = len(restaurant_counter)
        diversity_score = min(unique_restaurants / len(orders), 1.0)  # Cap at 1.0
        
        if unique_restaurants >= 10:
            insights.append(Insight(
                type=InsightType.RESTAURANT_DIVERSITY,
                severity=InsightSeverity.INFO,
                title="High Restaurant Diversity",
                message=f"You've ordered from {unique_restaurants} different restaurants, showing good variety.",
                value=unique_restaurants,
                unit="restaurants",
                period=period_label,
                supporting_data={
                    "unique_restaurants": unique_restaurants,
                    "total_orders": len(orders),
                    "diversity_score": round(diversity_score, 2),
                }
            ))
        elif unique_restaurants <= 3:
            insights.append(Insight(
                type=InsightType.RESTAURANT_DIVERSITY,
                severity=InsightSeverity.INFO,
                title="Limited Restaurant Diversity",
                message=f"You've ordered from only {unique_restaurants} restaurants. Consider exploring more options!",
                value=unique_restaurants,
                unit="restaurants",
                period=period_label,
                supporting_data={
                    "unique_restaurants": unique_restaurants,
                    "total_orders": len(orders),
                    "diversity_score": round(diversity_score, 2),
                }
            ))
        
        return insights
    
    # -----------------------------------------------------------------------
    # Cuisine Preference Insights
    # -----------------------------------------------------------------------
    
    def _generate_cuisine_insights(
        self,
        orders: list[Order],
        period_label: str,
    ) -> list[Insight]:
        """Generate cuisine preference insights."""
        insights: list[Insight] = []
        
        if len(orders) < DataThresholds.MIN_ORDERS_FOR_CUISINE:
            return insights
        
        # Count orders per cuisine
        cuisine_counter: Counter[str] = Counter()
        for o in orders:
            for cuisine in o.cuisine_list:
                if cuisine:
                    cuisine_counter[cuisine] += 1
        
        if not cuisine_counter:
            return insights
        
        # Favorite cuisine
        fav_cuisine, fav_count = cuisine_counter.most_common(1)[0]
        fav_percentage = (fav_count / len(orders) * 100) if orders else 0
        
        insights.append(Insight(
            type=InsightType.FAVORITE_CUISINE,
            severity=InsightSeverity.INFO,
            title=f"Favorite Cuisine: {fav_cuisine}",
            message=f"{fav_cuisine} is your most ordered cuisine, appearing in {fav_count} orders ({fav_percentage:.0f}%).",
            value=fav_count,
            unit="orders",
            period=period_label,
            supporting_data={
                "cuisine": fav_cuisine,
                "order_count": fav_count,
                "percentage": round(fav_percentage, 1),
            }
        ))
        
        # Cuisine diversity
        unique_cuisines = len(cuisine_counter)
        if unique_cuisines >= 10:
            insights.append(Insight(
                type=InsightType.CUISINE_DIVERSITY,
                severity=InsightSeverity.SUCCESS,
                title="High Cuisine Diversity",
                message=f"You enjoy {unique_cuisines} different cuisines, showing adventurous taste!",
                value=unique_cuisines,
                unit="cuisines",
                period=period_label,
                supporting_data={
                    "unique_cuisines": unique_cuisines,
                    "total_orders": len(orders),
                }
            ))
        elif unique_cuisines <= 3:
            insights.append(Insight(
                type=InsightType.CUISINE_DIVERSITY,
                severity=InsightSeverity.INFO,
                title="Limited Cuisine Variety",
                message=f"You primarily order from {unique_cuisines} cuisine types. Try exploring new cuisines!",
                value=unique_cuisines,
                unit="cuisines",
                period=period_label,
                supporting_data={
                    "unique_cuisines": unique_cuisines,
                    "total_orders": len(orders),
                }
            ))
        
        cuisine_trend = self._calculate_cuisine_trend(orders)
        if cuisine_trend:
            insights.append(cuisine_trend)

        return insights

    def _calculate_cuisine_trend(self, orders: list[Order]) -> Insight | None:
        """Compare the top cuisine in the latest month with the previous month."""
        monthly_cuisines: dict[str, Counter[str]] = defaultdict(Counter)
        for order in orders:
            if not order.order_time:
                continue
            month = order.order_time.strftime("%Y-%m")
            for cuisine in order.cuisine_list:
                monthly_cuisines[month][cuisine] += 1

        months = sorted(monthly_cuisines)
        if len(months) < DataThresholds.MIN_MONTHS_FOR_COMPARISON:
            return None

        prev_month, last_month = months[-2], months[-1]
        prev_counter = monthly_cuisines[prev_month]
        last_counter = monthly_cuisines[last_month]
        if sum(prev_counter.values()) < 3 or sum(last_counter.values()) < 3:
            return None

        prev_top, prev_count = prev_counter.most_common(1)[0]
        last_top, last_count = last_counter.most_common(1)[0]
        if prev_top == last_top:
            return Insight(
                type=InsightType.CUISINE_TREND,
                severity=InsightSeverity.INFO,
                title="Cuisine Preference Stayed Consistent",
                message=f"{last_top} remained your top cuisine across the last two active months.",
                value=last_top,
                unit="cuisine",
                period="monthly",
                supporting_data={
                    "last_month": last_month,
                    "last_month_top_cuisine": last_top,
                    "last_month_count": last_count,
                    "previous_month": prev_month,
                    "previous_month_top_cuisine": prev_top,
                    "previous_month_count": prev_count,
                },
            )

        return Insight(
            type=InsightType.CUISINE_TREND,
            severity=InsightSeverity.INFO,
            title="Cuisine Preference Shift",
            message=f"Your top cuisine shifted from {prev_top} to {last_top} in the latest active month.",
            value=last_top,
            unit="cuisine",
            period="monthly",
            supporting_data={
                "last_month": last_month,
                "last_month_top_cuisine": last_top,
                "last_month_count": last_count,
                "previous_month": prev_month,
                "previous_month_top_cuisine": prev_top,
                "previous_month_count": prev_count,
            },
        )
    
    # -----------------------------------------------------------------------
    # Repeat Food Item Insights
    # -----------------------------------------------------------------------
    
    def _generate_repeat_food_insights(
        self,
        orders: list[Order],
        period_label: str,
    ) -> list[Insight]:
        """Generate repeat food item insights."""
        insights: list[Insight] = []
        
        if len(orders) < DataThresholds.MIN_ORDERS_FOR_REPEAT_ITEMS:
            return insights
        
        # Query all order items from database
        from sqlmodel import select
        from ..models import OrderItem
        
        order_ids = [o.order_id for o in orders]
        if not order_ids:
            return insights
        
        # Get all items for these orders
        stmt = select(OrderItem).where(OrderItem.order_id.in_(order_ids))
        items = self.session.exec(stmt).all()
        
        if not items:
            # Insufficient item-level data
            return insights
        
        # Count item occurrences
        item_counter: Counter[str] = Counter()
        for item in items:
            if item.name:
                # Normalize item names (lowercase, strip)
                normalized_name = item.name.strip().lower()
                item_counter[normalized_name] += 1
        
        # Find repeat items (ordered MIN_ITEM_OCCURRENCES+ times)
        repeat_items = [(name, count) for name, count in item_counter.items() 
                       if count >= DataThresholds.MIN_ITEM_OCCURRENCES]
        
        if not repeat_items:
            return insights
        
        # Sort by count
        repeat_items.sort(key=lambda x: x[1], reverse=True)
        
        # Top repeat item
        top_item, top_count = repeat_items[0]
        
        insights.append(Insight(
            type=InsightType.FAVORITE_ITEMS,
            severity=InsightSeverity.INFO,
            title=f"Favorite Item: {top_item.title()}",
            message=f"You've ordered '{top_item.title()}' {top_count} times - it's your go-to dish!",
            value=top_count,
            unit="orders",
            period=period_label,
            supporting_data={
                "item_name": top_item,
                "order_count": top_count,
                "all_repeat_items": len(repeat_items),
            }
        ))
        
        # General repeat behavior
        if len(repeat_items) >= 3:
            insights.append(Insight(
                type=InsightType.REPEAT_FOOD,
                severity=InsightSeverity.INFO,
                title="You Have Favorite Dishes",
                message=f"You've ordered {len(repeat_items)} items 3+ times each, showing clear preferences.",
                value=len(repeat_items),
                unit="items",
                period=period_label,
                supporting_data={
                    "repeat_items_count": len(repeat_items),
                    "top_3_items": [{"name": name, "count": count} for name, count in repeat_items[:3]],
                }
            ))
        
        return insights
    
    # -----------------------------------------------------------------------
    # Late-Night Ordering Insights
    # -----------------------------------------------------------------------
    
    def _generate_late_night_insights(
        self,
        orders: list[Order],
        period_label: str,
    ) -> list[Insight]:
        """Generate late-night ordering insights."""
        insights: list[Insight] = []
        
        if len(orders) < DataThresholds.MIN_ORDERS_FOR_LATE_NIGHT:
            return insights
        
        # Count late-night orders (10 PM to 6 AM)
        late_night_orders = []
        late_night_restaurants: Counter[str] = Counter()
        late_night_spending = 0.0
        
        for o in orders:
            if o.order_time:
                hour = o.order_time.hour
                # Late night: 22:00-05:59 (10 PM to 6 AM)
                if hour >= 22 or hour < 6:
                    late_night_orders.append(o)
                    if o.restaurant_name:
                        late_night_restaurants[o.restaurant_name] += 1
                    late_night_spending += o.order_total
        
        if not late_night_orders:
            return insights
        
        late_night_count = len(late_night_orders)
        late_night_pct = (late_night_count / len(orders) * 100) if orders else 0
        
        # Late-night ordering frequency
        if late_night_count >= DataThresholds.MIN_ORDERS_FOR_LATE_NIGHT:
            severity = InsightSeverity.WARNING if late_night_pct > 30 else InsightSeverity.INFO
            
            insights.append(Insight(
                type=InsightType.LATE_NIGHT_ORDERING,
                severity=severity,
                title=f"{late_night_pct:.0f}% Late-Night Orders",
                message=f"You placed {late_night_count} orders after 10 PM ({late_night_pct:.0f}%), spending ₹{late_night_spending:.2f}.",
                value=late_night_count,
                unit="orders",
                period=period_label,
                supporting_data={
                    "late_night_count": late_night_count,
                    "late_night_percentage": round(late_night_pct, 1),
                    "late_night_spending": round(late_night_spending, 2),
                    "avg_late_night_order": round(late_night_spending / late_night_count, 2) if late_night_count > 0 else 0,
                    "most_common_late_night_restaurant": late_night_restaurants.most_common(1)[0][0] if late_night_restaurants else None,
                }
            ))
        
        return insights
    
    # -----------------------------------------------------------------------
    # Helper Methods
    # -----------------------------------------------------------------------
    
    def _insufficient_data_insight(self, order_count: int) -> Insight:
        """Return an insight indicating insufficient data for analysis."""
        return Insight(
            type=InsightType.INSUFFICIENT_DATA,
            severity=InsightSeverity.INFO,
            title="Insufficient Order History",
            message=(
                f"You have {order_count} orders. "
                f"At least {DataThresholds.MIN_ORDERS_FOR_PATTERNS} orders are needed for reliable pattern analysis."
            ),
            value=order_count,
            unit="orders",
            period=None,
            supporting_data={
                "current_orders": order_count,
                "required_orders": DataThresholds.MIN_ORDERS_FOR_PATTERNS,
            }
        )
    
    def _format_period(self, start_date: str | None, end_date: str | None) -> str:
        """Format the period string for display."""
        if start_date and end_date:
            return f"{start_date} to {end_date}"
        elif start_date:
            return f"from {start_date}"
        elif end_date:
            return f"until {end_date}"
        else:
            return "all-time"
    
    def _format_date_range(self, start: datetime, end: datetime) -> str:
        """Format a datetime range for display."""
        return f"{start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}"


# ---------------------------------------------------------------------------
# Convenience function for standalone usage
# ---------------------------------------------------------------------------

def generate_food_insights(
    session: Session,
    start_date: str | None = None,
    end_date: str | None = None,
    period: str | None = None,
    *,
    user_id: int | None = None,
    today: date | None = None,
) -> list[Insight]:
    """
    Convenience function to generate food insights.
    
    Args:
        session: SQLModel database session
        start_date: Optional start date (YYYY-MM-DD)
        end_date: Optional end date (YYYY-MM-DD)
        period: Optional natural period such as "last month"
    
    Returns:
        List of Insight objects
    """
    engine = InsightEngine(session, user_id=user_id)
    return engine.generate_all_insights(start_date, end_date, period, today=today)


def build_food_insights_response(
    session: Session,
    start_date: str | None = None,
    end_date: str | None = None,
    period: str | None = None,
    *,
    user_id: int | None = None,
    today: date | None = None,
) -> InsightsListResponse:
    """Build the shared structured response used by REST and MCP."""
    resolved_period = resolve_insight_period(start_date, end_date, period, today=today)
    insights = generate_food_insights(
        session,
        start_date=start_date,
        end_date=end_date,
        period=period,
        user_id=user_id,
        today=today,
    )
    orders = repository.get_orders_in_range(
        session,
        user_id=user_id,
        start_date=resolved_period.start_date,
        end_date=resolved_period.end_date,
    )

    return InsightsListResponse(
        period={
            "start": resolved_period.start_date,
            "end": resolved_period.end_date,
            "label": resolved_period.label,
        },
        total_orders=len(orders),
        insights=[
            InsightResponse(
                type=insight.type,
                severity=insight.severity,
                title=insight.title,
                message=insight.message,
                value=insight.value,
                unit=insight.unit,
                period=insight.period,
                supporting_data=insight.supporting_data,
            )
            for insight in insights
        ],
        generated_at=datetime.now(timezone.utc).isoformat() + "Z",
    )
