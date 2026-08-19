"""
FastAPI REST layer for the Swiggy MCP server.

These routes expose the *exact same* functionality as the MCP tools but
return structured JSON (Pydantic models) instead of markdown text.

All request / response schemas are imported from ``models.py`` so they
stay in sync with the MCP tool signatures.
"""

from __future__ import annotations
import logging
import os
import httpx
from datetime import datetime, timedelta, timezone
from typing import Generator
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session, select
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
from .security import encrypt_token

logger = logging.getLogger(__name__)

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


# ---------------------------------------------------------------------------
# GET /api/auth/swiggy/callback
# ---------------------------------------------------------------------------

@router.get("/auth/swiggy/callback", summary="OAuth Callback for Swiggy", tags=["Authentication"], response_class=HTMLResponse)
async def swiggy_oauth_callback(
    request: Request,
    state: str = Query(..., description="OAuth State"),
    code: str | None = Query(default=None, description="Authorization Code"),
    error: str | None = Query(default=None, description="Error"),
    error_description: str | None = Query(default=None, description="Error description"),
    session: Session = Depends(_session),
) -> HTMLResponse:
    """Handle Swiggy OAuth callback."""
    
    import hashlib
    from .database import get_engine
    
    logger.info(f"OAuth callback reached; code_present={bool(code)}; state_present={bool(state)}; error_present={bool(error)}")
    logger.info(f"Callback request host: {request.url.hostname}; path: {request.url.path}")
    
    cb_state_hash = hashlib.sha256(state.encode('utf-8')).hexdigest()[:12] if state else "none"
    engine_url = str(get_engine().url)
    logger.info(f"OAuth callback STATE:")
    logger.info(f"  callback_state_hash={cb_state_hash}")
    logger.info(f"  callback_state_length={len(state) if state else 0}")
    logger.info(f"  engine_url={engine_url}")
    logger.info(f"  current_time={datetime.now(timezone.utc)}")
    
    if error:
        logger.error(f"OAuth error received: {error} - {error_description}")
        return HTMLResponse(f"<h1>❌ Swiggy connection failed: {error} - {error_description}</h1>", status_code=400)
        
    if not code:
        logger.error("OAuth callback missing code")
        return HTMLResponse("<h1>❌ Swiggy connection failed: Missing code.</h1>", status_code=400)

    from .models import User, SwiggyConnection, OAuthState
    
    # Validate State
    oauth_state = session.exec(select(OAuthState).where(OAuthState.state == state)).first()
    
    if not oauth_state:
        logger.error(f"OAuth callback failed: Invalid state (hash={cb_state_hash})")
        return HTMLResponse("<h1>❌ Swiggy connection failed: Invalid or missing state.</h1>", status_code=400)
    
    # Check expiry
    try:
        now_utc = datetime.now(timezone.utc)
        expires_at_aware = oauth_state.expires_at.replace(tzinfo=timezone.utc) if oauth_state.expires_at.tzinfo is None else oauth_state.expires_at

        if expires_at_aware < now_utc:
            logger.error(f"OAuth callback failed: Expired state (hash={cb_state_hash})")
            return HTMLResponse("<h1>❌ Swiggy connection failed: State expired. Please try again.</h1>", status_code=400)
        
        telegram_id = oauth_state.telegram_id
        code_verifier = oauth_state.code_verifier
        
        # 2. Exchange Code for Token
        from .dcr import get_or_register_client
        try:
            client_id = await get_or_register_client()
        except Exception:
            logger.exception("Failed to get or register Swiggy OAuth client during callback")
            return HTMLResponse("<h1>❌ Swiggy connection failed: Internal client error.</h1>", status_code=500)
            
        redirect_uri = os.getenv("SWIGGY_REDIRECT_URI", "http://127.0.0.1:8000/api/auth/swiggy/callback")
        
        token_url = "https://mcp.swiggy.com/auth/token"
        
        data = {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
        }
            
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(token_url, data=data, timeout=10.0)
                if resp.status_code != 200:
                    logger.error("Swiggy token exchange failed: %s %s", resp.status_code, resp.text)
                    return HTMLResponse("<h1>❌ Swiggy connection failed: Token exchange failed.</h1>", status_code=400)
                
                token_data = resp.json()
                access_token = token_data.get("access_token")
                expires_in = token_data.get("expires_in", 3600)
                
                if not access_token:
                    return HTMLResponse("<h1>❌ Swiggy connection failed: Missing access token in response.</h1>", status_code=400)
                    
            except Exception:
                logger.exception("Exception during Swiggy token exchange")
                return HTMLResponse("<h1>❌ Swiggy connection failed: Network error during token exchange.</h1>", status_code=500)
        
        # 3. Create or Update User & Connection
        
        user = session.exec(select(User).where(User.telegram_id == telegram_id)).first()
        if not user:
            user = User(telegram_id=telegram_id)
            session.add(user)
            session.commit()
            session.refresh(user)
            
        conn = session.exec(select(SwiggyConnection).where(SwiggyConnection.user_id == user.id)).first()
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
        
        if not conn:
            conn = SwiggyConnection(
                user_id=user.id,
                status="CONNECTED",
                access_token=encrypt_token(access_token),
                expires_at=expires_at
            )
            session.add(conn)
        else:
            conn.status = "CONNECTED"
            conn.access_token = encrypt_token(access_token)
            conn.expires_at = expires_at
            conn.updated_at = datetime.now(timezone.utc)
            session.add(conn)
    
        session.commit()
    finally:
        # 4. Always consume the state
        session.delete(oauth_state)
        session.commit()

    # 4. Show success page
    html = """
    <html>
        <head><title>Swiggy Connected</title></head>
        <body style="font-family: sans-serif; text-align: center; padding: 50px;">
            <h1 style="color: #4CAF50;">✅ Swiggy connected successfully!</h1>
            <p>Your FoodIQ account is now connected to Swiggy.</p>
            <p>You can close this window and return to Telegram.</p>
        </body>
    </html>
    """
    return HTMLResponse(html)
