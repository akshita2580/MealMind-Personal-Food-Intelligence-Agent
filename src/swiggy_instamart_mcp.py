import logging
from typing import Any
from src.mcp_transport import mcp_call, extract_mcp_result

logger = logging.getLogger(__name__)

SWIGGY_INSTAMART_MCP_URL = "https://mcp.swiggy.com/im"

async def _mcp_call(access_token: str, tool_name: str, arguments: dict[str, Any]) -> dict:
    return await mcp_call(access_token, SWIGGY_INSTAMART_MCP_URL, tool_name, arguments)

def _extract_result(response: dict, tool_name: str) -> Any:
    return extract_mcp_result(response, tool_name)

async def search_products(access_token: str, address_id: str, query: str, offset: int = 0) -> dict:
    """Search for groceries on Instamart."""
    resp = await _mcp_call(access_token, "search_products", {
        "addressId": address_id,
        "query": query,
        "offset": offset
    })
    return _extract_result(resp, "search_products")

async def get_cart(access_token: str, address_id: str) -> dict:
    """Get the current Instamart cart."""
    resp = await _mcp_call(access_token, "get_cart", {
        "addressId": address_id
    })
    return _extract_result(resp, "get_cart")

async def update_cart(access_token: str, address_id: str, items: list) -> dict:
    """Update the Instamart cart.
    items should be a list of dicts: [{'spinId': '...', 'quantity': 1}]
    """
    resp = await _mcp_call(access_token, "update_cart", {
        "selectedAddressId": address_id,
        "items": items
    })
    return _extract_result(resp, "update_cart")

async def clear_cart(access_token: str) -> dict:
    """Clear the current Instamart cart."""
    resp = await _mcp_call(access_token, "clear_cart", {})
    return _extract_result(resp, "clear_cart")

async def checkout(access_token: str, address_id: str, payment_method: str = "Cash") -> dict:
    """Place an Instamart order."""
    args = {
        "addressId": address_id,
        "paymentMethod": payment_method
    }
    resp = await _mcp_call(access_token, "checkout", args)
    return _extract_result(resp, "checkout")

async def get_payment_options(access_token: str, address_id: str) -> dict:
    resp = await _mcp_call(access_token, "get_payment_options", {
        "addressId": address_id
    })
    return _extract_result(resp, "get_payment_options")

async def check_payment_status(access_token: str, paas_id: str, order_id: str, address_id: str) -> dict:
    resp = await _mcp_call(access_token, "check_payment_status", {
        "paasId": paas_id,
        "orderId": order_id,
        "addressId": address_id
    })
    return _extract_result(resp, "check_payment_status")

async def confirm_order(access_token: str, order_id: str, address_id: str) -> dict:
    resp = await _mcp_call(access_token, "confirm_order", {
        "orderId": order_id,
        "addressId": address_id
    })
    return _extract_result(resp, "confirm_order")
