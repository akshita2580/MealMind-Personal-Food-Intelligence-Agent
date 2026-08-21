import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from src.swiggy_mcp_client import _mcp_call, get_addresses
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
