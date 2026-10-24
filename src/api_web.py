"""
Web UI specific API endpoints for React frontend.
Handles authentication, food ordering, Instamart, and Dineout operations.
"""
from fastapi import APIRouter, Depends, HTTPException, Response, Cookie, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select
from typing import Annotated, Optional, Generator
import secrets
import os
import urllib.parse
from datetime import datetime, timezone, timedelta

from .database import get_session
from .models import User, SwiggyConnection, OAuthState
from .security import decrypt_token, generate_oauth_state, generate_pkce_verifier, generate_pkce_challenge
from . import swiggy_mcp_client

router = APIRouter(prefix="/api", tags=["Web UI"])

# -------------------------------------------------------------------------
# Database session dependency
# -------------------------------------------------------------------------

def _get_db_session() -> Generator[Session, None, None]:
    """Yield a SQLModel session for dependency injection."""
    with get_session() as session:
        yield session

# -------------------------------------------------------------------------
# Session management
# -------------------------------------------------------------------------

# In-memory session store (use Redis in production)
sessions: dict[str, dict] = {}

def generate_session_id() -> str:
    """Generate a secure session ID."""
    return secrets.token_urlsafe(32)

def get_current_user(
    request: Request,
    session_id: Annotated[str | None, Cookie()] = None,
    db: Session = Depends(_get_db_session)
) -> User | None:
    """Get the currently authenticated user from session cookie or X-Session-ID header."""
    # Try to get session_id from cookie first, then from header
    if not session_id:
        session_id = request.headers.get("X-Session-ID")
    
    if not session_id or session_id not in sessions:
        return None
    user_id = sessions[session_id].get("user_id")
    if not user_id:
        return None
    return db.exec(select(User).where(User.id == user_id)).first()

def require_auth(user: User | None = Depends(get_current_user)) -> User:
    """Require authentication, raise 401 if not logged in."""
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user

def get_user_token(user: User, db: Session) -> str | None:
    """Get decrypted Swiggy access token for a user."""
    conn = db.exec(select(SwiggyConnection).where(SwiggyConnection.user_id == user.id)).first()
    if not conn or conn.status != "CONNECTED":
        return None
    
    # Check token expiry
    if conn.expires_at:
        now = datetime.now(timezone.utc)
        expires_at = conn.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if now > expires_at:
            return None
    
    return decrypt_token(conn.access_token)

# -------------------------------------------------------------------------
# Authentication
# -------------------------------------------------------------------------

@router.get("/auth/login")
async def init_oauth_web():
    """Initiate OAuth flow for web users."""
    state = generate_oauth_state()
    verifier = generate_pkce_verifier()
    challenge = generate_pkce_challenge(verifier)
    
    # Store OAuth state in database
    with get_session() as db:
        now_utc = datetime.now(timezone.utc)
        expires_at = now_utc + timedelta(minutes=15)
        oauth_state = OAuthState(
            state=state,
            telegram_id="web_user",  # Placeholder for web users
            code_verifier=verifier,
            expires_at=expires_at.replace(tzinfo=None)
        )
        db.add(oauth_state)
        db.commit()
    
    # Get or register OAuth client
    from .dcr import get_or_register_client
    try:
        client_id = await get_or_register_client()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to register OAuth client: {str(e)}")
    
    # Build OAuth authorization URL
    redirect_uri = os.getenv("SWIGGY_REDIRECT_URI", "http://127.0.0.1:8000/api/auth/swiggy/callback")
    auth_base_url = "https://mcp.swiggy.com/auth/authorize"
    
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "scope": "mcp:tools"
    }
    
    auth_url = f"{auth_base_url}?{urllib.parse.urlencode(params)}"
    
    # Redirect to Swiggy OAuth
    return RedirectResponse(url=auth_url, status_code=302)

@router.get("/auth/status")
async def auth_status(
    request: Request,
    user: User | None = Depends(get_current_user),
    session_id: Annotated[str | None, Cookie()] = None
):
    """Check if user is authenticated."""
    import logging
    logger = logging.getLogger(__name__)
    
    # Log all cookies received
    all_cookies = request.cookies
    logger.info(f"Auth check - All cookies received: {all_cookies}")
    logger.info(f"Auth check - session_id from cookie: {session_id}")
    logger.info(f"Active sessions: {list(sessions.keys())}")
    logger.info(f"Session details: {sessions}")
    logger.info(f"User found: {user is not None}")
    
    return {
        "authenticated": user is not None,
        "user_id": user.id if user else None,
        "session_id_present": session_id is not None,
        "session_valid": session_id in sessions if session_id else False,
        "debug": {
            "cookies_received": list(all_cookies.keys()),
            "active_sessions_count": len(sessions)
        }
    }

@router.post("/auth/logout")
async def logout(
    session_id: Annotated[str | None, Cookie()] = None,
    response: Response = None
):
    """Logout and clear session."""
    if session_id and session_id in sessions:
        del sessions[session_id]
    
    if response:
        response.delete_cookie(key="session_id")
    
    return {"success": True}

# -------------------------------------------------------------------------
# Food Delivery
# -------------------------------------------------------------------------

@router.get("/food/addresses")
async def get_addresses(
    user: User = Depends(require_auth),
    db: Session = Depends(_get_db_session)
):
    """Get user's saved addresses from Swiggy."""
    token = get_user_token(user, db)
    if not token:
        raise HTTPException(status_code=400, detail="Not connected to Swiggy")
    
    try:
        addresses = await swiggy_mcp_client.get_addresses(token)
        return {"addresses": addresses}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/food/search-restaurants")
async def search_restaurants(
    request_body: dict,
    user: User = Depends(require_auth),
    db: Session = Depends(_get_db_session)
):
    """Search restaurants by name or cuisine."""
    import logging
    logger = logging.getLogger(__name__)
    
    token = get_user_token(user, db)
    if not token:
        raise HTTPException(status_code=400, detail="Not connected to Swiggy")
    
    address_id = request_body.get("address_id")
    query = request_body.get("query")
    
    try:
        results = await swiggy_mcp_client.search_restaurants(token, address_id, query)
        
        logger.info(f"=== RESTAURANT SEARCH BACKEND DEBUG ===")
        logger.info(f"Raw results type: {type(results)}")
        
        # Normalize response
        restaurants = []
        if isinstance(results, dict):
            logger.info(f"Results keys: {list(results.keys())}")
            for key in ['restaurants', 'items', 'data', 'results']:
                if key in results:
                    restaurants = results[key] if isinstance(results[key], list) else []
                    logger.info(f"Found {len(restaurants)} restaurants in '{key}' key")
                    break
        elif isinstance(results, list):
            restaurants = results
            logger.info(f"Results is list with {len(restaurants)} items")
        
        return {"restaurants": restaurants}
    except Exception as e:
        logger.exception("Restaurant search failed")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/food/menu/{restaurant_id}")
async def get_restaurant_menu(
    restaurant_id: str,
    address_id: str,
    user: User = Depends(require_auth),
    db: Session = Depends(_get_db_session)
):
    """Get restaurant menu."""
    token = get_user_token(user, db)
    if not token:
        raise HTTPException(status_code=400, detail="Not connected to Swiggy")
    
    try:
        menu = await swiggy_mcp_client.get_restaurant_menu(token, address_id, restaurant_id)
        return menu
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/food/cart")
async def update_food_cart(
    request_body: dict,
    user: User = Depends(require_auth),
    db: Session = Depends(_get_db_session),
):
    """Add or update one item in the user's Swiggy food cart."""
    address_id = request_body.get("address_id")
    restaurant_id = request_body.get("restaurant_id")
    item_id = request_body.get("item_id")
    quantity = request_body.get("quantity", 1)

    if not all((address_id, restaurant_id, item_id)):
        raise HTTPException(
            status_code=422,
            detail="address_id, restaurant_id, and item_id are required",
        )
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
        raise HTTPException(status_code=422, detail="quantity must be a positive integer")

    token = get_user_token(user, db)
    if not token:
        raise HTTPException(status_code=400, detail="Not connected to Swiggy")

    try:
        result = await swiggy_mcp_client.update_food_cart(
            token,
            str(restaurant_id),
            [{"menu_item_id": str(item_id), "quantity": quantity}],
            str(address_id),
        )
        return {"success": True, "item_id": str(item_id), "quantity": quantity, "cart": result}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Unable to update Swiggy food cart: {e}") from e

# -------------------------------------------------------------------------
# Instamart
# -------------------------------------------------------------------------

@router.post("/instamart/search")
async def search_products(
    request_body: dict,
    user: User = Depends(require_auth),
    db: Session = Depends(_get_db_session)
):
    """Search Instamart products."""
    import logging
    import json
    logger = logging.getLogger(__name__)
    
    token = get_user_token(user, db)
    if not token:
        raise HTTPException(status_code=400, detail="Not connected to Swiggy")
    
    address_id = request_body.get("address_id")
    query = request_body.get("query")
    offset = request_body.get("offset", 0)
    
    try:
        from . import swiggy_instamart_mcp
        results = await swiggy_instamart_mcp.search_products(token, address_id, query, offset)
        
        logger.info(f"=== INSTAMART BACKEND DEBUG ===")
        logger.info(f"Raw results type: {type(results)}")
        logger.info(f"Raw results: {json.dumps(results, indent=2, default=str)[:2000]}")
        
        # Parse and normalize the response
        products = []
        
        if isinstance(results, dict):
            logger.info(f"Results is dict with keys: {list(results.keys())}")
            
            # Check for nested data structures
            # Pattern 1: {"products": [...]}
            if 'products' in results and isinstance(results['products'], list):
                products = results['products']
                logger.info(f"Found {len(products)} products in 'products' key")
            
            # Pattern 2: {"items": [...]}
            elif 'items' in results and isinstance(results['items'], list):
                products = results['items']
                logger.info(f"Found {len(products)} products in 'items' key")
            
            # Pattern 3: {"data": {"products": [...]}}
            elif 'data' in results and isinstance(results['data'], dict):
                data = results['data']
                if 'products' in data and isinstance(data['products'], list):
                    products = data['products']
                    logger.info(f"Found {len(products)} products in data.products")
                elif 'items' in data and isinstance(data['items'], list):
                    products = data['items']
                    logger.info(f"Found {len(products)} products in data.items")
            
            # Pattern 4: {"searches": [...]}
            elif 'searches' in results and isinstance(results['searches'], list):
                products = results['searches']
                logger.info(f"Found {len(products)} products in 'searches' key")
            
            # If still no products found, log full structure
            if not products:
                logger.warning(f"Could not find products array. Full structure: {json.dumps(results, indent=2, default=str)[:1000]}")
        
        elif isinstance(results, list):
            products = results
            logger.info(f"Results is directly a list with {len(products)} items")
        
        # Log first product structure
        if len(products) > 0:
            first = products[0]
            logger.info(f"=== FIRST PRODUCT ===")
            logger.info(f"First product: {json.dumps(first, indent=2, default=str)[:500]}")
            if isinstance(first, dict):
                logger.info(f"First product keys: {list(first.keys())}")
        else:
            logger.warning("No products extracted!")
        
        logger.info(f"Final products count: {len(products)}")
        return {"products": products}
        
    except Exception as e:
        logger.exception("Instamart search failed")
        raise HTTPException(status_code=500, detail=str(e))

# -------------------------------------------------------------------------
# Orders & Analytics
# -------------------------------------------------------------------------

@router.get("/orders")
async def get_orders(
    user: User = Depends(require_auth),
    db: Session = Depends(_get_db_session),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    restaurant: Optional[str] = None,
    limit: int = 50
):
    """Get user's order history with optional filters."""
    from . import repository
    from .models import Order, OrderItem
    
    # Build query
    query = select(Order).where(Order.user_id == user.id)
    
    if start_date:
        query = query.where(Order.order_time >= start_date)
    if end_date:
        query = query.where(Order.order_time <= end_date)
    if restaurant:
        query = query.where(Order.restaurant_name.contains(restaurant))
    
    query = query.order_by(Order.order_time.desc()).limit(limit)
    
    orders = db.exec(query).all()
    
    # Format response with order items
    result = []
    for o in orders:
        # Fetch order items for this order
        items_query = select(OrderItem).where(OrderItem.order_id == o.order_id)
        items = db.exec(items_query).all()
        
        result.append({
            "id": o.order_id,
            "restaurant_name": o.restaurant_name,
            "restaurant_area": o.restaurant_locality or "",
            "restaurant_city": o.restaurant_city or "",
            "order_total": float(o.order_total) if o.order_total else 0,
            "order_time": o.order_time.isoformat() if o.order_time else None,
            "delivery_time": None,  # Not available in current schema
            "is_veg": False,  # Would need to check items or add to schema
            "order_items": [item.name for item in items]
        })
    
    return {
        "orders": result,
        "total_count": len(result)
    }

@router.post("/orders/sync")
async def sync_user_orders(
    user: User = Depends(require_auth),
    db: Session = Depends(_get_db_session),
):
    """Fetch the signed-in user's Swiggy order history and store it locally."""
    token = get_user_token(user, db)
    if not token:
        raise HTTPException(status_code=400, detail="Connect or reconnect your Swiggy account first")

    try:
        addresses = await swiggy_mcp_client.get_addresses(token)
        address_id = next(
            (
                address.get("id") or address.get("addressId") or address.get("address_id")
                for address in addresses
                if isinstance(address, dict)
                and (address.get("id") or address.get("addressId") or address.get("address_id"))
            ),
            None,
        )
        if not address_id:
            raise HTTPException(status_code=502, detail="Swiggy returned no usable delivery address")

        raw_orders = await swiggy_mcp_client.get_food_orders(token, str(address_id))
        if raw_orders and not any(
            isinstance(order, dict)
            and (order.get("order_id") or order.get("orderId") or order.get("id"))
            for order in raw_orders
        ):
            raise HTTPException(
                status_code=502,
                detail="Swiggy returned order data in an unsupported format; no order IDs were found",
            )
        from . import repository

        saved_count = repository.upsert_orders(raw_orders, db, user_id=user.id)
        summary = repository.get_sync_result(db, user_id=user.id)
        return {
            "orders_received": len(raw_orders),
            "new_orders_fetched": saved_count,
            "total_orders": summary.total_orders_in_db,
            "date_coverage": summary.date_coverage,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Unable to sync orders from Swiggy: {e}") from e

@router.get("/analytics")
async def get_analytics(
    user: User = Depends(require_auth),
    db: Session = Depends(_get_db_session),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """Get spending analytics and statistics."""
    from . import repository
    
    # Use build_analytics (not get_analytics which doesn't exist)
    result = repository.build_analytics(
        db, 
        user_id=user.id,
        start_date=start_date,
        end_date=end_date,
        analysis_type="summary"
    )
    
    # Extract data from result
    summary = result.summary if hasattr(result, 'summary') else result
    
    return {
        "total_spent": summary.total_spent if hasattr(summary, 'total_spent') else 0,
        "order_count": summary.total_orders if hasattr(summary, 'total_orders') else 0,
        "avg_order_value": summary.average_order_value if hasattr(summary, 'average_order_value') else 0,
        "date_range": {
            "start": (summary.first_order if hasattr(summary, 'first_order') and summary.first_order else None) or start_date or "",
            "end": (summary.last_order if hasattr(summary, 'last_order') and summary.last_order else None) or end_date or ""
        },
        "top_restaurants": result.top_restaurants or [],
        "top_cuisines": result.top_cuisines or [],
        "monthly_spending": result.monthly_trends or [],
        "veg_vs_nonveg": {
            "veg_orders": 0,  # Not available in current data model
            "nonveg_orders": 0
        }
    }

@router.get("/insights")
async def get_insights(
    user: User = Depends(require_auth),
    db: Session = Depends(_get_db_session)
):
    """Get personalized food insights and recommendations."""
    from .services.insight_engine import build_food_insights_response
    
    try:
        # Use the same insight engine as the main API
        insights_response = build_food_insights_response(
            db,
            user_id=user.id,
            start_date=None,
            end_date=None,
            period=None
        )
        
        return {
            "insights": insights_response.insights if hasattr(insights_response, 'insights') else [],
            "generated_at": insights_response.generated_at if hasattr(insights_response, 'generated_at') else None
        }
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to generate insights: {str(e)}")
        # Return empty insights on error
        return {
            "insights": [],
            "generated_at": None
        }

# -------------------------------------------------------------------------
# Dineout
# -------------------------------------------------------------------------

@router.post("/dineout/search")
async def search_venues(
    request_body: dict,
    user: User = Depends(require_auth),
    db: Session = Depends(_get_db_session)
):
    """Search Dineout venues."""
    import logging
    logger = logging.getLogger(__name__)
    
    token = get_user_token(user, db)
    if not token:
        raise HTTPException(status_code=400, detail="Not connected to Swiggy")
    
    query = request_body.get("query")
    address_id = request_body.get("address_id")
    lat = request_body.get("lat")
    lng = request_body.get("lng")
    
    try:
        from . import swiggy_dineout_mcp
        results = await swiggy_dineout_mcp.search_restaurants_dineout(token, query, address_id, lat, lng)
        
        logger.info(f"=== DINEOUT SEARCH BACKEND DEBUG ===")
        logger.info(f"Raw results type: {type(results)}")
        
        # Normalize response
        venues = []
        if isinstance(results, dict):
            logger.info(f"Results keys: {list(results.keys())}")
            for key in ['restaurants', 'venues', 'items', 'data', 'results']:
                if key in results:
                    venues = results[key] if isinstance(results[key], list) else []
                    logger.info(f"Found {len(venues)} venues in '{key}' key")
                    break
        elif isinstance(results, list):
            venues = results
            logger.info(f"Results is list with {len(venues)} items")
        
        return {"venues": venues}
    except Exception as e:
        logger.exception("Dineout search failed")
        raise HTTPException(status_code=500, detail=str(e))
