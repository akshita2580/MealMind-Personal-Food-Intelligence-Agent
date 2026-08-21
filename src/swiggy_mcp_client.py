"""
Client for calling the official Swiggy Food MCP server.

Uses the stored OAuth access token to call get_addresses and get_food_orders
via the MCP JSON-RPC protocol on https://mcp.swiggy.com/food.
"""
import logging
from typing import Any
from src.mcp_transport import mcp_call, extract_mcp_result

logger = logging.getLogger(__name__)

SWIGGY_FOOD_MCP_URL = "https://mcp.swiggy.com/food"


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

    orders = []
    if isinstance(data, list):
        orders = data
    elif isinstance(data, dict) and "orders" in data:
        orders = data["orders"]
    elif isinstance(data, dict) and "statusCode" in data:
        orders = data.get("orders", [])
        if not isinstance(orders, list):
            orders = []
            
    logger.info("get_food_orders diagnostic: order_count=%d", len(orders))
    return orders

async def search_restaurants(access_token: str, address_id: str, query: str) -> dict:
    resp = await _mcp_call(access_token, "search_restaurants", {"addressId": address_id, "query": query})
    return _extract_result(resp, "search_restaurants")

async def search_menu(access_token: str, address_id: str, query: str, restaurant_id: str = "") -> dict:
    payload = {"addressId": address_id, "query": query}
    if restaurant_id:
        payload["restaurantIdOfAddedItem"] = restaurant_id
    resp = await _mcp_call(access_token, "search_menu", payload)
    return _extract_result(resp, "search_menu")

async def get_restaurant_menu(access_token: str, address_id: str, restaurant_id: str) -> dict:
    resp = await _mcp_call(access_token, "get_restaurant_menu", {"addressId": address_id, "restaurantId": restaurant_id})
    return _extract_result(resp, "get_restaurant_menu")

async def update_food_cart(access_token: str, restaurant_id: str, cart_items: list, address_id: str) -> dict:
    resp = await _mcp_call(access_token, "update_food_cart", {
        "restaurantId": restaurant_id,
        "cartItems": cart_items,
        "addressId": address_id,
        "cutleryOptIn": False
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


