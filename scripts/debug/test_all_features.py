"""
Comprehensive Feature Testing Script for MealMind Web App
Tests all features to ensure proper Swiggy API sync
"""

import asyncio
import sys
from sqlmodel import Session
from src.database import get_engine
from src.models import User
from src.swiggy_mcp_client import SwiggyMCPClient
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_all_features():
    """Test all MealMind features with actual Swiggy sync"""
    
    results = {
        "passed": [],
        "failed": [],
        "warnings": []
    }
    
    # Initialize
    db = Session(get_engine())
    swiggy_client = SwiggyMCPClient()
    
    try:
        # 1. Check if user is authenticated
        logger.info("\n=== 1. AUTHENTICATION CHECK ===")
        user = db.query(User).first()
        if not user or not user.swiggy_token:
            results["failed"].append("Authentication: No authenticated user found")
            logger.error("❌ No authenticated user. Please login first.")
            return results
        
        token = user.swiggy_token
        logger.info(f"✅ User authenticated: {user.telegram_username or user.id}")
        results["passed"].append("Authentication: User logged in")
        
        # 2. Test Food Delivery - Get Addresses
        logger.info("\n=== 2. FOOD DELIVERY - ADDRESSES ===")
        try:
            addresses = await swiggy_client.get_addresses(token)
            if addresses and len(addresses) > 0:
                logger.info(f"✅ Found {len(addresses)} addresses")
                logger.info(f"   Sample: {addresses[0].get('addressLine', 'N/A')[:50]}...")
                results["passed"].append(f"Food Addresses: {len(addresses)} addresses loaded")
            else:
                results["warnings"].append("Food Addresses: No addresses found")
                logger.warning("⚠️  No addresses found")
        except Exception as e:
            results["failed"].append(f"Food Addresses: {str(e)}")
            logger.error(f"❌ Address loading failed: {e}")
        
        # 3. Test Food Delivery - Restaurant Search
        logger.info("\n=== 3. FOOD DELIVERY - RESTAURANT SEARCH ===")
        try:
            if addresses and len(addresses) > 0:
                lat = addresses[0].get('lat')
                lng = addresses[0].get('lng')
                
                restaurants = await swiggy_client.search_restaurants(
                    token=token,
                    lat=lat,
                    lng=lng,
                    query="pizza"
                )
                
                if restaurants and len(restaurants) > 0:
                    logger.info(f"✅ Found {len(restaurants)} restaurants for 'pizza'")
                    logger.info(f"   Sample: {restaurants[0].get('name', 'N/A')}")
                    results["passed"].append(f"Restaurant Search: {len(restaurants)} restaurants found")
                else:
                    results["warnings"].append("Restaurant Search: No results")
                    logger.warning("⚠️  No restaurants found")
            else:
                results["warnings"].append("Restaurant Search: Skipped (no address)")
        except Exception as e:
            results["failed"].append(f"Restaurant Search: {str(e)}")
            logger.error(f"❌ Restaurant search failed: {e}")
        
        # 4. Test Food Delivery - Menu Loading
        logger.info("\n=== 4. FOOD DELIVERY - MENU LOADING ===")
        try:
            if 'restaurants' in locals() and restaurants and len(restaurants) > 0:
                restaurant_id = restaurants[0].get('id')
                address_id = addresses[0].get('id')
                
                menu = await swiggy_client.get_restaurant_menu(
                    token=token,
                    restaurant_id=str(restaurant_id),
                    address_id=str(address_id)
                )
                
                # Count menu items
                item_count = 0
                if isinstance(menu, dict):
                    if 'categories' in menu:
                        for cat in menu['categories']:
                            if 'items' in cat:
                                item_count += len(cat['items'])
                    elif 'items' in menu:
                        item_count = len(menu['items'])
                
                if item_count > 0:
                    logger.info(f"✅ Menu loaded with {item_count} items")
                    results["passed"].append(f"Menu Loading: {item_count} items")
                else:
                    results["warnings"].append("Menu Loading: Empty menu")
                    logger.warning("⚠️  Menu loaded but no items found")
            else:
                results["warnings"].append("Menu Loading: Skipped (no restaurant)")
        except Exception as e:
            results["failed"].append(f"Menu Loading: {str(e)}")
            logger.error(f"❌ Menu loading failed: {e}")
        
        # 5. Test Instamart - Product Search
        logger.info("\n=== 5. INSTAMART - PRODUCT SEARCH ===")
        try:
            if addresses and len(addresses) > 0:
                lat = addresses[0].get('lat')
                lng = addresses[0].get('lng')
                
                products = await swiggy_client.search_instamart_products(
                    token=token,
                    lat=lat,
                    lng=lng,
                    query="milk"
                )
                
                if products and len(products) > 0:
                    logger.info(f"✅ Found {len(products)} products for 'milk'")
                    sample = products[0]
                    product_name = sample.get('displayName') or sample.get('name', 'N/A')
                    logger.info(f"   Sample: {product_name}")
                    
                    # Check if price is available
                    price = None
                    if 'variations' in sample and len(sample['variations']) > 0:
                        price = sample['variations'][0].get('price', {}).get('offer_price')
                    
                    if price:
                        logger.info(f"   Price: ₹{price}")
                        results["passed"].append(f"Instamart Search: {len(products)} products with prices")
                    else:
                        results["warnings"].append("Instamart Search: Products found but price unavailable")
                        logger.warning("⚠️  Products found but price structure unclear")
                else:
                    results["warnings"].append("Instamart Search: No products found")
                    logger.warning("⚠️  No products found")
            else:
                results["warnings"].append("Instamart Search: Skipped (no address)")
        except Exception as e:
            results["failed"].append(f"Instamart Search: {str(e)}")
            logger.error(f"❌ Instamart search failed: {e}")
        
        # 6. Test Instamart - Cart Operations
        logger.info("\n=== 6. INSTAMART - CART OPERATIONS ===")
        try:
            cart = await swiggy_client.get_instamart_cart(token)
            if cart is not None:
                item_count = len(cart.get('items', []))
                logger.info(f"✅ Cart loaded with {item_count} items")
                results["passed"].append(f"Instamart Cart: Loaded successfully ({item_count} items)")
            else:
                results["warnings"].append("Instamart Cart: Empty or null response")
                logger.warning("⚠️  Cart returned empty")
        except Exception as e:
            results["failed"].append(f"Instamart Cart: {str(e)}")
            logger.error(f"❌ Cart loading failed: {e}")
        
        # 7. Test Food Cart Operations
        logger.info("\n=== 7. FOOD DELIVERY - CART OPERATIONS ===")
        try:
            if 'address_id' in locals():
                food_cart = await swiggy_client.get_food_cart(token, str(address_id))
                if food_cart is not None:
                    item_count = len(food_cart.get('items', []))
                    logger.info(f"✅ Food cart loaded with {item_count} items")
                    results["passed"].append(f"Food Cart: Loaded successfully ({item_count} items)")
                else:
                    results["warnings"].append("Food Cart: Empty response")
                    logger.warning("⚠️  Food cart returned empty")
            else:
                results["warnings"].append("Food Cart: Skipped (no address)")
        except Exception as e:
            results["failed"].append(f"Food Cart: {str(e)}")
            logger.error(f"❌ Food cart loading failed: {e}")
        
        # 8. Test Orders Sync
        logger.info("\n=== 8. ORDERS - SYNC & DISPLAY ===")
        try:
            orders_data = await swiggy_client.get_orders(token)
            if orders_data and 'orders' in orders_data:
                order_count = len(orders_data['orders'])
                logger.info(f"✅ Found {order_count} orders")
                results["passed"].append(f"Orders: {order_count} orders synced")
            else:
                results["warnings"].append("Orders: No orders found")
                logger.warning("⚠️  No orders found")
        except Exception as e:
            results["failed"].append(f"Orders: {str(e)}")
            logger.error(f"❌ Orders sync failed: {e}")
        
        # 9. Test Analytics
        logger.info("\n=== 9. ANALYTICS ===")
        try:
            from src.analytics import build_analytics
            analytics = build_analytics(db, user.id)
            if analytics:
                logger.info(f"✅ Analytics generated")
                logger.info(f"   Total spent: ₹{analytics.get('total_spent', 0)}")
                logger.info(f"   Total orders: {analytics.get('total_orders', 0)}")
                results["passed"].append("Analytics: Generated successfully")
            else:
                results["warnings"].append("Analytics: Empty data")
                logger.warning("⚠️  Analytics returned empty")
        except Exception as e:
            results["failed"].append(f"Analytics: {str(e)}")
            logger.error(f"❌ Analytics generation failed: {e}")
        
        # 10. Test Insights
        logger.info("\n=== 10. INSIGHTS ===")
        try:
            from src.analytics import build_food_insights_response
            insights = build_food_insights_response(db, user.id)
            if insights:
                logger.info(f"✅ Insights generated")
                results["passed"].append("Insights: Generated successfully")
            else:
                results["warnings"].append("Insights: Empty data")
                logger.warning("⚠️  Insights returned empty")
        except Exception as e:
            results["failed"].append(f"Insights: {str(e)}")
            logger.error(f"❌ Insights generation failed: {e}")
        
    finally:
        db.close()
    
    return results

def print_summary(results):
    """Print test summary"""
    logger.info("\n" + "="*70)
    logger.info("TEST SUMMARY")
    logger.info("="*70)
    
    logger.info(f"\n✅ PASSED ({len(results['passed'])} tests):")
    for item in results['passed']:
        logger.info(f"   • {item}")
    
    if results['warnings']:
        logger.info(f"\n⚠️  WARNINGS ({len(results['warnings'])} items):")
        for item in results['warnings']:
            logger.info(f"   • {item}")
    
    if results['failed']:
        logger.info(f"\n❌ FAILED ({len(results['failed'])} tests):")
        for item in results['failed']:
            logger.info(f"   • {item}")
    
    logger.info("\n" + "="*70)
    
    # Overall status
    total_tests = len(results['passed']) + len(results['failed'])
    if len(results['failed']) == 0:
        logger.info("🎉 ALL TESTS PASSED!")
    else:
        pass_rate = (len(results['passed']) / total_tests * 100) if total_tests > 0 else 0
        logger.info(f"Pass Rate: {pass_rate:.1f}% ({len(results['passed'])}/{total_tests})")
    
    logger.info("="*70 + "\n")

if __name__ == "__main__":
    logger.info("Starting comprehensive feature test...\n")
    results = asyncio.run(test_all_features())
    print_summary(results)
    
    # Exit with error code if there are failures
    sys.exit(1 if results['failed'] else 0)
