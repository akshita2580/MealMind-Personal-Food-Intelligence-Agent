import pytest
from unittest.mock import patch, AsyncMock
from src.telegram_bot import _do_sync
from src.models import User, SwiggyConnection
from src.database import get_session

@pytest.fixture(autouse=True)
def clean_db():
    from sqlmodel import delete
    from src.models import OrderItem, OrderCuisine, Order, OAuthState
    with get_session() as session:
        session.exec(delete(OrderItem))
        session.exec(delete(OrderCuisine))
        session.exec(delete(Order))
        session.exec(delete(SwiggyConnection))
        session.exec(delete(OAuthState))
        session.exec(delete(User))
        session.commit()
    yield

def _create_connected_user(telegram_id="test_error_user"):
    with get_session() as session:
        user = User(telegram_id=telegram_id)
        session.add(user)
        session.commit()
        session.refresh(user)

        conn = SwiggyConnection(
            user_id=user.id,
            status="CONNECTED",
            access_token="fake_encrypted",
        )
        session.add(conn)
        session.commit()
        return user.id

@pytest.mark.asyncio
async def test_telegram_handles_mcp_406_safely():
    _create_connected_user("error_user")
    with patch("src.telegram_bot.get_user_access_token", return_value="fake_token"):
        with patch("src.swiggy_mcp_client.get_addresses", new_callable=AsyncMock, return_value=[{"id": "addr_1"}]):
            with patch("src.swiggy_mcp_client.get_food_orders", new_callable=AsyncMock) as mock_get_orders:
                mock_get_orders.side_effect = RuntimeError("Swiggy MCP get_food_orders returned HTTP 406")
                result = await _do_sync("error_user")
                assert "Swiggy service unreachable" in result

@pytest.mark.asyncio
async def test_telegram_handles_network_error():
    _create_connected_user("net_user")
    with patch("src.telegram_bot.get_user_access_token", return_value="fake_token"):
        with patch("src.swiggy_mcp_client.get_addresses", new_callable=AsyncMock, return_value=[{"id": "addr_1"}]):
            with patch("src.swiggy_mcp_client.get_food_orders", new_callable=AsyncMock) as mock_get_orders:
                mock_get_orders.side_effect = RuntimeError("Swiggy MCP get_food_orders network error: [Errno 11002] getaddrinfo failed")
                result = await _do_sync("net_user")
                assert "Swiggy service unreachable" in result

@pytest.mark.asyncio
async def test_telegram_handles_auth_error():
    _create_connected_user("auth_user")
    with patch("src.telegram_bot.get_user_access_token", return_value="fake_token"):
        with patch("src.swiggy_mcp_client.get_addresses", new_callable=AsyncMock, return_value=[{"id": "addr_1"}]):
            with patch("src.swiggy_mcp_client.get_food_orders", new_callable=AsyncMock) as mock_get_orders:
                mock_get_orders.side_effect = RuntimeError("Swiggy MCP get_food_orders returned HTTP 401")
                result = await _do_sync("auth_user")
                assert "rejected by Swiggy (HTTP 401)" in result

@pytest.mark.asyncio
async def test_telegram_handles_timeout():
    _create_connected_user("timeout_user")
    with patch("src.telegram_bot.get_user_access_token", return_value="fake_token"):
        with patch("src.swiggy_mcp_client.get_addresses", new_callable=AsyncMock, return_value=[{"id": "addr_1"}]):
            with patch("src.swiggy_mcp_client.get_food_orders", new_callable=AsyncMock) as mock_get_orders:
                mock_get_orders.side_effect = RuntimeError("Swiggy MCP get_food_orders network error: [Timeout] Request exceeded maximum time limit")
                result = await _do_sync("timeout_user")
                assert "Swiggy service unreachable" in result
