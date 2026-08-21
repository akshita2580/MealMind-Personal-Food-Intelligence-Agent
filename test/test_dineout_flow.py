import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from src.dineout_booking_flow import (
    start_dineout_flow, handle_do_address_selection, handle_dining_search,
    handle_do_venue_selection, handle_do_slot_selection, handle_do_guest_selection,
    confirm_do_booking, cancel_do_flow,
    SELECT_DO_ADDRESS, SEARCH_DINING, SELECT_DINING_VENUE, SELECT_DATE_TIME,
    SELECT_GUEST_COUNT, CONFIRM_BOOKING
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
@patch("src.dineout_booking_flow.get_user_access_token", return_value="token123")
@patch("src.swiggy_mcp_client.get_addresses", new_callable=AsyncMock)
async def test_start_dineout_flow(mock_get_addr, mock_token, mock_update, mock_context):
    mock_get_addr.return_value = [{"id": "addr1", "addressTag": "Home", "latitude": 19.0, "longitude": 72.0}]
    
    state = await start_dineout_flow(mock_update, mock_context)
    
    assert state == SELECT_DO_ADDRESS
    assert mock_context.user_data["do_flow"]["token"] == "token123"

@pytest.mark.asyncio
async def test_handle_do_address_selection(mock_update, mock_context):
    mock_context.user_data["do_flow"] = {
        "addresses": [{"id": "addr1", "latitude": 19.0, "longitude": 72.0}]
    }
    mock_update.callback_query.data = "doaddr_addr1"
    
    state = await handle_do_address_selection(mock_update, mock_context)
    
    assert state == SEARCH_DINING
    assert mock_context.user_data["do_flow"]["address_id"] == "addr1"
    assert mock_context.user_data["do_flow"]["lat"] == 19.0
    assert mock_context.user_data["do_flow"]["lng"] == 72.0

@pytest.mark.asyncio
@patch("src.swiggy_dineout_mcp.search_restaurants_dineout", new_callable=AsyncMock)
async def test_handle_dining_search(mock_search, mock_update, mock_context):
    mock_context.user_data["do_flow"] = {"token": "token123", "address_id": "addr1"}
    mock_update.message.text = "pizza"
    
    mock_search.return_value = {
        "restaurants": [
            {"id": "rest1", "name": "Pizza Hut"}
        ]
    }
    
    state = await handle_dining_search(mock_update, mock_context)
    
    assert state == SELECT_DINING_VENUE
    mock_update.message.reply_text.assert_called_with("🔍 Searching Dineout for 'pizza'...")

@pytest.mark.asyncio
@patch("src.swiggy_dineout_mcp.get_available_slots", new_callable=AsyncMock)
async def test_handle_do_venue_selection(mock_slots, mock_update, mock_context):
    mock_context.user_data["do_flow"] = {"token": "token123", "lat": 19.0, "lng": 72.0}
    mock_update.callback_query.data = "dorest_rest1"
    
    mock_slots.return_value = {
        "slots": [
            {
                "timeString": "19:00",
                "reservationTime": 1700000000,
                "deals": [{"slotId": 123, "itemId": "item1"}]
            }
        ]
    }
    
    state = await handle_do_venue_selection(mock_update, mock_context)
    
    assert state == SELECT_DATE_TIME
    assert mock_context.user_data["do_flow"]["restaurant_id"] == "rest1"

@pytest.mark.asyncio
async def test_handle_do_slot_selection(mock_update, mock_context):
    mock_context.user_data["do_flow"] = {}
    mock_update.callback_query.data = "doslt_123_item1_1700000000"
    
    state = await handle_do_slot_selection(mock_update, mock_context)
    
    assert state == SELECT_GUEST_COUNT
    assert mock_context.user_data["do_flow"]["slot_id"] == 123
    assert mock_context.user_data["do_flow"]["item_id"] == "item1"
    assert mock_context.user_data["do_flow"]["reservation_time"] == 1700000000

@pytest.mark.asyncio
async def test_handle_do_guest_selection(mock_update, mock_context):
    mock_context.user_data["do_flow"] = {}
    mock_update.callback_query.data = "doguest_2"
    
    state = await handle_do_guest_selection(mock_update, mock_context)
    
    assert state == CONFIRM_BOOKING
    assert mock_context.user_data["do_flow"]["guests"] == 2

@pytest.mark.asyncio
@patch("src.swiggy_dineout_mcp.book_table", new_callable=AsyncMock)
async def test_confirm_do_booking(mock_book, mock_update, mock_context):
    mock_context.user_data["do_flow"] = {
        "token": "token123",
        "restaurant_id": "rest1",
        "slot_id": 123,
        "item_id": "item1",
        "reservation_time": 1700000000,
        "guests": 2,
        "lat": 19.0,
        "lng": 72.0
    }
    mock_update.callback_query.data = "doconfirm"
    
    mock_book.return_value = {"status": "CONFIRMED"}
    
    state = await confirm_do_booking(mock_update, mock_context)
    
    assert state == ConversationHandler.END
    mock_book.assert_called_with("token123", "rest1", 123, "item1", 1700000000, 2, 19.0, 72.0)
