import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from src.swiggy_mcp_client import _mcp_call, get_addresses, get_restaurant_menu
from src.swiggy_instamart_mcp import get_cart
import httpx

@pytest.mark.asyncio
async def test_mcp_headers():
    mock_post = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"result": {"content": [{"type": "text", "text": "{\"data\": {\"addresses\": []}}"}]}}
    mock_post.return_value = mock_resp

    with patch("httpx.AsyncClient.post", new=mock_post):
        await get_addresses("fake_token")
        
        # Verify post called with correct headers
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        headers = kwargs.get("headers", {})
        
        assert headers.get("Authorization") == "Bearer fake_token"
        assert headers.get("Content-Type") == "application/json"
        assert "application/json" in headers.get("Accept", "")
        assert "text/event-stream" in headers.get("Accept", "")

@pytest.mark.asyncio
async def test_mcp_406_handling():
    mock_post = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 406
    mock_resp.text = "Not Acceptable"
    mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError("406 Error", request=MagicMock(), response=mock_resp)
    mock_post.return_value = mock_resp

    with patch("httpx.AsyncClient.post", new=mock_post):
        with pytest.raises(RuntimeError) as exc:
            await get_addresses("fake_token")
            
        assert "Protocol/request format issue" in str(exc.value)

@pytest.mark.asyncio
async def test_get_restaurant_menu_uses_documented_arguments():
    response = {"result": {"structuredContent": {"categories": []}}}

    with patch("src.swiggy_mcp_client._mcp_call", new=AsyncMock(return_value=response)) as call:
        menu = await get_restaurant_menu("token", "address-123", "restaurant-456")

    assert menu == {"categories": []}
    call.assert_awaited_once_with(
        "token",
        "get_restaurant_menu",
        {"addressId": "address-123", "restaurantId": "restaurant-456"},
    )

@pytest.mark.asyncio
async def test_get_restaurant_menu_rejects_missing_ids_before_calling_upstream():
    with patch("src.swiggy_mcp_client._mcp_call", new=AsyncMock()) as call:
        with pytest.raises(ValueError, match="address_id and restaurant_id are required"):
            await get_restaurant_menu("token", "", "restaurant-456")

    call.assert_not_awaited()

@pytest.mark.asyncio
async def test_instamart_get_cart_uses_no_arguments():
    response = {"result": {"structuredContent": {"success": True, "items": []}}}

    with patch("src.swiggy_instamart_mcp._mcp_call", new=AsyncMock(return_value=response)) as call:
        result = await get_cart("token", "legacy-address-argument")

    assert result == {"success": True, "items": []}
    call.assert_awaited_once_with("token", "get_cart", {})

def test_mcp_failure_message_detects_unsuccessful_result():
    from src.api_web import _mcp_failure_message

    assert _mcp_failure_message({
        "success": False,
        "error": {"message": "This address is not serviceable"},
    }) == "This address is not serviceable"
    assert _mcp_failure_message({"success": True}) is None
