"""
Tests for the /sync command and Swiggy MCP sync flow.

Tests cover:
1. /sync when user is not connected -> OAuth connect flow is offered
2. /sync when user is already connected -> sync is attempted
3. No dummy orders are returned
4. If real orders are retrieved -> stored with correct user_id
5. User A cannot see User B's orders
6. All data tools use only current user's orders
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from sqlmodel import select
from src.database import get_session
from src.models import User, Order, SwiggyConnection
from src.telegram_bot import (
    is_user_connected,
    get_user_id,
    get_user_access_token,
    _build_oauth_url,
    _do_sync,
)


from sqlmodel import delete
from src.models import OrderItem, OrderCuisine, OAuthState

@pytest.fixture(autouse=True)
def clean_db():
    """Ensure a clean DB state before each test."""
    with get_session() as session:
        session.exec(delete(OrderItem))
        session.exec(delete(OrderCuisine))
        session.exec(delete(Order))
        session.exec(delete(SwiggyConnection))
        session.exec(delete(OAuthState))
        session.exec(delete(User))
        session.commit()
    yield
    with get_session() as session:
        session.exec(delete(OrderItem))
        session.exec(delete(OrderCuisine))
        session.exec(delete(Order))
        session.exec(delete(SwiggyConnection))
        session.exec(delete(OAuthState))
        session.exec(delete(User))
        session.commit()


def _create_connected_user(telegram_id="test_user_sync", encrypted_token="fake_encrypted"):
    """Helper to create a user with a CONNECTED SwiggyConnection."""
    with get_session() as session:
        user = User(telegram_id=telegram_id)
        session.add(user)
        session.commit()
        session.refresh(user)

        conn = SwiggyConnection(
            user_id=user.id,
            status="CONNECTED",
            access_token=encrypted_token,
        )
        session.add(conn)
        session.commit()
        return user.id


def _create_disconnected_user(telegram_id="test_user_disconnected"):
    """Helper to create a user without a SwiggyConnection."""
    with get_session() as session:
        user = User(telegram_id=telegram_id)
        session.add(user)
        session.commit()
        return user.id


# -------------------------------------------------------------------
# Test 1: /sync when not connected offers OAuth
# -------------------------------------------------------------------

def test_sync_not_connected_shows_false():
    """When user has no connection, is_user_connected returns False."""
    _create_disconnected_user("not_connected")
    assert is_user_connected("not_connected") is False


def test_sync_connected_shows_true():
    """When user has CONNECTED status, is_user_connected returns True."""
    _create_connected_user("connected_user")
    assert is_user_connected("connected_user") is True


# -------------------------------------------------------------------
# Test 2: _build_oauth_url generates a valid URL
# -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_build_oauth_url_generates_url():
    """_build_oauth_url should return a URL string when DCR succeeds."""
    _create_disconnected_user("oauth_user")

    with patch("src.dcr.get_or_register_client", new_callable=AsyncMock, return_value="test_client_id"):
        url = await _build_oauth_url("oauth_user")

    assert url is not None
    assert "mcp.swiggy.com/auth/authorize" in url
    assert "client_id=test_client_id" in url
    assert "code_challenge" in url


# -------------------------------------------------------------------
# Test 3: _do_sync with real orders stores them correctly
# -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_do_sync_stores_orders_with_user_id():
    """When Swiggy MCP returns orders, they are saved with correct user_id."""
    user_id = _create_connected_user("sync_test_user")

    mock_addresses = [{"id": "addr_123", "address": "Test Address"}]
    mock_orders = [
        {
            "order_id": "REAL-ORDER-001",
            "restaurant_name": "Real Restaurant",
            "order_total": 450.0,
            "order_status": "Delivered",
        },
        {
            "order_id": "REAL-ORDER-002",
            "restaurant_name": "Another Restaurant",
            "order_total": 300.0,
            "order_status": "Delivered",
        },
    ]

    with patch("src.telegram_bot.decrypt_token", return_value="fake_access_token"):
        with patch("src.swiggy_mcp_client.get_addresses", new_callable=AsyncMock, return_value=mock_addresses):
            with patch("src.swiggy_mcp_client.get_food_orders", new_callable=AsyncMock, return_value=mock_orders):
                result = await _do_sync("sync_test_user")

    assert "Swiggy data retrieved successfully" in result

    # Verify orders are in DB with correct user_id
    with get_session() as session:
        orders = session.exec(select(Order).where(Order.user_id == user_id)).all()
        assert len(orders) == 2
        order_ids = {o.order_id for o in orders}
        assert "REAL-ORDER-001" in order_ids
        assert "REAL-ORDER-002" in order_ids

        # Verify restaurant names are real, not dummy
        for o in orders:
            assert o.restaurant_name != "Test Restaurant"
            assert not o.restaurant_name.startswith("Restaurant ")


# -------------------------------------------------------------------
# Test 4: _do_sync with no addresses
# -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_do_sync_no_addresses():
    """When user has no saved addresses, sync explains."""
    _create_connected_user("no_addr_user")

    with patch("src.telegram_bot.decrypt_token", return_value="fake_token"):
        with patch("src.swiggy_mcp_client.get_addresses", new_callable=AsyncMock, return_value=[]):
            result = await _do_sync("no_addr_user")

    assert "No supported Swiggy data is currently available" in result


# -------------------------------------------------------------------
# Test 5: _do_sync with no orders
# -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_do_sync_no_orders():
    """When Swiggy returns empty orders, sync reports it cleanly."""
    _create_connected_user("no_orders_user")

    with patch("src.telegram_bot.decrypt_token", return_value="fake_token"):
        with patch("src.swiggy_mcp_client.get_addresses", new_callable=AsyncMock, return_value=[{"id": "addr_1"}]):
            with patch("src.swiggy_mcp_client.get_food_orders", new_callable=AsyncMock, return_value=[]):
                result = await _do_sync("no_orders_user")

    assert "No supported Swiggy data is currently available" in result


# -------------------------------------------------------------------
# Test X: >5 orders
# -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_do_sync_more_than_5_orders():
    """Verify that if Swiggy returns >5 orders, we save and display all of them."""
    user_id = _create_connected_user("large_order_user")

    # Generate 17 mock orders
    mock_orders = []
    for i in range(1, 18):
        mock_orders.append({
            "order_id": f"ORDER-{i}",
            "restaurant_name": f"Mock Restaurant {i}",
            "order_total": 100 + i
        })

    with patch("src.telegram_bot.decrypt_token", return_value="real_token"):
        with patch("src.swiggy_mcp_client.get_addresses", new_callable=AsyncMock, return_value=[{"id": "addr"}]):
            with patch("src.swiggy_mcp_client.get_food_orders", new_callable=AsyncMock, return_value=mock_orders):
                from src.telegram_bot import _do_sync
                await _do_sync("large_order_user")

    # Verify they were saved
    with get_session() as session:
        from src.models import Order
        from sqlmodel import select
        saved = session.exec(select(Order).where(Order.user_id == user_id)).all()
        assert len(saved) == 17

    # Verify get_orders displays them
    from src.mcp_server import get_orders
    result = get_orders(limit=50, user_id=user_id)
    assert "Mock Restaurant 17" in result
    assert "17." in result

# -------------------------------------------------------------------
# Test 6: User isolation - User A cannot see User B's orders
# -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_user_isolation_after_sync():
    """Orders synced by User A must not appear for User B."""
    user_a_id = _create_connected_user("user_a_iso")
    user_b_id = _create_connected_user("user_b_iso")

    mock_orders_a = [{"order_id": "A-ORDER-1", "restaurant_name": "A's Place", "order_total": 100}]
    mock_orders_b = [{"order_id": "B-ORDER-1", "restaurant_name": "B's Place", "order_total": 200}]

    # Sync User A
    with patch("src.telegram_bot.decrypt_token", return_value="token_a"):
        with patch("src.swiggy_mcp_client.get_addresses", new_callable=AsyncMock, return_value=[{"id": "addr_a"}]):
            with patch("src.swiggy_mcp_client.get_food_orders", new_callable=AsyncMock, return_value=mock_orders_a):
                await _do_sync("user_a_iso")

    # Sync User B
    with patch("src.telegram_bot.decrypt_token", return_value="token_b"):
        with patch("src.swiggy_mcp_client.get_addresses", new_callable=AsyncMock, return_value=[{"id": "addr_b"}]):
            with patch("src.swiggy_mcp_client.get_food_orders", new_callable=AsyncMock, return_value=mock_orders_b):
                await _do_sync("user_b_iso")

    # Verify isolation
    with get_session() as session:
        a_orders = session.exec(select(Order).where(Order.user_id == user_a_id)).all()
        b_orders = session.exec(select(Order).where(Order.user_id == user_b_id)).all()

        assert len(a_orders) == 1
        assert a_orders[0].order_id == "A-ORDER-1"
        assert a_orders[0].restaurant_name == "A's Place"

        assert len(b_orders) == 1
        assert b_orders[0].order_id == "B-ORDER-1"
        assert b_orders[0].restaurant_name == "B's Place"


# -------------------------------------------------------------------
# Test 7: No dummy data is ever returned
# -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_dummy_data_after_sync():
    """After sync, the DB must not contain any dummy/test data."""
    _create_connected_user("real_user")

    mock_orders = [{"order_id": "REAL-1", "restaurant_name": "Honest Burger", "order_total": 550}]

    with patch("src.telegram_bot.decrypt_token", return_value="real_token"):
        with patch("src.swiggy_mcp_client.get_addresses", new_callable=AsyncMock, return_value=[{"id": "addr"}]):
            with patch("src.swiggy_mcp_client.get_food_orders", new_callable=AsyncMock, return_value=mock_orders):
                await _do_sync("real_user")

    DUMMY_NAMES = {"Test Restaurant", "Test Kitchen", "Restaurant 0", "Restaurant 1",
                   "Burger King Test", "Pizza Palace Test"}

    with get_session() as session:
        all_orders = session.exec(select(Order)).all()
        for order in all_orders:
            assert order.restaurant_name not in DUMMY_NAMES, f"Dummy data found: {order.restaurant_name}"
            assert order.user_id is not None, "Order must have a user_id"

@pytest.mark.asyncio
async def test_do_sync_expired_token():
    """When the Swiggy token is expired, sync asks to reconnect."""
    with get_session() as session:
        from src.models import User, SwiggyConnection
        user = User(telegram_id="expired_user")
        session.add(user)
        session.commit()
        session.refresh(user)

        from datetime import datetime, timezone, timedelta
        conn = SwiggyConnection(
            user_id=user.id,
            status="CONNECTED",
            access_token="fake_encrypted",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1)
        )
        session.add(conn)
        session.commit()

    result = await _do_sync("expired_user")
    assert "Your Swiggy connection has expired" in result

@pytest.mark.asyncio
async def test_disconnect_command():
    """Test that /disconnect safely removes the SwiggyConnection without deleting the user."""
    from src.telegram_bot import disconnect_command
    import os
    from unittest.mock import AsyncMock, MagicMock

    # Setup environment
    os.environ["ENVIRONMENT"] = "development"

    # Setup connected user
    _create_connected_user("disconnect_user")

    # Mock Update and Context
    update = MagicMock()
    update.effective_user.id = "disconnect_user"
    update.message = AsyncMock()
    context = MagicMock()

    # Call disconnect
    await disconnect_command(update, context)

    # Verify response
    update.message.reply_text.assert_called_once_with("Swiggy disconnected. Use /start to connect again.")

    # Verify database state
    with get_session() as session:
        user = session.exec(select(User).where(User.telegram_id == "disconnect_user")).first()
        assert user is not None, "User should not be deleted"
        
        conn = session.exec(select(SwiggyConnection).where(SwiggyConnection.user_id == user.id)).first()
        assert conn is None, "SwiggyConnection should be deleted"

    # Clean up environment
    os.environ.pop("ENVIRONMENT", None)

@pytest.mark.asyncio
async def test_disconnect_command_production():
    """Test that /disconnect does nothing in production."""
    from src.telegram_bot import disconnect_command
    import os
    from unittest.mock import AsyncMock, MagicMock

    # Setup environment
    os.environ["ENVIRONMENT"] = "production"

    # Setup connected user
    _create_connected_user("disconnect_user_prod")

    # Mock Update and Context
    update = MagicMock()
    update.effective_user.id = "disconnect_user_prod"
    update.message = AsyncMock()
    context = MagicMock()

    # Call disconnect
    await disconnect_command(update, context)

    # Verify no response
    update.message.reply_text.assert_not_called()

    # Verify database state
    with get_session() as session:
        user = session.exec(select(User).where(User.telegram_id == "disconnect_user_prod")).first()
        conn = session.exec(select(SwiggyConnection).where(SwiggyConnection.user_id == user.id)).first()
        assert conn is not None, "SwiggyConnection should NOT be deleted in production"

    # Clean up environment
    os.environ.pop("ENVIRONMENT", None)
