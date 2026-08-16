"""
Swiggy API client — fetches order history via the private ``/dapi/order/all``
endpoint.

Design notes
~~~~~~~~~~~~
* **httpx** is used instead of *requests* for modern async support.
* The fetcher is *stateless* with respect to cookies — they're passed in at
  call-time and never cached.
* Pagination mirrors the original JS implementation: the oldest ``order_id``
  from each page is sent as a cursor for the next page.
* Exponential back-off with jitter is applied on failures.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class SwiggyAPIError(Exception):
    """Raised when Swiggy API returns a non-200 status code or error response."""
    
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"Swiggy API error [{status_code}]: {message}")


class AuthenticationError(Exception):
    """Raised when session cookies are invalid or expired."""
    
    def __init__(self, message: str = "Invalid or expired session cookies"):
        self.message = message
        super().__init__(message)

_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/139.0.0.0 Safari/537.36"
)
_REQUEST_DELAY = 0.5          # seconds between pages
_MAX_RETRIES = 3
_MAX_CONSECUTIVE_EMPTY = 10   # stop after this many blank pages


# ---------------------------------------------------------------------------
# Configuration from environment variables (requirement 13.4, 13.5)
# ---------------------------------------------------------------------------

def _get_base_url() -> str:
    """Get Swiggy API base URL from SWIGGY_API_URL env var."""
    return os.getenv("SWIGGY_API_URL", "https://www.swiggy.com/dapi/order/all")


def _get_timeout() -> float:
    """Get request timeout from REQUEST_TIMEOUT env var, default 30 seconds."""
    try:
        return float(os.getenv("REQUEST_TIMEOUT", "30"))
    except (ValueError, TypeError):
        return 30.0


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def _build_headers(cookies: str) -> dict[str, str]:
    return {
        "User-Agent": _DEFAULT_USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Cookie": cookies,
    }


async def _make_request(
    client: httpx.AsyncClient,
    cookies: str,
    order_id: str | None = None,
    *,
    attempt: int = 0,
) -> dict[str, Any] | None:
    """
    Single API call with retry & exponential back-off.
    
    Implements:
    - Retry mechanism (3 attempts) with exponential backoff (requirement 12.1)
    - Raises SwiggyAPIError for non-200 status codes (requirement 12.1)
    - Raises AuthenticationError for invalid/expired cookies (requirement 12.2)
    - Request timeout from REQUEST_TIMEOUT env var (requirement 13.5)
    - Error logs never include cookie values (requirement 12.6)
    """
    params: dict[str, str] = {}
    if order_id:
        params["order_id"] = order_id

    timeout = _get_timeout()

    try:
        resp = await client.get(
            _get_base_url(),
            params=params,
            headers=_build_headers(cookies),
            timeout=timeout,
        )
        
        # Check HTTP status code (requirement 12.1)
        if resp.status_code == 401 or resp.status_code == 403:
            # Authentication error (requirement 12.2)
            logger.error("Authentication failed with status %d", resp.status_code)
            raise AuthenticationError("Invalid or expired session cookies")
        
        if resp.status_code != 200:
            # Non-200 status code (requirement 12.1)
            error_message = f"HTTP {resp.status_code}"
            try:
                error_data = resp.json()
                if "statusMessage" in error_data:
                    error_message = error_data["statusMessage"]
            except Exception:
                pass
            logger.error("API request failed with status %d: %s", resp.status_code, error_message)
            raise SwiggyAPIError(resp.status_code, error_message)
        
        # Parse JSON response
        data = resp.json()
        
        # Check API-level status code
        api_status = data.get("statusCode")
        if api_status == 0:
            return data
        
        # Check for authentication errors in API response (requirement 12.2)
        if api_status in (401, 403) or "auth" in str(data.get("statusMessage", "")).lower():
            logger.error("API authentication error: %s", data.get("statusMessage"))
            raise AuthenticationError("Invalid or expired session cookies")
        
        # Other API errors (requirement 12.1)
        error_msg = data.get("statusMessage", "Unknown error")
        logger.warning("API status %s: %s", api_status, error_msg)
        raise SwiggyAPIError(api_status or 500, error_msg)
        
    except AuthenticationError:
        # Don't retry authentication errors, propagate immediately
        raise
    except SwiggyAPIError:
        # Don't retry API errors, propagate immediately
        raise
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        # Network errors, timeouts, JSON parsing errors - retry with exponential backoff
        if attempt < _MAX_RETRIES:
            # Exponential backoff: 0.5s, 1.0s, 2.0s (requirement 12.3)
            wait = _REQUEST_DELAY * (2 ** attempt)
            # Log error without cookie values (requirement 12.6)
            logger.warning(
                "Request failed (%s: %s), retry %d/%d in %.1fs",
                type(exc).__name__,
                str(exc),
                attempt + 1,
                _MAX_RETRIES,
                wait
            )
            await asyncio.sleep(wait)
            return await _make_request(client, cookies, order_id, attempt=attempt + 1)
        
        # Max retries exceeded, log and raise
        logger.error("Request failed after %d retries: %s: %s", _MAX_RETRIES, type(exc).__name__, str(exc))
        raise SwiggyAPIError(500, f"Request failed after {_MAX_RETRIES} retries: {str(exc)}")


def _extract_orders(response: dict[str, Any]) -> list[dict[str, Any]]:
    """Pull the ``orders`` list out of a raw API response."""
    return (response.get("data") or {}).get("orders") or []


def _oldest_order_id(orders: list[dict[str, Any]]) -> str | None:
    """Return the smallest order_id from a batch (used as pagination cursor)."""
    if not orders:
        return None
    
    # Safely convert order_id to int for comparison, fallback to 0 if invalid
    def _safe_int(oid: Any) -> int:
        try:
            return int(oid)
        except (ValueError, TypeError):
            return 0

    oldest = min(orders, key=lambda o: _safe_int(o.get("order_id", 0)))
    oid = oldest.get("order_id")
    return str(oid) if oid else None


# ---------------------------------------------------------------------------
# Main entry-point
# ---------------------------------------------------------------------------

async def sync_orders(
    cookies: str,
    *,
    max_orders: int = 1000,
    max_pages: int = 50
) -> list[dict[str, Any]]:
    """
    Fetch orders from Swiggy API with support for max_orders limit.

    This is the primary function for syncing order data, implementing:
    - Pagination using order_id cursor
    - 0.5 second delay between requests
    - Stop when max_orders limit is reached
    - Parse order JSON response extracting all required fields
    - Retry mechanism (3 attempts) with exponential backoff
    - Proper error handling with SwiggyAPIError and AuthenticationError

    Parameters
    ----------
    cookies : str
        Raw cookie header value (runtime-only, never persisted).
    max_orders : int
        Maximum number of orders to fetch (default: 1000).
    max_pages : int
        Safety cap on the number of API pages to request (default: 50).

    Returns
    -------
    list[dict]
        Raw order dicts with all required fields:
        - order_id, order_time, order_total
        - restaurant_name, restaurant_cuisine, restaurant_locality
        - Plus all other fields from the Swiggy API response

    Raises
    ------
    SwiggyAPIError
        When API returns non-200 status or error response
    AuthenticationError
        When session cookies are invalid or expired

    Requirements
    ------------
    Implements: 2.1, 3.1, 3.2, 3.5, 3.6, 3.7, 12.1, 12.2, 12.6, 13.4, 13.5, 14.5
    """
    all_orders: list[dict[str, Any]] = []
    last_order_id: str | None = None
    consecutive_empty = 0
    seen_order_ids: set[str] = set()

    async with httpx.AsyncClient() as client:
        for page in range(1, max_pages + 1):
            logger.info("[page %d] fetching (cursor=%s)…", page, last_order_id)

            try:
                response = await _make_request(client, cookies, last_order_id)
            except (SwiggyAPIError, AuthenticationError):
                # Propagate API and authentication errors immediately
                raise
            
            if response is None:
                consecutive_empty += 1
                if consecutive_empty >= _MAX_CONSECUTIVE_EMPTY:
                    logger.info("Stopping after %d consecutive empty responses", consecutive_empty)
                    break
                continue

            orders = _extract_orders(response)
            if not orders:
                consecutive_empty += 1
                if consecutive_empty >= _MAX_CONSECUTIVE_EMPTY:
                    logger.info("Stopping after %d consecutive empty responses", consecutive_empty)
                    break
                continue

            consecutive_empty = 0
            
            # Filter out orders we've already seen (deduplication)
            new_orders = [o for o in orders if str(o.get("order_id", "")) not in seen_order_ids]
            
            # If all orders on this page were already seen, stop pagination
            if not new_orders:
                logger.info("No new orders on page %d, stopping pagination", page)
                break
            
            # Add orders up to max_orders limit
            remaining = max_orders - len(all_orders)
            if remaining <= 0:
                logger.info("Reached max_orders limit of %d", max_orders)
                break
            
            orders_to_add = new_orders[:remaining]
            all_orders.extend(orders_to_add)
            
            # Track seen order IDs
            for order in orders_to_add:
                oid = str(order.get("order_id", ""))
                if oid:
                    seen_order_ids.add(oid)
            
            logger.info("[page %d] got %d orders (total %d)", page, len(orders_to_add), len(all_orders))

            # Check if we've reached the limit
            if len(all_orders) >= max_orders:
                logger.info("Reached max_orders limit of %d", max_orders)
                break

            # Get next cursor for pagination
            new_order_id = _oldest_order_id(new_orders)
            if not new_order_id:
                logger.info("No more orders available (no order_id found)")
                break
            
            # Stop if cursor hasn't changed (prevents infinite loop with duplicate orders)
            if new_order_id == last_order_id:
                logger.info("Pagination cursor unchanged, no more unique orders available")
                break
            
            last_order_id = new_order_id

            # Add 0.5 second delay between pagination requests (requirement 3.3)
            if page < max_pages:
                await asyncio.sleep(_REQUEST_DELAY)

    logger.info("Fetch complete – %d orders from %d pages", len(all_orders), page)
    return all_orders


async def fetch_all_orders(cookies: str, *, max_pages: int = 50) -> list[dict[str, Any]]:
    """
    Fetch all available orders from Swiggy, paginating until exhausted.

    This is a legacy function maintained for backward compatibility.
    New code should use sync_orders() instead.

    Parameters
    ----------
    cookies : str
        Raw cookie header value (runtime-only, never persisted).
    max_pages : int
        Safety cap on the number of API pages to request.

    Returns
    -------
    list[dict]
        Raw order dicts straight from the Swiggy API.
        
    Raises
    ------
    SwiggyAPIError
        When API returns non-200 status or error response
    AuthenticationError
        When session cookies are invalid or expired
    """
    # Delegate to sync_orders with a high max_orders limit
    return await sync_orders(cookies, max_orders=100000, max_pages=max_pages)


async def validate_session(cookies: str) -> bool:
    """
    Quick probe to check whether the cookies are still valid.
    
    Returns True if cookies are valid, False otherwise.
    Does not raise exceptions for invalid cookies (returns False instead).
    """
    async with httpx.AsyncClient() as client:
        try:
            result = await _make_request(client, cookies)
            return result is not None
        except (SwiggyAPIError, AuthenticationError):
            # Invalid cookies or API error
            return False
