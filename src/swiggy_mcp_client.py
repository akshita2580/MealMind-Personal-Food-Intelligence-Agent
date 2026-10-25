"""
Client for calling the official Swiggy Food MCP server.

Uses the stored OAuth access token to call get_addresses and get_food_orders
via the MCP JSON-RPC protocol on https://mcp.swiggy.com/food.
"""
import logging
import os
from typing import Any
from .mcp_transport import mcp_call, extract_mcp_result

logger = logging.getLogger(__name__)

SWIGGY_FOOD_MCP_URL = os.getenv("SWIGGY_FOOD_MCP_URL", "https://mcp.swiggy.com/food")


async def _mcp_call(access_token: str, tool_name: str, arguments: dict[str, Any]) -> dict:
    return await mcp_call(access_token, SWIGGY_FOOD_MCP_URL, tool_name, arguments)


def _extract_result(response: dict, tool_name: str) -> Any:
    return extract_mcp_result(response, tool_name)


async def get_addresses(access_token: str) -> list[dict]:
    """
    Call get_addresses on the Swiggy Food MCP to retrieve the user's
    saved delivery addresses. Returns a list of address dicts.
    """
    resp = await _mcp_call(access_token, "get_addresses", {})
    data = _extract_result(resp, "get_addresses")

    logger.info("get_addresses diagnostic: HTTP status=200, success=True")
    
    if isinstance(data, dict):
        logger.info("get_addresses diagnostic: response_keys=%s", list(data.keys()))
    else:
        logger.info("get_addresses diagnostic: response is type %s", type(data))

    addresses = []
    if isinstance(data, list):
        addresses = data
    elif isinstance(data, dict) and "addresses" in data:
        addresses = data["addresses"]
    elif isinstance(data, dict) and "id" in data:
        addresses = [data]
        
    logger.info("get_addresses diagnostic: address_count=%d", len(addresses))
    return addresses


async def get_food_orders(access_token: str, address_id: str) -> list[dict]:
    """
    Call get_food_orders on the Swiggy Food MCP to retrieve the user's
    order history. Returns a list of order dicts.
    """
    logger.info("get_food_orders diagnostic: calling with addressId=%s, activeOnly unset", address_id)
    resp = await _mcp_call(
        access_token,
        "get_food_orders",
        {"addressId": address_id},
    )
    data = _extract_result(resp, "get_food_orders")

    if isinstance(data, dict):
        logger.info("get_food_orders diagnostic: response_keys=%s", list(data.keys()))
    else:
        logger.info("get_food_orders diagnostic: response is type %s", type(data))

    # MCP servers may wrap the order list in different envelopes. Walk the
    # known wrappers rather than treating a successful but nested response as
    # an empty history.
    orders = data if isinstance(data, list) else []
    candidate = data
    for _ in range(4):
        if orders:
            break
        if not isinstance(candidate, dict):
            break
        found = False
        for key in ("orders", "data", "result", "orderHistory", "history"):
            nested = candidate.get(key)
            if isinstance(nested, list):
                orders = nested
                found = True
                break
            if isinstance(nested, dict):
                candidate = nested
                found = True
                break
        if not found:
            break

    if not isinstance(orders, list):
        orders = []
    orders = [order for order in orders if isinstance(order, dict)]
            
    logger.info("get_food_orders diagnostic: order_count=%d", len(orders))
    return orders

async def search_restaurants(access_token: str, address_id: str, query: str) -> dict:
    resp = await _mcp_call(access_token, "search_restaurants", {"addressId": address_id, "query": query})
    return _extract_result(resp, "search_restaurants")

async def search_menu(
    access_token: str,
    address_id: str,
    query: str,
    restaurant_id: str = "",
    offset: int = 0,
) -> dict:
    payload = {"addressId": address_id, "query": query}
    if restaurant_id:
        payload["restaurantIdOfAddedItem"] = restaurant_id
    if offset > 0:
        payload["offset"] = offset
    resp = await _mcp_call(access_token, "search_menu", payload)
    return _extract_result(resp, "search_menu")

async def get_restaurant_menu(
    access_token: str,
    address_id: str,
    restaurant_id: str,
    page: int = 1,
    page_size: int = 5,
) -> dict:
    """Get one page of a restaurant menu using Swiggy's pagination schema."""
    if not address_id or not restaurant_id:
        raise ValueError("address_id and restaurant_id are required to fetch a menu")
    if page < 1 or page_size < 1 or page_size > 8:
        raise ValueError("page must be positive and page_size must be between 1 and 8")

    arguments = {"addressId": str(address_id), "restaurantId": str(restaurant_id)}
    if page != 1 or page_size != 5:
        arguments.update({"page": page, "pageSize": page_size})
    resp = await _mcp_call(access_token, "get_restaurant_menu", arguments)
    return _extract_result(resp, "get_restaurant_menu")

def _clean_cart_item(item: dict, id_as_int: bool = False, include_aliases: bool = False) -> dict:
    item_id = (
        item.get("menu_item_id")
        or item.get("menuItemId")
        or item.get("id")
        or item.get("itemId")
        or item.get("item_id")
        or item.get("restaurantMenuItemId")
    )
    if not item_id:
        return {}

    qty = int(item.get("quantity", 1))
    formatted_id = int(item_id) if (id_as_int and str(item_id).isdigit()) else str(item_id)

    cleaned = {
        "menu_item_id": formatted_id,
        "quantity": qty,
    }

    if include_aliases:
        cleaned["itemId"] = str(item_id)
        cleaned["item_id"] = str(item_id)
        cleaned["id"] = str(item_id)

    # Customizations conforming to Swiggy MCP schema
    if item.get("variants") and isinstance(item["variants"], list):
        cleaned["variants"] = item["variants"]
    elif item.get("variantsV2") and isinstance(item["variantsV2"], list):
        cleaned["variantsV2"] = item["variantsV2"]
    if item.get("addons") and isinstance(item["addons"], list):
        cleaned["addons"] = item["addons"]

    return cleaned


async def update_food_cart(access_token: str, restaurant_id: str, cart_items: list, address_id: str) -> dict:
    """
    Standard official schema for Swiggy Food MCP update_food_cart.
    Requires menu_item_id (string) and quantity (number).
    """
    cleaned = [_clean_cart_item(i) for i in cart_items if isinstance(i, dict)]
    cleaned = [i for i in cleaned if i]
    # #region agent log
    try:
        import json, time
        with open(r"c:\Users\Akshita\Desktop\MealMind-Personal-Food-Intelligence-Agent\debug-dad6f0.log", "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"sessionId":"dad6f0","runId":"pre-fix","hypothesisId":"H5","location":"swiggy_mcp_client.py:update_food_cart","message":"cleaned MCP cartItems","data":{"mcp_url":SWIGGY_FOOD_MCP_URL,"restaurant_id":str(restaurant_id),"cleaned":cleaned},"timestamp":int(time.time()*1000)}, default=str)+"\n")
    except Exception:
        pass
    # #endregion
    resp = await _mcp_call(access_token, "update_food_cart", {
        "restaurantId": str(restaurant_id),
        "cartItems": cleaned,
        "addressId": str(address_id),
        "cutleryOptIn": False,
    })
    return _extract_result(resp, "update_food_cart")


async def update_food_cart_int_id(access_token: str, restaurant_id: str, cart_items: list, address_id: str) -> dict:
    """Fallback schema with integer menu_item_id if ID is all digits."""
    cleaned = [_clean_cart_item(i, id_as_int=True) for i in cart_items if isinstance(i, dict)]
    cleaned = [i for i in cleaned if i]
    resp = await _mcp_call(access_token, "update_food_cart", {
        "restaurantId": str(restaurant_id),
        "cartItems": cleaned,
        "addressId": str(address_id),
        "cutleryOptIn": False,
    })
    return _extract_result(resp, "update_food_cart")


async def update_food_cart_compat(access_token: str, restaurant_id: str, cart_items: list, address_id: str) -> dict:
    """Compatibility schema with itemId and menu_item_id aliases."""
    cleaned = [_clean_cart_item(i, include_aliases=True) for i in cart_items if isinstance(i, dict)]
    cleaned = [i for i in cleaned if i]
    resp = await _mcp_call(access_token, "update_food_cart", {
        "restaurantId": str(restaurant_id),
        "cartItems": cleaned,
        "addressId": str(address_id),
        "cutleryOptIn": False,
    })
    return _extract_result(resp, "update_food_cart")

async def get_food_cart(access_token: str, address_id: str) -> dict:
    resp = await _mcp_call(access_token, "get_food_cart", {"addressId": address_id})
    return _extract_result(resp, "get_food_cart")

async def flush_food_cart(access_token: str) -> dict:
    resp = await _mcp_call(access_token, "flush_food_cart", {})
    return _extract_result(resp, "flush_food_cart")

async def get_payment_options(access_token: str, address_id: str) -> dict:
    resp = await _mcp_call(access_token, "get_payment_options", {"addressId": address_id})
    return _extract_result(resp, "get_payment_options")

async def place_food_order(access_token: str, address_id: str, payment_method: str = "Cash") -> dict:
    resp = await _mcp_call(access_token, "place_food_order", {
        "addressId": address_id,
        "paymentMethod": payment_method
    })
    return _extract_result(resp, "place_food_order")

async def check_payment_status(access_token: str, paas_id: str, order_id: str, address_id: str) -> dict:
    resp = await _mcp_call(access_token, "check_payment_status", {
        "paasId": paas_id,
        "orderId": order_id,
        "addressId": address_id
    })
    return _extract_result(resp, "check_payment_status")

async def confirm_order(access_token: str, order_id: str, address_id: str, lat: float, lng: float) -> dict:
    resp = await _mcp_call(access_token, "confirm_order", {
        "orderId": order_id,
        "addressId": address_id,
        "lat": lat,
        "lng": lng
    })
    return _extract_result(resp, "confirm_order")

async def get_food_order_details(access_token: str, order_id: str) -> dict:
    resp = await _mcp_call(access_token, "get_food_order_details", {"orderId": order_id})
    return _extract_result(resp, "get_food_order_details")

async def track_food_order(access_token: str, order_id: str) -> dict:
    resp = await _mcp_call(access_token, "track_food_order", {"orderId": order_id})
    return _extract_result(resp, "track_food_order")

async def get_food_delivery_status(access_token: str, order_id: str) -> dict:
    resp = await _mcp_call(access_token, "get_food_delivery_status", {"orderId": order_id})
    return _extract_result(resp, "get_food_delivery_status")

async def fetch_food_coupons(access_token: str, restaurant_id: str, address_id: str) -> dict:
    resp = await _mcp_call(access_token, "fetch_food_coupons", {"restaurantId": restaurant_id, "addressId": address_id})
    return _extract_result(resp, "fetch_food_coupons")

async def apply_food_coupon(access_token: str, coupon_code: str, address_id: str, cart_id: str) -> dict:
    resp = await _mcp_call(access_token, "apply_food_coupon", {"couponCode": coupon_code, "addressId": address_id, "cartId": cart_id})
    return _extract_result(resp, "apply_food_coupon")


