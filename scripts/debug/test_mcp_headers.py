import asyncio
import os
import httpx
from src.database import get_session
from src.models import SwiggyConnection

async def main():
    # Get a real access token from the DB
    with get_session() as session:
        conn = session.query(SwiggyConnection).filter(SwiggyConnection.status == "CONNECTED").first()
        if not conn:
            print("No connected user found!")
            return
        
        from src.security import decrypt_token
        token = decrypt_token(conn.access_token)
    
    url = "https://mcp.swiggy.com/food"
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "get_addresses",
            "arguments": {},
        },
    }
    
    # Try different Accept headers
    async with httpx.AsyncClient() as client:
        print("Testing with standard headers...")
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        resp = await client.post(url, json=payload, headers=headers)
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.text[:200]}")
        
        if resp.status_code == 406:
            print("\nTesting with Accept: */* ...")
            headers["Accept"] = "*/*"
            resp = await client.post(url, json=payload, headers=headers)
            print(f"Status: {resp.status_code}")
            print(f"Response: {resp.text[:200]}")

            print("\nTesting with Accept: application/jsonrpc+json ...")
            headers["Accept"] = "application/jsonrpc+json"
            resp = await client.post(url, json=payload, headers=headers)
            print(f"Status: {resp.status_code}")
            print(f"Response: {resp.text[:200]}")
            
            print("\nTesting without Accept header ...")
            del headers["Accept"]
            resp = await client.post(url, json=payload, headers=headers)
            print(f"Status: {resp.status_code}")
            print(f"Response: {resp.text[:200]}")

if __name__ == "__main__":
    asyncio.run(main())
