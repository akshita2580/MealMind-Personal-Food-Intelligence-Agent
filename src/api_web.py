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
import json
import urllib.parse
from datetime import datetime, timezone, timedelta

from .database import get_session
from .models import User, SwiggyConnection, OAuthState
from .security import decrypt_token, generate_oauth_state, generate_pkce_verifier, generate_pkce_challenge
from . import swiggy_mcp_client
from . import swiggy_instamart_mcp
from . import swiggy_dineout_mcp

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


def _mcp_failure_message(result: object) -> str | None:
    """Find failure envelopes even when Swiggy nests them under data/result."""
    if isinstance(result, dict):
        # Normalised error injected by mcp_transport when isError=true
        if "_tool_error" in result:
            return str(result["_tool_error"])
        if result.get("success") is False:
            error = result.get("error") or result.get("message")
            if isinstance(error, dict):
                error = error.get("message") or error.get("detail")
            return str(error or "Swiggy rejected the operation")
        for key, value in result.items():
            # Don't recurse into the raw MCP envelope keys
            if key in ("_tool_error",):
                continue
            failure = _mcp_failure_message(value)
            if failure:
                return failure
    elif isinstance(result, list):
        for value in result:
            failure = _mcp_failure_message(value)
            if failure:
                return failure
    return None


def _find_nested_value(node: object, wanted: set[str]):
    """Find a named field inside nested MCP envelopes or JSON-encoded text."""
    normalized_wanted = {name.replace("_", "").lower() for name in wanted}
    if isinstance(node, dict):
        for key, value in node.items():
            if str(key).replace("_", "").lower() in normalized_wanted and value not in (None, {}):
                if isinstance(value, str):
                    try:
                        return json.loads(value)
                    except (ValueError, TypeError):
                        pass
                return value
        for value in node.values():
            found = _find_nested_value(value, wanted)
            if found is not None:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _find_nested_value(value, wanted)
            if found is not None:
                return found
    elif isinstance(node, str):
        try:
            decoded = json.loads(node)
        except (ValueError, TypeError):
            return None
        if isinstance(decoded, (dict, list)):
            return _find_nested_value(decoded, wanted)
    return None


def _food_cart_quantities(items: object) -> dict[str, int]:
    quantities: dict[str, int] = {}
    if not isinstance(items, list):
        return quantities
    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = item.get("menu_item_id") or item.get("menuItemId") or item.get("id")
        try:
            quantity = int(item.get("quantity", 0))
        except (TypeError, ValueError):
            continue
        if item_id:
            quantities[str(item_id)] = quantity
    return quantities


def _food_cart_matches(items: object, expected: dict[str, int]) -> bool:
    actual = _food_cart_quantities(items)
    return bool(expected) and all(actual.get(item_id) == quantity for item_id, quantity in expected.items())


def _agent_dbg(hypothesis_id: str, location: str, message: str, data: dict) -> None:
    # #region agent log
    try:
        import time
        with open(
            r"c:\Users\Akshita\Desktop\MealMind-Personal-Food-Intelligence-Agent\debug-dad6f0.log",
            "a",
            encoding="utf-8",
        ) as fh:
            fh.write(json.dumps({
                "sessionId": "dad6f0",
                "runId": "pre-fix",
                "hypothesisId": hypothesis_id,
                "location": location,
                "message": message,
                "data": data,
                "timestamp": int(time.time() * 1000),
            }, default=str) + "\n")
    except Exception:
        pass
    # #endregion


def _cart_shape(node: object, depth: int = 0):
    if depth > 3:
        return type(node).__name__
    if isinstance(node, dict):
        items = node.get("items")
        item_ids = []
        if isinstance(items, list):
            for row in items[:8]:
                if isinstance(row, dict):
                    item_ids.append({
                        "id": row.get("id"),
                        "menu_item_id": row.get("menu_item_id") or row.get("menuItemId"),
                        "item_id": row.get("item_id") or row.get("itemId"),
                        "qty": row.get("quantity"),
                    })
        return {
            "keys": list(node.keys())[:25],
            "success": node.get("success"),
            "statusMessage": node.get("statusMessage") or node.get("message") or node.get("result"),
            "item_ids": item_ids,
            "nested": {
                key: _cart_shape(node[key], depth + 1)
                for key in ("data", "result", "cart", "foodCart")
                if key in node
            },
        }
    if isinstance(node, list):
        return {"list_len": len(node), "first": _cart_shape(node[0], depth + 1) if node else None}
    return str(node)[:180]


async def _update_food_cart_and_confirm(token: str, restaurant_id: str, address_id: str, items: list[dict]):
    """Try both published Food MCP cart schemas and confirm the requested rows."""
    import logging
    logger = logging.getLogger(__name__)

    expected = {item["menu_item_id"]: item["quantity"] for item in items}
    logger.info(
        "Cart sync attempt: restaurant_id=%s address_id=%s item_ids=%s",
        restaurant_id, address_id, list(expected.keys()),
    )
    # #region agent log
    _agent_dbg("H1", "api_web.py:_update_food_cart_and_confirm", "cart sync request", {
        "restaurant_id": restaurant_id,
        "address_len": len(str(address_id or "")),
        "expected": expected,
        "item_customizations": [
            {
                "menu_item_id": item.get("menu_item_id"),
                "qty": item.get("quantity"),
                "has_variants": bool(item.get("variants")),
                "has_variantsV2": bool(item.get("variantsV2")),
                "has_addons": bool(item.get("addons")),
                "variantsV2_keys": list(item["variantsV2"][0].keys()) if isinstance(item.get("variantsV2"), list) and item["variantsV2"] and isinstance(item["variantsV2"][0], dict) else [],
                "variantsV2_sample": item.get("variantsV2")[:1] if isinstance(item.get("variantsV2"), list) else None,
                "addons_sample": item.get("addons")[:1] if isinstance(item.get("addons"), list) else None,
            }
            for item in items
        ],
        "has_minimal": hasattr(swiggy_mcp_client, "update_food_cart_minimal"),
    })
    # #endregion
    attempts = [
        ("cartItems/all_menu_ID_aliases", swiggy_mcp_client.update_food_cart),
        ("cartItems/id_item_id", swiggy_mcp_client.update_food_cart_compat),
    ]
    _minimal = getattr(swiggy_mcp_client, "update_food_cart_minimal", None)
    if _minimal:
        attempts.append(("cartItems/minimal_spec", _minimal))
    diagnostics = []
    for schema_name, updater in attempts:
        try:
            update_result = await updater(token, restaurant_id, items, address_id)
            # mcp_transport now returns isError payloads instead of raising;
            # extract the message so we can log it and try the next schema.
            tool_err = update_result.get("_tool_error") if isinstance(update_result, dict) else None
            failure = tool_err or _mcp_failure_message(update_result)
            # #region agent log
            _agent_dbg("H4", "api_web.py:update_result", "update_food_cart response", {
                "schema": schema_name,
                "failure": failure,
                "shape": _cart_shape(update_result),
            })
            # #endregion
            if failure:
                logger.warning("Cart schema %s failed: %s", schema_name, failure)
                diagnostics.append(f"{schema_name}: {failure}")
                continue
            update_items = _find_nested_value(update_result, {"items"})
            update_notice = _find_nested_value(update_result, {"statusMessage", "message", "result"})
            cart = await swiggy_mcp_client.get_food_cart(token, address_id)
            cart_failure = _mcp_failure_message(cart)
            if not cart_failure:
                live_items = _find_nested_value(cart, {"items"})
                # #region agent log
                _agent_dbg("H4", "api_web.py:get_food_cart", "live cart after update", {
                    "schema": schema_name,
                    "shape": _cart_shape(cart),
                    "parsed_quantities": _food_cart_quantities(live_items),
                    "expected": expected,
                    "matches": _food_cart_matches(live_items, expected),
                    "update_items_quantities": _food_cart_quantities(update_items),
                    "update_notice": str(update_notice)[:300] if update_notice is not None else None,
                })
                # #endregion
                if _food_cart_matches(live_items, expected):
                    logger.info("Cart confirmed via schema %s", schema_name)
                    return update_result, cart, live_items, schema_name
            else:
                live_items = None
            if _food_cart_matches(update_items, expected):
                # update_food_cart itself returns the live cart payload; use it
                # if get_food_cart is briefly stale on this MCP deployment.
                logger.info("Cart confirmed from update response via schema %s", schema_name)
                return update_result, update_result, update_items, schema_name
            diagnostics.append(
                f"{schema_name}: requested {expected}, returned {_food_cart_quantities(live_items if live_items is not None else update_items)}"
                + (f"; update response: {str(update_notice)[:300]}" if update_notice is not None else "")
                + (f"; get_food_cart: {cart_failure}" if cart_failure else "")
            )
        except Exception as exc:
            logger.warning("Cart schema %s exception: %s", schema_name, exc)
            diagnostics.append(f"{schema_name}: {exc}")
            # #region agent log
            _agent_dbg("H5", "api_web.py:schema_exception", "schema raised", {
                "schema": schema_name,
                "error": str(exc),
            })
            # #endregion
    raise HTTPException(
        status_code=502,
        detail="Swiggy cart sync failed: " + " | ".join(diagnostics),
    )

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

        # Transform to frontend expected format
        formatted_restaurants = []
        for r in restaurants:
            if isinstance(r, dict):
                formatted_restaurants.append({
                    "id": r.get("restaurantId") or r.get("id") or r.get("restaurant_id") or "",
                    "name": r.get("restaurantName") or r.get("name") or "",
                    "cuisine": r.get("cuisine") or r.get("cuisines") or [],
                    "rating": r.get("rating") or 0,
                    "delivery_time": r.get("deliveryTime") or r.get("delivery_time") or "",
                    "cost_for_two": r.get("costForTwo") or r.get("cost_for_two") or "",
                    "image_url": r.get("imageUrl") or r.get("image_url") or r.get("cloudinaryImageId") or ""
                })

        return {"restaurants": formatted_restaurants}
    except Exception as e:
        logger.exception("Restaurant search failed")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/food/menu/{restaurant_id}")
async def get_restaurant_menu(
    restaurant_id: str,
    address_id: str,
    page: int = 1,
    page_size: int = 5,
    user: User = Depends(require_auth),
    db: Session = Depends(_get_db_session)
):
    """Get restaurant menu."""
    import logging
    import re
    logger = logging.getLogger(__name__)
    from fastapi.responses import JSONResponse

    token = get_user_token(user, db)
    if not token:
        raise HTTPException(status_code=400, detail="Not connected to Swiggy")

    if not address_id or not restaurant_id:
        raise HTTPException(status_code=422, detail="address_id and restaurant_id are required")
    if page < 1 or page_size < 1 or page_size > 8:
        raise HTTPException(status_code=422, detail="page must be positive and page_size must be between 1 and 8")

    def clean_text(text):
        """Remove problematic Unicode characters (like unpaired surrogates)."""
        if not isinstance(text, str):
            return text
        # Remove unpaired surrogates and other problematic characters
        try:
            # Encode to utf-8 and decode, replacing errors
            return text.encode('utf-8', 'ignore').decode('utf-8')
        except:
            # If that fails, remove all non-ASCII characters
            return re.sub(r'[^\x00-\x7F]+', '', text)
    
    def clean_dict(obj):
        """Recursively clean all strings in a dictionary or list."""
        if isinstance(obj, dict):
            return {k: clean_dict(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [clean_dict(item) for item in obj]
        elif isinstance(obj, str):
            return clean_text(obj)
        else:
            return obj

    try:
        menu = await swiggy_mcp_client.get_restaurant_menu(
            token, address_id, restaurant_id, page=page, page_size=page_size
        )
        logger.info(
            "Loaded menu for restaurant_id=%s (response_type=%s)",
            restaurant_id,
            type(menu).__name__,
        )

        # Clean the menu data to remove problematic characters
        cleaned_menu = clean_dict(menu)

        # Return as JSONResponse with ensure_ascii=False to properly handle emojis
        return JSONResponse(content=cleaned_menu)

    except Exception as e:
        error_msg = str(e)
        logger.exception("Menu load failed for restaurant_id=%s", restaurant_id)

        raise HTTPException(
            status_code=502,
            detail=f"Could not load menu: {error_msg}",
        ) from e

@router.post("/food/cart")
async def update_food_cart(
    request_body: dict,
    user: User = Depends(require_auth),
    db: Session = Depends(_get_db_session)
):
    """Update food cart."""
    import logging
    logger = logging.getLogger(__name__)
    
    token = get_user_token(user, db)
    if not token:
        raise HTTPException(status_code=400, detail="Not connected to Swiggy")
    
    restaurant_id = request_body.get("restaurant_id")
    cart_items = request_body.get("cart_items", [])
    address_id = request_body.get("address_id")
    
    logger.info(f"=== FOOD CART UPDATE DEBUG ===")
    logger.info(f"Restaurant ID: {restaurant_id}")
    logger.info(f"Address ID: {address_id}")
    logger.info(f"Items count: {len(cart_items)}")
    logger.info(f"Token length: {len(token) if token else 0}")
    
    try:
        result = await swiggy_mcp_client.update_food_cart(
            token, 
            restaurant_id, 
            cart_items, 
            address_id
        )
        logger.info(f"Cart update successful: {result}")
        return result
    except Exception as e:
        logger.exception(f"Cart update failed")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Error message: {str(e)}")
        raise HTTPException(
            status_code=502,
            detail=f"Unable to update Swiggy food cart: {str(e)}"
        )


@router.get("/food/menu-item-debug")
async def debug_menu_item(
    address_id: str,
    restaurant_id: str,
    item_name: str,
    user: User = Depends(require_auth),
    db: Session = Depends(_get_db_session),
):
    """
    Debug endpoint: shows all ID fields that Swiggy returns for a named menu item.
    Use this to identify which field to use as the cart itemId.
    """
    import logging
    logger = logging.getLogger(__name__)
    token = get_user_token(user, db)
    if not token:
        raise HTTPException(status_code=400, detail="Not connected to Swiggy")
    try:
        raw_menu = await swiggy_mcp_client.get_restaurant_menu(token, address_id, restaurant_id)
        raw_search = await swiggy_mcp_client.search_menu(token, address_id, item_name, restaurant_id=restaurant_id)
        normalize_name = lambda s: (s or "").lower().replace(" ", "")
        target = normalize_name(item_name)

        def extract_id_fields(item: dict) -> dict:
            return {
                k: item[k]
                for k in (
                    "id", "item_id", "itemId", "menu_item_id", "menuItemId",
                    "restaurantMenuItemId", "itemUniqueId", "uniqueId",
                    "dishId", "dish_id", "productId", "product_id",
                )
                if k in item
            }

        def find_items(obj, depth=0):
            found = []
            if depth > 8:
                return found
            if isinstance(obj, list):
                for el in obj:
                    found.extend(find_items(el, depth + 1))
            elif isinstance(obj, dict):
                name = obj.get("name") or obj.get("item_name") or obj.get("itemName") or ""
                if normalize_name(name) == target:
                    found.append({"name": name, "ids": extract_id_fields(obj)})
                for v in obj.values():
                    found.extend(find_items(v, depth + 1))
            return found

        menu_matches = find_items(raw_menu)
        search_matches = find_items(raw_search)
        logger.info(
            "debug_menu_item: item=%r restaurant=%s menu_matches=%s search_matches=%s",
            item_name, restaurant_id, menu_matches, search_matches
        )
        return {
            "item_name": item_name,
            "restaurant_id": restaurant_id,
            "menu_matches": menu_matches,
            "search_matches": search_matches,
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

@router.get("/food/menu-search")
async def search_menu_items(
    address_id: str,
    query: str,
    restaurant_id: str,
    offset: int = 0,
    user: User = Depends(require_auth),
    db: Session = Depends(_get_db_session),
):
    """Search additional dishes in one restaurant, including later result pages."""
    if not address_id or not restaurant_id or not query.strip():
        raise HTTPException(status_code=422, detail="address_id, restaurant_id, and query are required")
    if offset < 0:
        raise HTTPException(status_code=422, detail="offset cannot be negative")

    token = get_user_token(user, db)
    if not token:
        raise HTTPException(status_code=400, detail="Not connected to Swiggy")
    try:
        result = await swiggy_mcp_client.search_menu(
            token, address_id, query.strip(), restaurant_id=restaurant_id, offset=offset
        )
        failure = _mcp_failure_message(result)
        if failure:
            raise HTTPException(status_code=502, detail=failure)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Unable to search this restaurant's menu: {e}") from e

@router.post("/food/checkout-summary")
async def sync_food_cart_and_get_summary(
    request_body: dict,
    user: User = Depends(require_auth),
    db: Session = Depends(_get_db_session),
):
    """Replace the Swiggy cart with the browser cart, then read its live bill."""
    address_id = request_body.get("address_id")
    restaurant_id = request_body.get("restaurant_id")
    items = request_body.get("items")
    if not address_id or not restaurant_id or not isinstance(items, list) or not items:
        raise HTTPException(status_code=422, detail="address_id, restaurant_id, and non-empty items are required")

    normalized_items = []
    for item in items:
        if not isinstance(item, dict):
            raise HTTPException(status_code=422, detail="Each cart item must be an object")
        item_id = item.get("menu_item_id") or item.get("menuItemId") or item.get("id")
        quantity = item.get("quantity")
        if not item_id or isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
            raise HTTPException(status_code=422, detail="Each cart item needs a menu_item_id and positive integer quantity")
        normalized = {"menu_item_id": str(item_id), "quantity": quantity}
        for customization in ("variants", "variantsV2", "addons"):
            if isinstance(item.get(customization), list):
                normalized[customization] = item[customization]
        normalized_items.append(normalized)

    token = get_user_token(user, db)
    if not token:
        raise HTTPException(status_code=400, detail="Not connected to Swiggy")
    try:
        _, _, _, schema = await _update_food_cart_and_confirm(
            token, str(restaurant_id), str(address_id), normalized_items
        )
        # The documented cart-update flow is immediately followed by reading
        # the authenticated Swiggy cart. The GET handler uses that bill for the summary.
        summary = await get_food_payment_options(str(address_id), user, db)
        live_items = summary.get("cart_items")
        if not isinstance(live_items, list):
            raise HTTPException(status_code=502, detail="Swiggy returned a bill without cart contents, so the selected items could not be confirmed.")
        live_quantities = {}
        for item in live_items:
            if not isinstance(item, dict):
                continue
            item_id = item.get("menu_item_id") or item.get("menuItemId") or item.get("id")
            try:
                quantity = int(item.get("quantity", 0))
            except (TypeError, ValueError):
                continue
            if item_id:
                live_quantities[str(item_id)] = quantity
        expected_quantities = {item["menu_item_id"]: item["quantity"] for item in normalized_items}
        mismatches = {
            item_id: {"requested": quantity, "swiggy": live_quantities.get(item_id)}
            for item_id, quantity in expected_quantities.items()
            if live_quantities.get(item_id) != quantity
        }
        if mismatches:
            raise HTTPException(
                status_code=502,
                detail=f"Swiggy's cart did not confirm the requested item quantities ({mismatches}); the bill was not confirmed.",
            )
        extras = [item for item in live_items if isinstance(item, dict) and str(
            item.get("menu_item_id") or item.get("menuItemId") or item.get("id") or ""
        ) not in expected_quantities]
        if extras:
            extra_names = [
                f"{item.get('name', item.get('menu_item_id', 'Item'))} × {item.get('quantity', 1)}"
                for item in extras
            ]
            raise HTTPException(
                status_code=409,
                detail=f"Swiggy's cart contains additional items not shown in this cart ({', '.join(extra_names)}). Remove them from Swiggy and retry to get an accurate bill.",
            )
        summary["verified_by"] = schema
        return summary
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Unable to sync cart and fetch Swiggy bill: {e}") from e


@router.get("/food/payment-options")
async def get_food_payment_options(
    address_id: str,
    user: User = Depends(require_auth),
    db: Session = Depends(_get_db_session),
):
    """
    Fetch payment options and fee breakdown (delivery fee, GST, surge, grand total)
    from the Swiggy MCP for the current cart state at the given address.
    """
    token = get_user_token(user, db)
    if not token:
        raise HTTPException(status_code=400, detail="Not connected to Swiggy")

    try:
        # Payment options only contains payment methods. The actual fee lines
        # and payable total live on the Swiggy food cart response.
        cart = await swiggy_mcp_client.get_food_cart(token, address_id)
        cart_failure = _mcp_failure_message(cart)
        if cart_failure:
            raise HTTPException(status_code=502, detail=cart_failure)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Unable to fetch Swiggy's live food cart: {e}") from e

    # Payment methods are supplementary. A temporary failure here must not
    # discard the live bill already returned by get_food_cart.
    try:
        raw = await swiggy_mcp_client.get_payment_options(token, address_id)
        if _mcp_failure_message(raw):
            raw = {}
    except Exception:
        raw = {}

    def _pick(d: dict, *keys, default=None):
        return next((d[k] for k in keys if k in d), default)

    def _amount(value):
        if isinstance(value, dict):
            for key in ("amount", "value", "price", "total"):
                if key in value:
                    parsed = _amount(value[key])
                    if parsed is not None:
                        return parsed
            return None
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        if isinstance(value, str):
            import re
            numeric = re.sub(r"[^0-9.-]", "", value.replace(",", ""))
            try:
                return float(numeric) if numeric else None
            except ValueError:
                return None
        return None

    def _walk(node, path=()):
        if isinstance(node, list):
            for item in node:
                yield from _walk(item, path)
        elif isinstance(node, dict):
            label = _pick(node, "title", "name", "label", "displayName")
            value = _pick(node, "amount", "value", "price")
            if label and value is not None:
                amount = _amount(value)
                if amount is not None:
                    yield str(label), amount
            else:
                for key, child in node.items():
                    normalized_key = str(key).replace("_", "").lower()
                    charge_words = ("delivery", "packing", "packaging", "platform", "surge", "gst", "tax", "handling", "rain", "smallorder", "discount", "coupon", "fee")
                    if any(word in normalized_key for word in charge_words):
                        amount = _amount(child)
                        if amount is not None:
                            yield str(key).replace("_", " ").title(), amount
                    yield from _walk(child, path + (str(key),))
        elif path:
            key = path[-1]
            normalized = key.replace("_", "").lower()
            charge_words = ("delivery", "packing", "packaging", "platform", "surge", "gst", "tax", "handling", "rain", "smallorder", "discount", "coupon", "fee")
            if any(word in normalized for word in charge_words):
                amount = _amount(node)
                if amount is not None:
                    yield key.replace("_", " ").title(), amount

    def _find_total(node):
        if isinstance(node, dict):
            for key in ("toPay", "to_pay", "totalPayable", "total_payable", "grandTotal", "grand_total", "totalAmount", "total_amount", "orderTotal", "order_total"):
                if key in node:
                    amount = _amount(node[key])
                    if amount is not None:
                        return amount
            for child in node.values():
                found = _find_total(child)
                if found is not None:
                    return found
        elif isinstance(node, list):
            for child in node:
                found = _find_total(child)
                if found is not None:
                    return found
        return None

    def _find_named(node, wanted):
        if isinstance(node, dict):
            for key, value in node.items():
                if str(key).replace("_", "").lower() == wanted.replace("_", "").lower():
                    if value is None or value == {}:
                        continue
                    if isinstance(value, str):
                        try:
                            return json.loads(value)
                        except (ValueError, TypeError):
                            pass
                    return value
            for value in node.values():
                found = _find_named(value, wanted)
                if found is not None:
                    return found
        elif isinstance(node, list):
            for value in node:
                found = _find_named(value, wanted)
                if found is not None:
                    return found
        elif isinstance(node, str):
            try:
                decoded = json.loads(node)
            except (ValueError, TypeError):
                return None
            if isinstance(decoded, (dict, list)):
                return _find_named(decoded, wanted)
        return None

    live_items = _find_named(cart, "items")
    if isinstance(live_items, list) and not live_items:
        raise HTTPException(
            status_code=502,
            detail="Swiggy returned an empty cart after synchronization. The browser cart was not confirmed by Swiggy.",
        )

    # Bill details are nested under billBreakdown on Swiggy's cart response.
    breakdown = []
    seen = set()
    live_item_total = None
    pricing = _find_named(cart, "pricing")
    if isinstance(pricing, dict):
        live_item_total = _amount(_pick(pricing, "item_total", "itemTotal"))
        for keys, label in (
            (("delivery_charge", "deliveryCharge"), "Delivery fee"),
            (("taxes_and_charges", "taxesAndCharges"), "Taxes and charges"),
        ):
            amount = _amount(_pick(pricing, *keys))
            if amount is not None:
                breakdown.append({"label": label, "amount": amount})
                seen.add((label.lower(), amount))
                if "delivery" in keys[0]:
                    seen.add(("delivery charge", amount))

    for label, amount in _walk(cart):
        normalized_label = label.replace("_", " ").lower()
        if "item total" in normalized_label or "itemtotal" in normalized_label or "subtotal" in normalized_label:
            continue
        key = (normalized_label, amount)
        if key not in seen:
            breakdown.append({"label": label, "amount": amount})
            seen.add(key)

    grand_total = _amount(_pick(pricing, "to_pay", "toPay")) if isinstance(pricing, dict) else None
    if grand_total is None:
        grand_total = _find_total(cart)
    payment_methods = []

    if isinstance(raw, dict):
        methods_raw = _pick(raw, "allMethods", "paymentOptions", "payment_options", "methods", "paymentMethods")
        if isinstance(methods_raw, list):
            for method in methods_raw:
                if isinstance(method, str):
                    payment_methods.append(method)
                elif isinstance(method, dict):
                    name = _pick(method, "name", "type", "method", "id", default="")
                    if name:
                        payment_methods.append(str(name))

    return {
        "breakdown": breakdown,
        "item_total": live_item_total,
        "grand_total": grand_total,
        "breakdown_available": bool(breakdown or grand_total is not None),
        "payment_methods": payment_methods,
        "cart_items": live_items if isinstance(live_items, list) else None,
    }

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

@router.get("/instamart/cart")
async def get_instamart_cart(
    user: User = Depends(require_auth),
    db: Session = Depends(_get_db_session)
):
    """Get the current Instamart cart."""
    token = get_user_token(user, db)
    if not token:
        raise HTTPException(status_code=400, detail="Not connected to Swiggy")

    try:
        cart = await swiggy_instamart_mcp.get_cart(token)
        failure = _mcp_failure_message(cart)
        if failure:
            raise HTTPException(status_code=502, detail=failure)
        return cart
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Unable to load Instamart cart: {e}") from e

@router.post("/instamart/cart")
async def update_instamart_cart(
    request_body: dict,
    user: User = Depends(require_auth),
    db: Session = Depends(_get_db_session)
):
    """Update the Instamart cart (add/update/remove items)."""
    import logging
    logger = logging.getLogger(__name__)
    
    token = get_user_token(user, db)
    if not token:
        raise HTTPException(status_code=400, detail="Not connected to Swiggy")

    address_id = request_body.get("address_id")
    items = request_body.get("items", [])  # [{spinId: "...", quantity: 1}]
    
    logger.info(f"=== INSTAMART CART UPDATE DEBUG ===")
    logger.info(f"Address ID: {address_id}")
    logger.info(f"Items count: {len(items)}")
    logger.info(f"Items: {items}")
    logger.info(f"Token present: {bool(token)}")

    if not address_id:
        # Try to get default address
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
            logger.info(f"Auto-detected address ID: {address_id}")
        except Exception as addr_err:
            logger.error(f"Failed to auto-detect address: {addr_err}")
            pass

    if not address_id:
        raise HTTPException(status_code=400, detail="No delivery address found")

    try:
        result = await swiggy_instamart_mcp.update_cart(token, str(address_id), items)
        logger.info(f"Cart update result: {result}")
        failure = _mcp_failure_message(result)
        if failure:
            logger.error(f"Cart update failed with message: {failure}")
            raise HTTPException(status_code=502, detail=failure)
        return {"success": True, "cart": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Instamart cart update exception")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Error message: {str(e)}")
        raise HTTPException(status_code=502, detail=f"Unable to update Instamart cart: {e}") from e

@router.delete("/instamart/cart")
async def clear_instamart_cart(
    user: User = Depends(require_auth),
    db: Session = Depends(_get_db_session)
):
    """Clear the Instamart cart."""
    token = get_user_token(user, db)
    if not token:
        raise HTTPException(status_code=400, detail="Not connected to Swiggy")

    try:
        result = await swiggy_instamart_mcp.clear_cart(token)
        failure = _mcp_failure_message(result)
        if failure:
            raise HTTPException(status_code=502, detail=failure)
        return {"success": True, "cart": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Unable to clear Instamart cart: {e}") from e

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
            "order_id": o.order_id,
            "restaurant_name": o.restaurant_name,
            "restaurant_area": o.restaurant_locality or "",
            "restaurant_locality": o.restaurant_locality or "",
            "restaurant_city": o.restaurant_city or "",
            "order_total": float(o.order_total) if o.order_total else 0,
            "order_time": o.order_time.isoformat() if o.order_time else None,
            "delivery_time": None,  # Not available in current schema
            "is_veg": any(item.is_veg for item in items) if items else False,
            "order_items": [item.name for item in items],
            "items": [
                {
                    "item_id": item.item_id,
                    "name": item.name,
                    "quantity": item.quantity,
                    "price": item.price,
                    "is_veg": item.is_veg
                } for item in items
            ],
            "cuisines": o.cuisine_list,
            "order_status": o.order_status,
            "payment_method": o.payment_method
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

        # Transform to frontend expected format
        formatted_venues = []
        for v in venues:
            if isinstance(v, dict):
                formatted_venues.append({
                    "id": v.get("id") or v.get("restaurantId") or v.get("restaurant_id") or "",
                    "name": v.get("name") or v.get("restaurantName") or "",
                    "cuisine": v.get("cuisine") or v.get("cuisines") or [],
                    "rating": v.get("rating") or 0,
                    "cost_for_two": v.get("costForTwo") or v.get("cost_for_two") or "",
                    "location": v.get("location") or v.get("locality") or v.get("area") or "",
                    "image_url": v.get("imageUrl") or v.get("image_url") or v.get("cloudinaryImageId") or ""
                })

        return {"venues": formatted_venues}
    except Exception as e:
        logger.exception("Dineout search failed")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/dineout/slots")
async def get_dineout_slots(
    restaurant_id: str,
    date: str,
    user: User = Depends(require_auth),
    db: Session = Depends(_get_db_session)
):
    """Get available booking slots for a Dineout restaurant."""
    token = get_user_token(user, db)
    if not token:
        raise HTTPException(status_code=400, detail="Not connected to Swiggy")

    # Get user's address for lat/lng
    addresses = await swiggy_mcp_client.get_addresses(token)
    address = addresses[0] if addresses else {}
    lat = address.get("latitude") or address.get("lat") or 0.0
    lng = address.get("longitude") or address.get("lng") or 0.0

    try:
        slots = await swiggy_dineout_mcp.get_available_slots(token, restaurant_id, date, float(lat), float(lng))
        return slots
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
