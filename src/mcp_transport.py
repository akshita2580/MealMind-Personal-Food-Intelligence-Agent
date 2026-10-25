import asyncio
import logging
import json
from typing import Any
import httpx
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Number of times to retry on transient network errors (e.g. DNS blips on Windows)
_MCP_MAX_RETRIES = 3
# Base delay in seconds; doubles each retry (0.5 -> 1 -> 2)
_MCP_RETRY_BASE_DELAY = 0.5


async def mcp_call(access_token: str, base_url: str, tool_name: str, arguments: dict[str, Any]) -> dict:
    """
    Make a JSON-RPC 2.0 tools/call request to an MCP server.

    Returns the parsed JSON response body.
    Raises RuntimeError on HTTP or protocol errors.

    Transient network errors (DNS failures, connection resets) are retried up to
    _MCP_MAX_RETRIES times with exponential backoff before raising.
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

    parsed_url = urlparse(base_url)
    logger.info(
        "MCP Request Diagnostics\nMCP hostname: %s\nMCP path: %s\nHTTP method: POST\nAuthorization header present: %s\ntoken_length: %s\nMCP tool: %s",
        parsed_url.hostname,
        parsed_url.path,
        str(bool(access_token)).lower(),
        len(access_token) if access_token else 0,
        tool_name,
    )

    last_exc: Exception | None = None
    for attempt in range(1, _MCP_MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient() as client:
                req_timeout = httpx.Timeout(10.0, read=15.0)

                response = await asyncio.wait_for(
                    client.post(base_url, json=payload, headers=headers, timeout=req_timeout),
                    timeout=20.0,
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

                data = _decode_mcp_response(response, tool_name)

                if not isinstance(data, dict):
                    raise RuntimeError(f"Swiggy MCP {tool_name} error: Invalid JSON-RPC response.")

                if "error" in data:
                    msg = data["error"].get("message", str(data["error"]))
                    raise RuntimeError(f"Swiggy MCP {tool_name} error: {msg}")

                result = data.get("result")
                if isinstance(result, dict) and result.get("isError"):
                    content = result.get("content", [])
                    details = " ".join(
                        item.get("text", "") for item in content
                        if isinstance(item, dict) and item.get("type") == "text"
                    ).strip()
                    # For cart/order tools, callers need to inspect the error text
                    # and try alternative schemas, so return it rather than raising.
                    # Inject a normalised "errorMessage" key the caller can check.
                    logger.warning(
                        "Swiggy MCP %s isError=true: %s", tool_name, details or "Tool execution failed."
                    )
                    data["_tool_error"] = details or "Tool execution failed."
                    return data

                return data

        except asyncio.TimeoutError as exc:
            # Timeouts are already slow -- don't retry, surface immediately
            logger.error("Swiggy MCP %s overall timeout: %s", tool_name, exc)
            raise RuntimeError(f"Swiggy MCP {tool_name} error: [Timeout] Request exceeded maximum time limit.") from exc

        except httpx.TimeoutException as exc:
            logger.error("Swiggy MCP %s network timeout: %s", tool_name, exc)
            raise RuntimeError(f"Swiggy MCP {tool_name} error: Network timeout.") from exc

        except httpx.HTTPStatusError as exc:
            response_body = exc.response.text[:1000]
            logger.error(
                "Swiggy MCP %s HTTP error: status=%s body=%r",
                tool_name,
                exc.response.status_code,
                response_body,
            )
            raise RuntimeError(
                f"Swiggy MCP {tool_name} error: HTTP {exc.response.status_code}: {response_body or 'empty response body'}"
            ) from exc

        except RuntimeError:
            # Auth/permission/protocol errors -- don't retry
            raise

        except httpx.RequestError as exc:
            # Covers DNS failures (getaddrinfo), connection errors, etc.
            delay = _MCP_RETRY_BASE_DELAY * (2 ** (attempt - 1))
            if attempt < _MCP_MAX_RETRIES:
                logger.warning(
                    "Swiggy MCP %s transient network error (attempt %d/%d), retrying in %.1fs: %s",
                    tool_name,
                    attempt,
                    _MCP_MAX_RETRIES,
                    delay,
                    exc,
                )
                await asyncio.sleep(delay)
                last_exc = exc
            else:
                logger.error("Swiggy MCP %s network error after %d attempts: %s", tool_name, _MCP_MAX_RETRIES, exc)
                raise RuntimeError(f"Swiggy MCP {tool_name} error: Network error {exc}") from exc

    # Should not reach here, but satisfy the type checker
    raise RuntimeError(f"Swiggy MCP {tool_name} error: Network error {last_exc}")


def _decode_mcp_response(response: httpx.Response, tool_name: str) -> dict[str, Any]:
    """Decode both JSON MCP responses and legacy/server-sent event responses."""
    content_type = response.headers.get("content-type", "").lower()
    if "text/event-stream" not in content_type:
        try:
            return response.json()
        except ValueError as exc:
            raise RuntimeError(f"Swiggy MCP {tool_name} error: Server returned invalid JSON.") from exc

    # MCP servers may return one or more SSE events. The JSON-RPC result is
    # carried in each event's data field; ignore comments and empty events.
    events: list[dict[str, Any]] = []
    data_lines: list[str] = []
    for line in response.text.splitlines() + [""]:
        if not line.strip():
            if data_lines:
                try:
                    event = json.loads("\n".join(data_lines))
                    if isinstance(event, dict):
                        events.append(event)
                except json.JSONDecodeError:
                    logger.warning("Swiggy MCP %s returned a malformed SSE event", tool_name)
                data_lines = []
            continue
        if line.startswith(":"):
            continue
        field, separator, value = line.partition(":")
        if separator and field == "data":
            data_lines.append(value[1:] if value.startswith(" ") else value)

    if not events:
        raise RuntimeError(f"Swiggy MCP {tool_name} error: Event stream contained no JSON-RPC response.")
    return next((event for event in events if "result" in event or "error" in event), events[-1])

def extract_mcp_result(response: dict, tool_name: str) -> Any:
    """Extract the result from a JSON-RPC response, handling MCP content format."""
    result = response.get("result", {})

    # Propagate the normalised tool error injected by mcp_call for isError responses.
    tool_error = response.get("_tool_error")

    if "structuredContent" in result:
        extracted = result["structuredContent"]
    elif "data" in result:
        extracted = result["data"]
    else:
        content = result.get("content", [])
        extracted = None
        if content and isinstance(content, list):
            for item in content:
                if item.get("type") == "text":
                    import json
                    try:
                        parsed = json.loads(item["text"])
                        if isinstance(parsed, dict) and "data" in parsed:
                            extracted = parsed["data"]
                        else:
                            extracted = parsed
                    except (json.JSONDecodeError, KeyError):
                        extracted = item.get("text", "")
                    break
        if extracted is None:
            extracted = result

    # Re-attach the tool error so callers (e.g. _update_food_cart_and_confirm)
    # can detect isError=true without the exception being raised.
    if tool_error and isinstance(extracted, dict):
        extracted = {**extracted, "_tool_error": tool_error}
    elif tool_error:
        # Wrap non-dict extracted values in a minimal error envelope.
        extracted = {"_tool_error": tool_error, "raw": extracted}

    return extracted
