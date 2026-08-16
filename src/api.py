"""
FastAPI REST layer for the Swiggy MCP server.

These routes expose the *exact same* functionality as the MCP tools but
return structured JSON (Pydantic models) instead of markdown text.

All request / response schemas are imported from ``models.py`` so they
stay in sync with the MCP tool signatures.
"""

from __future__ import annotations
from typing import Generator
from fastapi import APIRouter, Depends, Query
from sqlmodel import Session
from . import fetcher, repository
from .database import get_session
from .models import (
    AnalyticsResult,
    OrderOut,
    RestaurantStats,
    SyncOrdersRequest,
    SyncResult,
    InsightsListResponse,
)

router = APIRouter(prefix="/api", tags=["Swiggy Orders"])

# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _validate_date_format(date_str: str | None, param_name: str) -> None:
    """
    Validate date string format (YYYY-MM-DD).
    
    Raises ValueError if format is invalid (will be caught by error handler).
    Implements requirement 12.4: Return HTTP 400 for invalid requests.
    """
    if date_str is None:
        return
    
    from datetime import datetime
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"Invalid date format for {param_name}: expected YYYY-MM-DD, got '{date_str}'")


def _validate_analysis_type(analysis_type: str) -> None:
    """
    Validate analysis_type parameter.
    
    Raises ValueError if analysis_type is not one of the allowed values.
    Implements requirement 12.4: Return HTTP 400 for invalid requests.
    """
    valid_types = {"summary", "spending", "timing", "restaurants", "cuisines"}
    if analysis_type not in valid_types:
        raise ValueError(
            f"Invalid analysis_type: '{analysis_type}'. "
            f"Must be one of: {', '.join(sorted(valid_types))}"
        )

# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------

def _session() -> Generator[Session, None, None]:
    """Yield a SQLModel session for dependency injection."""
    with get_session() as session:
        yield session

# ---------------------------------------------------------------------------
# GET /api/health
# ---------------------------------------------------------------------------

@router.get("/health", summary="Health check", tags=["System"])
def health_check(session: Session = Depends(_session)) -> dict[str, str | dict[str, int | str]]:
    """
    Health check endpoint with database statistics.
    
    Returns service status and database metrics including:
    - Total orders in database
    - Date coverage (first to last order)
    """
    sync_result = repository.get_sync_result(session)
    return {
        "status": "ok",
        "service": "swiggy-mcp-server",
        "database": {
            "total_orders": sync_result.total_orders_in_db,
            "date_coverage": sync_result.date_coverage,
        }
    }

# ---------------------------------------------------------------------------
# POST /api/sync
# ---------------------------------------------------------------------------

@router.post("/sync", response_model=SyncResult, summary="Sync orders from Swiggy")
async def sync_orders(body: SyncOrdersRequest, session: Session = Depends(_session)) -> SyncResult:
    """
    Fetch orders from the Swiggy API using the provided session cookies
    and persist them into the local SQLite database.

    **Cookies are used only for this request and are never stored.**
    
    Error responses:
    - 401: Invalid or expired session cookies
    - 422: Request validation failed
    - 502: Failed to fetch from Swiggy API
    """
    # Fetch orders from Swiggy API (errors propagate to error handlers)
    raw_orders = await fetcher.fetch_all_orders(body.cookies.get_secret_value(), max_pages=body.max_pages)

    # Persist to database
    new_count = repository.upsert_orders(raw_orders, session)
    result = repository.get_sync_result(session)
    result.new_orders_fetched = new_count
    return result

# ---------------------------------------------------------------------------
# GET /api/orders
# ---------------------------------------------------------------------------

@router.get("/orders", response_model=list[OrderOut], summary="Get orders")
def get_orders_endpoint(
    start_date: str | None = Query(default=None, description="YYYY-MM-DD"),
    end_date: str | None = Query(default=None, description="YYYY-MM-DD"),
    restaurant_name: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    session: Session = Depends(_session),
) -> list[OrderOut]:
    """Retrieve orders with optional date, restaurant, and limit filters."""
    orders = repository.get_orders(
        session,
        start_date=start_date,
        end_date=end_date,
        restaurant_name=restaurant_name,
        limit=limit,
    )
    return [repository.to_order_out(o, session) for o in orders]

# ---------------------------------------------------------------------------
# GET /api/restaurants
# ---------------------------------------------------------------------------

@router.get("/restaurants", response_model=list[RestaurantStats], summary="Get restaurants")
def get_restaurants(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    min_orders: int = Query(default=1, ge=1),
    session: Session = Depends(_session),
) -> list[RestaurantStats]:
    """List restaurants with aggregated stats (order count, spending, etc.)."""
    return repository.get_restaurants(
        session, start_date=start_date, end_date=end_date, min_orders=min_orders,
    )

# ---------------------------------------------------------------------------
# GET /api/analytics
# ---------------------------------------------------------------------------

@router.get("/analytics", response_model=AnalyticsResult, summary="Get analytics")
def get_analytics(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    analysis_type: str = Query(default="summary"),
    session: Session = Depends(_session),
) -> AnalyticsResult:
    """
    Generate analytics.

    **analysis_type** can be one of:
    ``summary``, ``spending``, ``timing``, ``restaurants``, ``cuisines``.
    """
    return repository.build_analytics(
        session,
        start_date=start_date,
        end_date=end_date,
        analysis_type=analysis_type,
    )

# ---------------------------------------------------------------------------
# GET /api/search
# ---------------------------------------------------------------------------

@router.get("/search", response_model=list[OrderOut], summary="Search orders")
def search_orders(
    query: str = Query(..., min_length=1, description="Search term"),
    limit: int = Query(default=20, ge=1, le=200),
    session: Session = Depends(_session),
) -> list[OrderOut]:
    """Search orders by restaurant name, cuisine, location, or item name."""
    orders = repository.search_orders(session, query, limit=limit)
    return [repository.to_order_out(o, session) for o in orders]

# ---------------------------------------------------------------------------
# GET /api/insights
# ---------------------------------------------------------------------------

@router.get("/insights", response_model=InsightsListResponse, summary="Get food intelligence insights")
def get_insights(
    start_date: str | None = Query(default=None, description="YYYY-MM-DD"),
    end_date: str | None = Query(default=None, description="YYYY-MM-DD"),
    period: str | None = Query(
        default=None,
        description="Natural period: today, yesterday, this week, last week, this month, last month",
    ),
    session: Session = Depends(_session),
) -> InsightsListResponse:
    """
    Generate personalized food intelligence insights.
    
    Analyzes your ordering behavior, spending patterns, restaurant loyalty,
    cuisine preferences, and more to provide actionable insights.
    
    **Query Parameters:**
    - start_date: Filter insights to orders from this date onwards (YYYY-MM-DD)
    - end_date: Filter insights to orders until this date (YYYY-MM-DD)
    - period: Natural period such as "this month" or "last week"
    
    **Returns:**
    - InsightsListResponse with period info and list of insights
    
    **Insights Include:**
    - Spending patterns and trends
    - Ordering behavior (frequency, peak hours, days)
    - Restaurant loyalty and diversity
    - Cuisine preferences
    - Repeat food items
    - Late-night ordering patterns
    """
    from .services.insight_engine import build_food_insights_response

    return build_food_insights_response(
        session,
        start_date=start_date,
        end_date=end_date,
        period=period,
    )
