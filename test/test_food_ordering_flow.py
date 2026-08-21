import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.food_ordering_flow import (
    start_order_flow, handle_address_selection, handle_restaurant_search,
    handle_restaurant_selection, handle_menu_item_selection, show_cart,
    proceed_to_payment, confirm_payment_and_place_order, check_upi_status,
    handle_cart_callback, handle_active_order_callback
)

@pytest.mark.asyncio
async def test_order_flow_start():
    update = MagicMock()
    update.effective_user.id = "test_user"
    update.callback_query = AsyncMock()
    context = MagicMock()
    context.user_data = {}
    
    with patch("src.food_ordering_flow.get_user_access_token", return_value="token"):
        with patch("src.swiggy_mcp_client.get_addresses", new_callable=AsyncMock, return_value=[{"id": "addr1", "annotation": "Home"}]):
            state = await start_order_flow(update, context)
            
    assert state == 0 # SELECT_ADDRESS
    assert context.user_data["order_flow"]["token"] == "token"
    update.callback_query.edit_message_text.assert_called()

@pytest.mark.asyncio
async def test_handle_cart_callback():
    update = MagicMock()
    update.effective_user.id = "test_user"
    update.callback_query = AsyncMock()
    context = MagicMock()
    
    with patch("src.food_ordering_flow.get_user_access_token", return_value="token"):
        with patch("src.swiggy_mcp_client.get_addresses", new_callable=AsyncMock, return_value=[{"id": "addr1"}]):
            with patch("src.swiggy_mcp_client.get_food_cart", new_callable=AsyncMock, return_value={"items": [{"name": "Burger", "price": 10000}], "cartTotal": 10000}):
                await handle_cart_callback(update, context)
                
    update.callback_query.message.reply_text.assert_called()

@pytest.mark.asyncio
async def test_handle_active_order_callback():
    update = MagicMock()
    update.effective_user.id = "test_user"
    update.callback_query = AsyncMock()
    context = MagicMock()
    
    with patch("src.food_ordering_flow.get_user_access_token", return_value="token"):
        with patch("src.swiggy_mcp_client.get_addresses", new_callable=AsyncMock, return_value=[{"id": "addr1"}]):
            with patch("src.swiggy_mcp_client._mcp_call", new_callable=AsyncMock, return_value={"result": {"structuredContent": {"orders": [{"isActiveOrder": True, "orderId": "123", "orderStatus": "PENDING"}]}}}):
                await handle_active_order_callback(update, context)
                
    update.callback_query.message.reply_text.assert_called()
