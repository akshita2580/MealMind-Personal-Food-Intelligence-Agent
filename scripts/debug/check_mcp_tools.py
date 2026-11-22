import asyncio
import httpx
from src.database import get_session
from src.models import SwiggyConnection

async def main():
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
        "method": "tools/list",
        "params": {}
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"
    }
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, headers=headers)
        import json
        print(json.dumps(resp.json(), indent=2))

if __name__ == "__main__":
    asyncio.run(main())
