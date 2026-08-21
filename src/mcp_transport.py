import logging
from typing import Any
import httpx
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

async def mcp_call(access_token: str, base_url: str, tool_name: str, arguments: dict[str, Any]) -> dict:
    """
    Make a JSON-RPC 2.0 tools/call request to an MCP server.

    Returns the parsed JSON response body.
    Raises RuntimeError on HTTP or protocol errors.
    """
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments,
        },
    }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }

    async with httpx.AsyncClient() as client:
        parsed_url = urlparse(base_url)
        logger.info(
            "MCP Request Diagnostics\nMCP hostname: %s\nMCP path: %s\nHTTP method: POST\nAuthorization header present: %s\ntoken_length: %s\nMCP tool: %s",
            parsed_url.hostname,
            parsed_url.path,
            str(bool(access_token)).lower(),
            len(access_token) if access_token else 0,
            tool_name
        )

        try:
            import asyncio
            req_timeout = httpx.Timeout(10.0, read=15.0)
            
            response = await asyncio.wait_for(
                client.post(base_url, json=payload, headers=headers, timeout=req_timeout),
                timeout=20.0
            )
            
            if response.status_code == 401:
                raise RuntimeError(f"Swiggy MCP {tool_name} error: Authentication expired. Please reconnect.")
            elif response.status_code == 403:
                raise RuntimeError(f"Swiggy MCP {tool_name} error: Permission/scope issue.")
            elif response.status_code == 406:
                raise RuntimeError(f"Swiggy MCP {tool_name} error: Protocol/request format issue.")
            elif response.status_code >= 500:
                raise RuntimeError(f"Swiggy MCP {tool_name} error: Temporary Swiggy failure (HTTP {response.status_code}).")
                
            response.raise_for_status()
            
            data = response.json()
            
            if "error" in data:
                msg = data["error"].get("message", str(data["error"]))
                raise RuntimeError(f"Swiggy MCP {tool_name} error: {msg}")
                
            return data
            
        except asyncio.TimeoutError as exc:
            logger.error("Swiggy MCP %s overall timeout: %s", tool_name, exc)
            raise RuntimeError(f"Swiggy MCP {tool_name} error: [Timeout] Request exceeded maximum time limit.") from exc
        except httpx.TimeoutException as exc:
            logger.error("Swiggy MCP %s network timeout: %s", tool_name, exc)
            raise RuntimeError(f"Swiggy MCP {tool_name} error: Network timeout.") from exc
        except httpx.HTTPStatusError as exc:
            logger.error("Swiggy MCP %s HTTP error: %s", tool_name, exc)
            raise RuntimeError(f"Swiggy MCP {tool_name} error: HTTP {exc.response.status_code}") from exc
        except httpx.RequestError as exc:
            logger.error("Swiggy MCP %s network error: %s", tool_name, exc)
            raise RuntimeError(f"Swiggy MCP {tool_name} error: Network error {exc}") from exc

def extract_mcp_result(response: dict, tool_name: str) -> Any:
    """Extract the result from a JSON-RPC response, handling MCP content format."""
    result = response.get("result", {})

    if "structuredContent" in result:
        return result["structuredContent"]
    if "data" in result:
        return result["data"]

    content = result.get("content", [])
    if content and isinstance(content, list):
        for item in content:
            if item.get("type") == "text":
                import json
                try:
                    parsed = json.loads(item["text"])
                    if isinstance(parsed, dict) and "data" in parsed:
                        return parsed["data"]
                    return parsed
                except (json.JSONDecodeError, KeyError):
                    return item.get("text", "")
    return result
