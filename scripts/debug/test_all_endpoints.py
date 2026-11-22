#!/usr/bin/env python3
"""
Comprehensive test script for all web API endpoints.
Run this after logging in through the browser to get a valid session ID.
"""
import requests
import json
import sys
from typing import Optional

BASE_URL = "http://localhost:8000/api"

def test_endpoint(name: str, method: str, url: str, headers: dict, params: dict = None, data: dict = None):
    """Test a single endpoint and print results."""
    print(f"\n{'='*80}")
    print(f"Testing: {name}")
    print(f"{'='*80}")
    print(f"Method: {method}")
    print(f"URL: {url}")
    
    try:
        if method == "GET":
            response = requests.get(url, headers=headers, params=params)
        elif method == "POST":
            response = requests.post(url, headers=headers, json=data)
        else:
            print(f"❌ Unsupported method: {method}")
            return False
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            print(f"✅ SUCCESS")
            result = response.json()
            print(f"Response (truncated):")
            print(json.dumps(result, indent=2)[:500])
            if len(json.dumps(result)) > 500:
                print("... (truncated)")
            return True
        else:
            print(f"❌ FAILED")
            print(f"Error: {response.text}")
            return False
    
    except Exception as e:
        print(f"❌ EXCEPTION: {str(e)}")
        return False

def main():
    print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║                   MealMind Web API - Comprehensive Test Suite                ║
╚══════════════════════════════════════════════════════════════════════════════╝

INSTRUCTIONS:
1. Make sure the backend is running: python -m src.main
2. Make sure you're logged in via the browser: http://localhost:5173
3. Open browser DevTools (F12) → Application → Local Storage
4. Copy the 'session_id' value
5. Paste it when prompted below

""")
    
    session_id = input("Enter your session_id from browser localStorage: ").strip()
    
    if not session_id:
        print("❌ No session ID provided. Exiting.")
        sys.exit(1)
    
    headers = {
        "X-Session-ID": session_id,
        "Content-Type": "application/json"
    }
    
    results = {}
    
    # Test 1: Auth Status
    results["auth_status"] = test_endpoint(
        "Authentication Status",
        "GET",
        f"{BASE_URL}/auth/status",
        headers
    )
    
    # Test 2: Orders
    results["orders"] = test_endpoint(
        "Order History (all)",
        "GET",
        f"{BASE_URL}/orders",
        headers,
        params={"limit": 10}
    )
    
    # Test 3: Orders with filters
    results["orders_filtered"] = test_endpoint(
        "Order History (filtered by date)",
        "GET",
        f"{BASE_URL}/orders",
        headers,
        params={
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "limit": 5
        }
    )
    
    # Test 4: Analytics
    results["analytics"] = test_endpoint(
        "Analytics (all time)",
        "GET",
        f"{BASE_URL}/analytics",
        headers
    )
    
    # Test 5: Insights
    results["insights"] = test_endpoint(
        "Personalized Insights",
        "GET",
        f"{BASE_URL}/insights",
        headers
    )
    
    # Test 6: Addresses
    results["addresses"] = test_endpoint(
        "User Addresses",
        "GET",
        f"{BASE_URL}/food/addresses",
        headers
    )
    
    # Store address_id for subsequent tests
    address_id = None
    if results["addresses"]:
        # Try to extract address from successful response
        try:
            response = requests.get(f"{BASE_URL}/food/addresses", headers=headers)
            if response.status_code == 200:
                data = response.json()
                if data.get("addresses") and len(data["addresses"]) > 0:
                    address_id = data["addresses"][0].get("id")
                    print(f"\n📍 Using address_id for search tests: {address_id[:30]}...")
        except:
            pass
    
    if address_id:
        # Test 7: Food Search
        results["food_search"] = test_endpoint(
            "Food Delivery Search (Pizza)",
            "POST",
            f"{BASE_URL}/food/search-restaurants",
            headers,
            data={
                "address_id": address_id,
                "query": "pizza"
            }
        )
        
        # Test 8: Instamart Search
        results["instamart_search"] = test_endpoint(
            "Instamart Search (Milk)",
            "POST",
            f"{BASE_URL}/instamart/search",
            headers,
            data={
                "address_id": address_id,
                "query": "milk",
                "offset": 0
            }
        )
        
        # Test 9: Dineout Search
        results["dineout_search"] = test_endpoint(
            "Dineout Search",
            "POST",
            f"{BASE_URL}/dineout/search",
            headers,
            data={
                "query": "restaurant",
                "address_id": address_id,
                "lat": None,
                "lng": None
            }
        )
    else:
        print("\n⚠️  No address_id found, skipping search tests")
        results["food_search"] = False
        results["instamart_search"] = False
        results["dineout_search"] = False
    
    # Summary
    print(f"\n\n{'='*80}")
    print(f"TEST SUMMARY")
    print(f"{'='*80}")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, passed_flag in results.items():
        status = "✅ PASS" if passed_flag else "❌ FAIL"
        print(f"{test_name:30s} {status}")
    
    print(f"\n{'='*80}")
    print(f"Total: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    print(f"{'='*80}\n")
    
    if passed == total:
        print("🎉 All tests passed! The application is working correctly.")
        return 0
    else:
        print("⚠️  Some tests failed. Check the output above for details.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
