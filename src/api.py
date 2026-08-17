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
    logger.info(f"  callback_state_repr={repr(state[:4])}...{repr(state[-4:])} (first/last 4 chars)")
    logger.info(f"  engine_url={engine_url}")
    logger.info(f"  current_time={datetime.now(timezone.utc)}")
    
    if error:
        logger.error(f"OAuth error received: {error} - {error_description}")
        return HTMLResponse(f"<h1>❌ Swiggy connection failed: {error} - {error_description}</h1>", status_code=400)
        
    if not code:
        logger.error("OAuth callback missing code")
        return HTMLResponse("<h1>❌ Swiggy connection failed: Missing code.</h1>", status_code=400)

    from .models import User, SwiggyConnection, OAuthState
    
    # 1. Validate State
    # Diagnostic: enumerate ALL states in DB with their hashes
    total_states = session.exec(select(OAuthState)).all()
    logger.info(f"DATABASE LOOKUP DIAGNOSTICS:")
    logger.info(f"  Total OAuthState rows: {len(total_states)}")
    logger.info(f"  engine_url={engine_url}")
    logger.info(f"  Callback state (first/last 8 chars): {repr(state[:8])}...{repr(state[-8:])}")
    
    for i, row in enumerate(total_states):
        row_hash = hashlib.sha256(row.state.encode('utf-8')).hexdigest()[:12]
        # Check exact comparison
        exact_match = (row.state == state)
        # Check byte-by-byte
        bytes_match = (row.state.encode('utf-8') == state.encode('utf-8'))
        logger.info(f"  row[{i}]: hash={row_hash} length={len(row.state)} telegram_id={row.telegram_id} expires_at={row.expires_at}")
        logger.info(f"         exact_match={exact_match} bytes_match={bytes_match}")
        if not exact_match and len(row.state) == len(state):
            # Find first difference
            for idx, (c1, c2) in enumerate(zip(row.state, state)):
                if c1 != c2:
                    logger.info(f"         first_diff_at={idx}: db={repr(c1)} callback={repr(c2)}")
                    break
    
    matching_state = session.exec(select(OAuthState).where(OAuthState.state == state)).first()
    logger.info(f"  Matching row for callback state: {matching_state is not None}")
    if matching_state:
        now_utc = datetime.now(timezone.utc)
        ms_expires = matching_state.expires_at.replace(tzinfo=timezone.utc) if matching_state.expires_at.tzinfo is None else matching_state.expires_at
        logger.info(f"  Matching state expires_at={ms_expires}")
        logger.info(f"  Is matching state expired: {ms_expires < now_utc}")
        logger.info(f"  current_time={now_utc}")
        
    oauth_state = session.exec(select(OAuthState).where(OAuthState.state == state)).first()
    
    # Opportunistic cleanup of stale states
    now = datetime.now(timezone.utc)
    # Compare with naive datetime since SQLite stores naive datetimes
    now_naive = now.replace(tzinfo=None)
    expired_states = session.exec(select(OAuthState).where(OAuthState.expires_at < now_naive)).all()
    deleted_count = 0
    state_exists_before = (oauth_state is not None)
    
    for st in expired_states:
        if not oauth_state or st.state != oauth_state.state:
            session.delete(st)
            deleted_count += 1
    if deleted_count > 0:
        session.commit()
        
    # Re-check after cleanup
    if state_exists_before and not oauth_state:
        # This should never happen — just safety check
        oauth_state = session.exec(select(OAuthState).where(OAuthState.state == state)).first()
    state_exists_after = (session.exec(select(OAuthState).where(OAuthState.state == state)).first() is not None)
    logger.info(f"CLEANUP DIAGNOSTICS:")
    logger.info(f"  Expired states found: {len(expired_states)}")
    logger.info(f"  States deleted: {deleted_count}")
    logger.info(f"  Callback state exists BEFORE cleanup: {state_exists_before}")
    logger.info(f"  Callback state exists AFTER cleanup: {state_exists_after}")

    if not oauth_state:
        logger.error("OAuth state validation FAILED: State not found in database")
        logger.error(f"  Searched for state hash: {cb_state_hash}")
        logger.error(f"  State exists after cleanup: {state_exists_after}")
        
        # Additional diagnostic: Check if state exists in a completely fresh session
        from .database import get_session as fresh_get_session
        with fresh_get_session() as diagnostic_session:
            diagnostic_all = diagnostic_session.exec(select(OAuthState)).all()
            logger.error(f"  Diagnostic check - Total states in fresh session: {len(diagnostic_all)}")
            for ds in diagnostic_all:
                ds_hash = hashlib.sha256(ds.state.encode('utf-8')).hexdigest()[:12]
                logger.error(f"    State: hash={ds_hash} telegram_id={ds.telegram_id}")
        
        return HTMLResponse("<h1>❌ Swiggy connection failed: Invalid or missing state.</h1>", status_code=400)
    
    try:
        now_utc = datetime.now(timezone.utc)
        expires_at_naive = oauth_state.expires_at
        expires_at_aware = oauth_state.expires_at.replace(tzinfo=timezone.utc) if oauth_state.expires_at.tzinfo is None else oauth_state.expires_at
        
        logger.info(f"OAuth state check:")
        logger.info(f"  created_at: {oauth_state.created_at}")
        logger.info(f"  expires_at (raw): {oauth_state.expires_at} (tzinfo: {oauth_state.expires_at.tzinfo})")
        logger.info(f"  expires_at (aware): {expires_at_aware}")
        logger.info(f"  now (UTC): {now_utc}")
        logger.info(f"  remaining seconds: {(expires_at_aware - now_utc).total_seconds()}")
        logger.info(f"  is_expired: {expires_at_aware < now_utc}")

        if expires_at_aware < now_utc:
            logger.error("OAuth state validation FAILED: State expired")
            logger.error(f"  State hash: {cb_state_hash}")
            logger.error(f"  Expired by: {(now_utc - expires_at_aware).total_seconds()} seconds")
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
