import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from src.instamart_ordering_flow import (
    start_instamart_flow, handle_im_address_selection, handle_grocery_search,
    handle_im_item_selection, show_im_cart, proceed_to_im_payment,
    confirm_im_payment_and_place_order, check_im_upi_status, cancel_im_flow,
    SELECT_IM_ADDRESS, SEARCH_GROCERY, SELECT_GROCERY_ITEM, VIEW_IM_CART,
    SELECT_IM_PAYMENT, IM_PAYMENT_PENDING
)
from telegram.ext import ConversationHandler

@pytest.fixture
def mock_update():
    update = MagicMock()
    update.effective_user.id = "user123"
    update.callback_query = AsyncMock()
    update.message = AsyncMock()
    return update

@pytest.fixture
def mock_context():
    context = MagicMock()
    context.user_data = {}
    return context

@pytest.mark.asyncio
@patch("src.instamart_ordering_flow.get_user_access_token", return_value="token123")
@patch("src.swiggy_mcp_client.get_addresses", new_callable=AsyncMock)
async def test_start_instamart_flow(mock_get_addr, mock_token, mock_update, mock_context):
    mock_get_addr.return_value = [{"id": "addr1", "addressTag": "Home"}]
    
    state = await start_instamart_flow(mock_update, mock_context)
    
    assert state == SELECT_IM_ADDRESS
    assert mock_context.user_data["im_order_flow"]["token"] == "token123"
    assert mock_update.callback_query.edit_message_text.called
    args = mock_update.callback_query.edit_message_text.call_args[0]
    assert "Please select a delivery address" in args[0]

@pytest.mark.asyncio
async def test_handle_im_address_selection(mock_update, mock_context):
    mock_context.user_data["im_order_flow"] = {}
    mock_update.callback_query.data = "imaddr_addr1"
    
    state = await handle_im_address_selection(mock_update, mock_context)
    
    assert state == SEARCH_GROCERY
    assert mock_context.user_data["im_order_flow"]["address_id"] == "addr1"

@pytest.mark.asyncio
@patch("src.swiggy_instamart_mcp.search_products", new_callable=AsyncMock)
async def test_handle_grocery_search(mock_search, mock_update, mock_context):
    mock_context.user_data["im_order_flow"] = {"token": "token123", "address_id": "addr1"}
    mock_update.message.text = "milk"
    
    mock_search.return_value = {
        "products": [
            {
                "displayName": "Milk",
                "variations": [
                    {"spinId": "spin1", "quantityDescription": "1L", "price": {"offerPrice": 50}}
                ]
            }
        ]
    }
    
    state = await handle_grocery_search(mock_update, mock_context)
    
    assert state == SELECT_GROCERY_ITEM
    mock_update.message.reply_text.assert_called_with("🔍 Searching Instamart for 'milk'...")

@pytest.mark.asyncio
@patch("src.swiggy_instamart_mcp.update_cart", new_callable=AsyncMock)
@patch("src.instamart_ordering_flow.show_im_cart", new_callable=AsyncMock)
async def test_handle_im_item_selection(mock_show_cart, mock_update_cart, mock_update, mock_context):
    mock_context.user_data["im_order_flow"] = {"token": "token123", "address_id": "addr1", "cart_items": []}
    mock_update.callback_query.data = "imitem_spin1"
    mock_show_cart.return_value = VIEW_IM_CART
    
    state = await handle_im_item_selection(mock_update, mock_context)
    
    assert state == VIEW_IM_CART
    mock_update_cart.assert_called_with("token123", "addr1", [{"spinId": "spin1", "quantity": 1}])

@pytest.mark.asyncio
@patch("src.swiggy_instamart_mcp.get_cart", new_callable=AsyncMock)
async def test_show_im_cart(mock_get_cart, mock_update, mock_context):
    mock_context.user_data["im_order_flow"] = {"token": "token123", "address_id": "addr1"}
    
    mock_get_cart.return_value = {
        "items": [{"itemName": "Milk", "quantity": 1, "discountedFinalPrice": 50}],
        "billBreakdown": {"toPay": {"value": "₹50"}}
    }
    
    state = await show_im_cart(mock_update, mock_context)
    
    assert state == VIEW_IM_CART
    mock_update.callback_query.edit_message_text.assert_called()

@pytest.mark.asyncio
@patch("src.swiggy_instamart_mcp.get_cart", new_callable=AsyncMock)
@patch("src.swiggy_instamart_mcp.get_payment_options", new_callable=AsyncMock)
async def test_proceed_to_im_payment(mock_payment_opts, mock_get_cart, mock_update, mock_context):
    mock_context.user_data["im_order_flow"] = {"token": "token123", "address_id": "addr1"}
    
    mock_get_cart.return_value = {"billBreakdown": {"toPay": {"value": "₹50"}}}
    mock_payment_opts.return_value = {"paymentMethods": [{"type": "Cash"}]}
    
    state = await proceed_to_im_payment(mock_update, mock_context)
    
    assert state == SELECT_IM_PAYMENT

@pytest.mark.asyncio
@patch("src.swiggy_instamart_mcp.checkout", new_callable=AsyncMock)
async def test_confirm_im_payment_and_place_order(mock_checkout, mock_update, mock_context):
    mock_context.user_data["im_order_flow"] = {"token": "token123", "address_id": "addr1"}
    mock_update.callback_query.data = "impay_Cash"
    
    mock_checkout.return_value = {"status": "PLACED"}
    
    state = await confirm_im_payment_and_place_order(mock_update, mock_context)
    
    assert state == ConversationHandler.END
    mock_checkout.assert_called_with("token123", "addr1", "Cash")
