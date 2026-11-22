#!/usr/bin/env python3
"""Test Instamart API response structure"""
import asyncio
import json
from src.swiggy_instamart_mcp import search_products
from src.database import get_session
from src.models import SwiggyConnection
from sqlmodel import select
from src.security import decrypt_token

async def main():
    with get_session() as db:
        conn = db.exec(select(SwiggyConnection).where(SwiggyConnection.status == 'CONNECTED')).first()
        
        if not conn:
            print("No active Swiggy connection found")
            return
        
        token = decrypt_token(conn.access_token)
    
    # Test with milk search
    print("Testing Instamart search for 'milk'...")
    result = await search_products(token, 'd5fifs9smnnl38pg26j0__ARqElARoVogS5QFY-hPnKc', 'milk', 0)
    
    print("\n" + "="*80)
    print("RESULT TYPE:", type(result))
    print("="*80)
    
    print("\nFULL RESULT:")
    print(json.dumps(result, indent=2, default=str)[:2000])
    
    print("\n" + "="*80)
    print("ANALYSIS:")
    print("="*80)
    
    if isinstance(result, dict):
        print(f"Keys: {list(result.keys())}")
        
        # Check for products in different keys
        for key in ['products', 'items', 'data', 'results']:
            if key in result:
                items = result[key]
                print(f"\nFound items in '{key}' key")
                print(f"Type: {type(items)}")
                if isinstance(items, list) and len(items) > 0:
                    print(f"First item keys: {list(items[0].keys())}")
                    print(f"First item sample:")
                    print(json.dumps(items[0], indent=2, default=str))
                break
    elif isinstance(result, list):
        print(f"Result is a list with {len(result)} items")
        if len(result) > 0:
            print(f"First item keys: {list(result[0].keys())}")
            print(f"First item sample:")
            print(json.dumps(result[0], indent=2, default=str))

if __name__ == "__main__":
    asyncio.run(main())
