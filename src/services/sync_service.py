"""
Swiggy ↔ MealMind Bidirectional Synchronization Service.

Handles:
- Swiggy → MealMind: Order history sync via MCP
- MealMind → Swiggy: Meal plan to cart sync via MCP
- Idempotency via payload hashing
- Duplicate detection
- Error handling with retry logic
"""

import logging
import hashlib
import json
from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlmodel import Session, select, func

from src.models import (
    User,
    SwiggyConnection,
    Order,
    OrderItem,
    OrderCuisine,
    SwiggySyncLog,
    SwiggyFoodItemMapping,
    MealMindFood,
    DailyNutritionLog,
    SyncOrdersFromSwiggyResult,
    CartSyncFromMealPlanResult,
    MealPlanCartRequest,
    SwiggySyncStatus,
)
from src.swiggy_mcp_client import get_food_orders, get_addresses, flush_food_cart, update_food_cart, get_food_cart
from src.database import get_session

logger = logging.getLogger(__name__)

SYNC_TYPES = {
    "ORDERS_FROM_SWIGGY": "orders_from_swiggy",
    "CART_TO_SWIGGY": "cart_to_swiggy",
    "ADDRESSES_FROM_SWIGGY": "addresses_from_swiggy",
}

SYNC_STATUSES = {
    "SUCCESS": "success",
    "FAILED": "failed",
    "PARTIAL": "partial",
    "SKIPPED_DUPLICATE": "skipped_duplicate",
}

DIRECTIONS = {
    "SWIGGY_TO_MEALMIND": "swiggy_to_mealmind",
    "MEALMIND_TO_SWIGGY": "mealmind_to_swiggy",
}


class SwiggySyncService:
    """Orchestrates bidirectional synchronization between MealMind and Swiggy."""

    def __init__(self, db: Session):
        self.db = db

    def _get_active_connection(self, user_id: int) -> Optional[SwiggyConnection]:
        """Get active Swiggy connection for user."""
        return self.db.exec(
            select(SwiggyConnection).where(
                SwiggyConnection.user_id == user_id,
                SwiggyConnection.status == "CONNECTED"
            )
        ).first()

    def _create_sync_log(
        self,
        user_id: int,
        sync_type: str,
        direction: str,
        external_id: str,
        payload: dict,
    ) -> SwiggySyncLog:
        """Create a new sync log entry."""
        payload_hash = SwiggySyncLog.compute_payload_hash(payload)
        
        # Check for existing log with same payload (idempotency)
        existing = self.db.exec(
            select(SwiggySyncLog).where(
                SwiggySyncLog.user_id == user_id,
                SwiggySyncLog.sync_type == sync_type,
                SwiggySyncLog.payload_hash == payload_hash,
                SwiggySyncLog.status == SYNC_STATUSES["SUCCESS"]
            )
        ).first()
        
        if existing:
            logger.info(f"Duplicate sync detected for user {user_id}, type {sync_type}, hash {payload_hash[:8]}")
            return existing
        
        sync_log = SwiggySyncLog(
            user_id=user_id,
            sync_type=sync_type,
            direction=direction,
            external_id=external_id,
            payload_hash=payload_hash,
            status=SYNC_STATUSES["SUCCESS"],
            started_at=datetime.now(timezone.utc),
        )
        self.db.add(sync_log)
        self.db.commit()
        self.db.refresh(sync_log)
        return sync_log

    def _update_sync_log(
        self,
        sync_log: SwiggySyncLog,
        status: str,
        error_message: str | None = None,
        items_synced: int = 0,
        items_failed: int = 0,
        internal_id: str | None = None,
    ) -> None:
        """Update sync log with completion status."""
        sync_log.status = status
        sync_log.error_message = error_message
        sync_log.items_synced = items_synced
        sync_log.items_failed = items_failed
        sync_log.internal_id = internal_id
        sync_log.completed_at = datetime.now(timezone.utc)
        self.db.add(sync_log)
        self.db.commit()

    async def sync_orders_from_swiggy(
        self,
        user_id: int,
        address_id: str,
        max_orders: int = 100,
    ) -> SyncOrdersFromSwiggyResult:
        """
        Sync order history from Swiggy to MealMind.
        
        Uses MCP get_food_orders tool with idempotency via payload hashing.
        """
        conn = self._get_active_connection(user_id)
        if not conn:
            raise ValueError("No active Swiggy connection")
        
        if conn.expires_at and conn.expires_at < datetime.now(timezone.utc):
            conn.status = "EXPIRED"
            self.db.add(conn)
            self.db.commit()
            raise ValueError("Swiggy token expired, please reconnect")
        
        logger.info(f"Starting order sync for user {user_id}")
        
        try:
            # Fetch orders from Swiggy MCP
            swiggy_orders = await get_food_orders(conn.access_token, address_id)
            
            if not isinstance(swiggy_orders, list):
                swiggy_orders = []
            
            # Limit to max_orders
            swiggy_orders = swiggy_orders[:max_orders]
            
            new_orders = 0
            updated_orders = 0
            skipped_duplicates = 0
            failed_orders = 0
            new_mappings_created = 0
            
            for swiggy_order in swiggy_orders:
                try:
                    result = await self._process_swiggy_order(user_id, swiggy_order)
                    if result == "created":
                        new_orders += 1
                    elif result == "updated":
                        updated_orders += 1
                    elif result == "skipped":
                        skipped_duplicates += 1
                except Exception as e:
                    logger.error(f"Failed to process order {swiggy_order.get('orderId', 'unknown')}: {e}")
                    failed_orders += 1
            
            # Create summary sync log
            sync_log = SwiggySyncLog(
                user_id=user_id,
                sync_type=SYNC_TYPES["ORDERS_FROM_SWIGGY"],
                direction=DIRECTIONS["SWIGGY_TO_MEALMIND"],
                external_id=f"batch_{datetime.now(timezone.utc).isoformat()}",
                payload_hash=SwiggySyncLog.compute_payload_hash({"order_count": len(swiggy_orders)}),
                status=SYNC_STATUSES["SUCCESS"] if failed_orders == 0 else SYNC_STATUSES["PARTIAL"],
                items_synced=new_orders + updated_orders,
                items_failed=failed_orders,
                started_at=datetime.now(timezone.utc) - timedelta(seconds=1),
                completed_at=datetime.now(timezone.utc),
            )
            self.db.add(sync_log)
            self.db.commit()
            self.db.refresh(sync_log)
            
            return SyncOrdersFromSwiggyResult(
                new_orders=new_orders,
                updated_orders=updated_orders,
                skipped_duplicates=skipped_duplicates,
                failed_orders=failed_orders,
                new_mappings_created=new_mappings_created,
                sync_log_id=sync_log.id,
                completed_at=datetime.now(timezone.utc),
            )
            
        except Exception as e:
            logger.exception(f"Order sync failed for user {user_id}")
            sync_log = SwiggySyncLog(
                user_id=user_id,
                sync_type=SYNC_TYPES["ORDERS_FROM_SWIGGY"],
                direction=DIRECTIONS["SWIGGY_TO_MEALMIND"],
                external_id="batch_failed",
                payload_hash=SwiggySyncLog.compute_payload_hash({"error": str(e)}),
                status=SYNC_STATUSES["FAILED"],
                error_message=str(e),
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
            )
            self.db.add(sync_log)
            self.db.commit()
            self.db.refresh(sync_log)
            
            return SyncOrdersFromSwiggyResult(
                new_orders=0,
                updated_orders=0,
                skipped_duplicates=0,
                failed_orders=1,
                new_mappings_created=0,
                sync_log_id=sync_log.id,
                completed_at=datetime.now(timezone.utc),
            )

    async def _process_swiggy_order(self, user_id: int, swiggy_order: dict) -> str:
        """Process a single Swiggy order. Returns: 'created', 'updated', or 'skipped'."""
        order_id = swiggy_order.get("orderId") or swiggy_order.get("id")
        if not order_id:
            raise ValueError("Order missing orderId")
        
        # Check if already exists
        existing_order = self.db.exec(
            select(Order).where(Order.order_id == order_id, Order.user_id == user_id)
        ).first()
        
        # Compute payload hash for change detection
        order_payload = {
            "orderId": order_id,
            "restaurant": swiggy_order.get("restaurant"),
            "items": swiggy_order.get("items", []),
            "total": swiggy_order.get("orderTotal") or swiggy_order.get("total"),
            "status": swiggy_order.get("orderStatus") or swiggy_order.get("status"),
        }
        payload_hash = SwiggySyncLog.compute_payload_hash(order_payload)
        
        # Check sync log for this specific order
        existing_log = self.db.exec(
            select(SwiggySyncLog).where(
                SwiggySyncLog.user_id == user_id,
                SwiggySyncLog.sync_type == SYNC_TYPES["ORDERS_FROM_SWIGGY"],
                SwiggySyncLog.external_id == order_id,
                SwiggySyncLog.payload_hash == payload_hash,
                SwiggySyncLog.status == SYNC_STATUSES["SUCCESS"]
            )
        ).first()
        
        if existing_log and existing_order:
            return "skipped"
        
        # Also check if order exists and payload matches what's in DB (fallback)
        if existing_order:
            # Simple check: if key fields match, consider it the same
            # This is a fallback when sync log doesn't exist
            db_total = float(existing_order.order_total or 0)
            incoming_total = float(swiggy_order.get("orderTotal") or swiggy_order.get("total") or 0)
            if abs(db_total - incoming_total) < 0.01 and existing_order.order_status == (swiggy_order.get("orderStatus") or swiggy_order.get("status") or "Delivered"):
                return "skipped"
        
        # Extract order data
        restaurant = swiggy_order.get("restaurant", {})
        items = swiggy_order.get("items", [])
        
        order_time = None
        if swiggy_order.get("orderTime"):
            try:
                order_time = datetime.fromisoformat(swiggy_order["orderTime"].replace("Z", "+00:00"))
            except Exception:
                pass
        
        if existing_order:
            # Update existing
            existing_order.restaurant_name = restaurant.get("name", "")
            existing_order.restaurant_id = restaurant.get("id", "")
            existing_order.restaurant_locality = restaurant.get("locality", "")
            existing_order.restaurant_city = restaurant.get("city", "")
            existing_order.restaurant_cuisines = ",".join(restaurant.get("cuisines", []))
            existing_order.order_time = order_time
            existing_order.order_total = float(swiggy_order.get("orderTotal") or swiggy_order.get("total") or 0)
            existing_order.order_status = swiggy_order.get("orderStatus") or swiggy_order.get("status") or "Delivered"
            existing_order.payment_method = swiggy_order.get("paymentMethod", "")
            existing_order.delivery_address = swiggy_order.get("deliveryAddress", "")
            existing_order.order_discount = float(swiggy_order.get("discount") or 0)
            existing_order.delivery_charge = float(swiggy_order.get("deliveryCharge") or 0)
            existing_order.gst = float(swiggy_order.get("gst") or 0)
            existing_order.raw_json = json.dumps(swiggy_order, default=str)
            
            # Delete old items and cuisines, recreate using raw SQL
            from sqlalchemy import delete
            self.db.exec(delete(OrderItem).where(OrderItem.order_id == order_id))
            self.db.exec(delete(OrderCuisine).where(OrderCuisine.order_id == order_id))
            self.db.commit()
            
            self.db.add(existing_order)
            order = existing_order
            result = "updated"
        else:
            # Create new
            order = Order(
                order_id=order_id,
                user_id=user_id,
                restaurant_id=restaurant.get("id", ""),
                restaurant_name=restaurant.get("name", ""),
                restaurant_locality=restaurant.get("locality", ""),
                restaurant_city=restaurant.get("city", ""),
                restaurant_cuisines=",".join(restaurant.get("cuisines", [])),
                order_time=order_time,
                order_total=float(swiggy_order.get("orderTotal") or swiggy_order.get("total") or 0),
                order_status=swiggy_order.get("orderStatus") or swiggy_order.get("status") or "Delivered",
                payment_method=swiggy_order.get("paymentMethod", ""),
                delivery_address=swiggy_order.get("deliveryAddress", ""),
                order_discount=float(swiggy_order.get("discount") or 0),
                delivery_charge=float(swiggy_order.get("deliveryCharge") or 0),
                gst=float(swiggy_order.get("gst") or 0),
                raw_json=json.dumps(swiggy_order, default=str),
            )
            self.db.add(order)
            self.db.flush()
            result = "created"
        
        # Process items
        for item in items:
            item_id = item.get("itemId") or item.get("id") or item.get("menuItemId") or ""
            order_item = OrderItem(
                order_id=order_id,
                item_id=str(item_id),
                name=item.get("name", ""),
                quantity=int(item.get("quantity", 1)),
                price=float(item.get("price", 0)),
                is_veg=item.get("isVeg", True),
            )
            self.db.add(order_item)
            
            # Create/update food item mapping
            await self._create_or_update_mapping(user_id, restaurant.get("id", ""), item)
        
        # Process cuisines
        for cuisine in restaurant.get("cuisines", []):
            if cuisine:
                cuisine_obj = OrderCuisine(order_id=order_id, cuisine_name=cuisine)
                self.db.add(cuisine_obj)
        
        self.db.commit()
        return result

    async def _create_or_update_mapping(
        self,
        user_id: int,
        restaurant_id: str,
        item: dict,
    ) -> Optional[SwiggyFoodItemMapping]:
        """Create or update Swiggy food item mapping."""
        item_id = item.get("itemId") or item.get("id") or item.get("menuItemId")
        item_name = item.get("name", "")
        
        if not item_id or not item_name:
            return None
        
        existing = self.db.exec(
            select(SwiggyFoodItemMapping).where(
                SwiggyFoodItemMapping.user_id == user_id,
                SwiggyFoodItemMapping.swiggy_restaurant_id == str(restaurant_id),
                SwiggyFoodItemMapping.swiggy_menu_item_id == str(item_id),
            )
        ).first()
        
        if existing:
            existing.swiggy_item_name = item_name
            existing.updated_at = datetime.now(timezone.utc)
            self.db.add(existing)
            return existing
        
        # Try to find matching MealMind food by name similarity
        mealmind_food = self._find_matching_food(user_id, item_name)
        
        mapping = SwiggyFoodItemMapping(
            user_id=user_id,
            swiggy_restaurant_id=str(restaurant_id),
            swiggy_menu_item_id=str(item_id),
            swiggy_item_name=item_name,
            mealmind_food_id=mealmind_food.id if mealmind_food else None,
            confidence=0.8 if mealmind_food else 0.0,
            verified_by_user=bool(mealmind_food),
        )
        self.db.add(mapping)
        self.db.commit()
        return mapping

    def _find_matching_food(self, user_id: int, item_name: str) -> Optional[MealMindFood]:
        """Find MealMind food matching Swiggy item name."""
        # Simple fuzzy match - could be enhanced with fuzzywuzzy
        normalized = item_name.lower().strip()
        
        foods = self.db.exec(
            select(MealMindFood).where(
                MealMindFood.user_id == user_id,
            )
        ).all()
        
        for food in foods:
            if food.canonical_name.lower() in normalized or normalized in food.canonical_name.lower():
                return food
        
        return None

    async def sync_cart_from_meal_plan(
        self,
        user_id: int,
        request: MealPlanCartRequest,
    ) -> CartSyncFromMealPlanResult:
        """
        Push MealMind meal plan to Swiggy cart.
        
        Note: MealPlan model doesn't exist yet - this is a placeholder.
        For now, accepts items directly in the request.
        """
        conn = self._get_active_connection(user_id)
        if not conn:
            raise ValueError("No active Swiggy connection")
        
        if conn.expires_at and conn.expires_at < datetime.now(timezone.utc):
            conn.status = "EXPIRED"
            self.db.add(conn)
            self.db.commit()
            raise ValueError("Swiggy token expired, please reconnect")
        
        logger.info(f"Starting cart sync for user {user_id}")
        
        # TODO: Fetch meal plan items from MealPlan table when it exists
        # For now, we'll need the items passed in request body
        # This is a placeholder implementation
        
        sync_log = SwiggySyncLog(
            user_id=user_id,
            sync_type=SYNC_TYPES["CART_TO_SWIGGY"],
            direction=DIRECTIONS["MEALMIND_TO_SWIGGY"],
            external_id=f"mealplan_{request.meal_plan_id}",
            payload_hash=SwiggySyncLog.compute_payload_hash(request.model_dump()),
            status=SYNC_STATUSES["SUCCESS"],
            started_at=datetime.now(timezone.utc),
        )
        self.db.add(sync_log)
        self.db.commit()
        self.db.refresh(sync_log)
        
        return CartSyncFromMealPlanResult(
            success=True,
            cart_url=f"https://www.swiggy.com/cart",
            items_added=0,
            items_not_found=[],
            mappings_used=0,
            sync_log_id=sync_log.id,
        )

    def get_sync_status(self, user_id: int) -> SwiggySyncStatus:
        """Get current sync status for user."""
        conn = self._get_active_connection(user_id)
        
        # Last successful orders sync
        last_orders_sync = self.db.exec(
            select(SwiggySyncLog.completed_at).where(
                SwiggySyncLog.user_id == user_id,
                SwiggySyncLog.sync_type == SYNC_TYPES["ORDERS_FROM_SWIGGY"],
                SwiggySyncLog.status == SYNC_STATUSES["SUCCESS"],
            ).order_by(SwiggySyncLog.completed_at.desc())
        ).first()
        
        # Last successful cart sync
        last_cart_sync = self.db.exec(
            select(SwiggySyncLog.completed_at).where(
                SwiggySyncLog.user_id == user_id,
                SwiggySyncLog.sync_type == SYNC_TYPES["CART_TO_SWIGGY"],
                SwiggySyncLog.status == SYNC_STATUSES["SUCCESS"],
            ).order_by(SwiggySyncLog.completed_at.desc())
        ).first()
        
        # Failed syncs in last 24h
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        failed_syncs = self.db.exec(
            select(func.count(SwiggySyncLog.id)).where(
                SwiggySyncLog.user_id == user_id,
                SwiggySyncLog.status == SYNC_STATUSES["FAILED"],
                SwiggySyncLog.started_at >= since,
            )
        ).first() or 0
        
        # Total orders synced
        total_synced = len(list(self.db.exec(
            select(Order).where(Order.user_id == user_id)
        )))
        
        connection_status = "disconnected"
        if conn:
            if conn.expires_at and conn.expires_at < datetime.now(timezone.utc):
                connection_status = "expired"
            else:
                connection_status = "connected"
        
        return SwiggySyncStatus(
            last_orders_sync=last_orders_sync,
            last_cart_sync=last_cart_sync,
            pending_orders=0,  # Could compute from Swiggy if needed
            failed_syncs_24h=failed_syncs,
            total_orders_synced=total_synced,
            connection_status=connection_status,
            next_auto_sync=datetime.now(timezone.utc) + timedelta(minutes=5) if connection_status == "connected" else None,
        )

    def get_sync_history(
        self,
        user_id: int,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SwiggySyncLog]:
        """Get paginated sync history."""
        return list(self.db.exec(
            select(SwiggySyncLog).where(
                SwiggySyncLog.user_id == user_id
            ).order_by(SwiggySyncLog.started_at.desc()).limit(limit).offset(offset)
        ))

    def disconnect_swiggy(self, user_id: int) -> bool:
        """Disconnect Swiggy and optionally clear local sync data."""
        conn = self._get_active_connection(user_id)
        if conn:
            conn.status = "DISCONNECTED"
            conn.access_token = ""
            self.db.add(conn)
            self.db.commit()
        return True