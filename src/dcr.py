"""
Dynamic Client Registration (DCR) for Swiggy OAuth.
"""
import os
import json
import logging
from datetime import datetime, timezone
import httpx

logger = logging.getLogger(__name__)

CLIENT_FILE = ".swiggy_oauth_client.json"

async def get_or_register_client() -> str:
    """
    Get the registered Swiggy OAuth client ID.
    If the local registration file is missing or invalid, or if the redirect URI
    has changed, it performs a new Dynamic Client Registration with Swiggy.
    """
    redirect_uri = os.getenv("SWIGGY_REDIRECT_URI", "http://127.0.0.1:8000/api/auth/swiggy/callback")
    
    # 1. Check existing registration
    if os.path.exists(CLIENT_FILE):
        try:
            with open(CLIENT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            client_id = data.get("client_id")
            stored_redirect_uri = data.get("redirect_uri")
            
            if client_id and stored_redirect_uri == redirect_uri:
                return client_id
            
            if not client_id:
                logger.info("DCR: Missing client_id in stored configuration. Re-registering.")
            elif stored_redirect_uri != redirect_uri:
                logger.info("DCR: Redirect URI mismatch. Re-registering.")
                
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("DCR: Failed to read %s. Re-registering. Error: %s", CLIENT_FILE, e)
            
    # 2. Perform Dynamic Client Registration
    registration_data = {
        "client_name": "MealMind",
        "redirect_uris": [redirect_uri],
        "grant_types": ["authorization_code"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "scope": "mcp:tools"
    }
    
    register_url = "https://mcp.swiggy.com/auth/register"
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(register_url, json=registration_data, timeout=15.0)
            resp.raise_for_status()
            
            resp_data = resp.json()
            client_id = resp_data.get("client_id")
            
            if not client_id:
                raise RuntimeError("Swiggy DCR responded successfully but missing client_id")
                
            # 3. Store the new client registration
            client_metadata = {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            with open(CLIENT_FILE, "w", encoding="utf-8") as f:
                json.dump(client_metadata, f, indent=2)
                
            logger.info("DCR: Successfully registered new OAuth client with Swiggy.")
            return client_id
            
        except httpx.HTTPStatusError as e:
            logger.error("DCR failed with HTTP %s: %s", e.response.status_code, e.response.text)
            raise RuntimeError(f"DCR registration failed with HTTP {e.response.status_code}") from e
        except httpx.RequestError as e:
            logger.error("DCR network error: %s", str(e))
            raise RuntimeError(f"DCR registration failed due to network error: {e}") from e
        except json.JSONDecodeError as e:
            logger.error("DCR failed to parse JSON response: %s", str(e))
            raise RuntimeError(f"DCR registration failed to parse JSON: {e}") from e
