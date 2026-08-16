import asyncio
import os
from src.telegram_bot import generate_oauth_state, generate_pkce_verifier, generate_pkce_challenge
from src.dcr import get_or_register_client
import urllib.parse

async def main():
    state = generate_oauth_state()
    verifier = generate_pkce_verifier()
    challenge = generate_pkce_challenge(verifier)
    client_id = await get_or_register_client()
    
    redirect_uri = os.getenv("SWIGGY_REDIRECT_URI", "http://localhost:8000/api/auth/swiggy/callback")
    auth_base_url = "https://mcp.swiggy.com/auth/authorize"
    
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "scope": "mcp:tools"
    }
    
    auth_url = f"{auth_base_url}?{urllib.parse.urlencode(params)}"
    print("Redirect URI:", redirect_uri)
    print("Auth URL:", auth_url)

if __name__ == "__main__":
    asyncio.run(main())
