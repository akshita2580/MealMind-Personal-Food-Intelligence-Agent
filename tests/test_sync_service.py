"""
Tests for Swiggy Sync Service.

Tests cover:
- Idempotency via payload hashing
- Duplicate order detection
- Sync log creation
- Error handling
- Food item mapping
"""

import pytest
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from sqlmodel import Session, create_engine, SQLModel, select, func

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
)
from src.services.sync_service import SwiggySyncService
from src.database import get_session


# Test database setup
TEST_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture
def db_session():
    """Create a test database session."""
    engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def test_user(db_session):
    """Create a test user."""
    user = User(telegram_id="test_user_123")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def test_connection(db_session, test_user):
    """Create a test Swiggy connection."""
    conn = SwiggyConnection(
        user_id=test_user.id,
        access_token="test_token",
        status="CONNECTED",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db_session.add(conn)
    db_session.commit()
    db_session.refresh(conn)
    return conn


@pytest.fixture
def sync_service(db_session):
    """Create a sync service instance."""
    return SwiggySyncService(db_session)


@pytest.fixture
def sample_swiggy_order():
    """Sample Swiggy order data."""
    return {
        "orderId": "ORDER_123",
        "id": "ORDER_123",
        "restaurant": {
            "id": "REST_456",
            "name": "Test Restaurant",
            "locality": "Koramangala",
            "city": "Bangalore",
            "cuisines": ["North Indian", "Chinese"],
        },
        "orderTime": "2024-01-15T19:30:00Z",
        "orderTotal": 450.0,
        "total": 450.0,
        "orderStatus": "Delivered",
        "status": "Delivered",
        "paymentMethod": "UPI",
        "deliveryAddress": "123 Test St, Bangalore",
        "discount": 50.0,
        "deliveryCharge": 30.0,
        "gst": 25.0,
        "items": [
            {
                "itemId": "ITEM_789",
                "id": "ITEM_789",
                "menuItemId": "ITEM_789",
                "name": "Paneer Biryani",
                "quantity": 1,
                "price": 250.0,
                "isVeg": True,
            },
            {
                "itemId": "ITEM_790",
                "id": "ITEM_790",
                "menuItemId": "ITEM_790",
                "name": "Butter Naan",
                "quantity": 2,
                "price": 50.0,
                "isVeg": True,
            },
        ],
    }


class TestSyncOrdersFromSwiggy:
    """Tests for syncing orders from Swiggy to MealMind."""

    @pytest.mark.asyncio
    async def test_sync_new_order(self, sync_service, test_user, test_connection, sample_swiggy_order):
        """Test syncing a new order creates all records."""
        with patch('src.services.sync_service.get_food_orders', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = [sample_swiggy_order]
            
            result = await sync_service.sync_orders_from_swiggy(
                user_id=test_user.id,
                address_id="ADDR_123",
            )
            
            assert result.new_orders == 1
            assert result.updated_orders == 0
            assert result.skipped_duplicates == 0
            assert result.failed_orders == 0
            
            # Verify order created
            order = sync_service.db.get(Order, "ORDER_123")
            assert order is not None
            assert order.restaurant_name == "Test Restaurant"
            assert order.order_total == 450.0
            
            # Verify items created
            items = sync_service.db.exec(
                select(OrderItem).where(OrderItem.order_id == "ORDER_123")
            ).all()
            assert len(items) == 2
            
            # Verify cuisines created
            cuisines = sync_service.db.exec(
                select(OrderCuisine).where(OrderCuisine.order_id == "ORDER_123")
            ).all()
            assert len(cuisines) == 2
            
            # Verify sync log created
            logs = sync_service.db.exec(
                select(SwiggySyncLog).where(SwiggySyncLog.user_id == test_user.id)
            ).all()
            assert len(logs) >= 1

    @pytest.mark.asyncio
    async def test_sync_duplicate_order_skipped(self, sync_service, test_user, test_connection, sample_swiggy_order):
        """Test that duplicate orders are skipped via payload hash."""
        with patch('src.services.sync_service.get_food_orders', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = [sample_swiggy_order]
            
            # First sync
            result1 = await sync_service.sync_orders_from_swiggy(test_user.id, "ADDR_123")
            assert result1.new_orders == 1
            
            # Second sync with same data
            result2 = await sync_service.sync_orders_from_swiggy(test_user.id, "ADDR_123")
            assert result2.skipped_duplicates == 1
            assert result2.new_orders == 0

    @pytest.mark.asyncio
    async def test_sync_updated_order(self, sync_service, test_user, test_connection, sample_swiggy_order):
        """Test that changed orders are updated."""
        with patch('src.services.sync_service.get_food_orders', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = [sample_swiggy_order]
            
            # First sync
            await sync_service.sync_orders_from_swiggy(test_user.id, "ADDR_123")
            
            # Modify order
            modified_order = sample_swiggy_order.copy()
            modified_order["orderTotal"] = 500.0
            modified_order["orderStatus"] = "Cancelled"
            mock_get.return_value = [modified_order]
            
            # Second sync
            result = await sync_service.sync_orders_from_swiggy(test_user.id, "ADDR_123")
            assert result.updated_orders == 1
            
            # Verify order updated
            order = sync_service.db.get(Order, "ORDER_123")
            assert order.order_total == 500.0
            assert order.order_status == "Cancelled"

    @pytest.mark.asyncio
    async def test_sync_creates_food_mappings(self, sync_service, test_user, test_connection, sample_swiggy_order):
        """Test that food item mappings are created during sync."""
        with patch('src.services.sync_service.get_food_orders', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = [sample_swiggy_order]
            
            await sync_service.sync_orders_from_swiggy(test_user.id, "ADDR_123")
            
            # Verify mappings created
            mappings = sync_service.db.exec(
                select(SwiggyFoodItemMapping).where(
                    SwiggyFoodItemMapping.user_id == test_user.id
                )
            ).all()
            assert len(mappings) == 2
            
            for mapping in mappings:
                assert mapping.swiggy_restaurant_id == "REST_456"
                # Confidence is 0.0 when no MealMind food matches
                assert mapping.confidence == 0.0

    @pytest.mark.asyncio
    async def test_sync_failed_connection(self, sync_service, test_user, db_session):
        """Test sync fails gracefully with no connection."""
        # Remove connection
        conn = sync_service.db.get(SwiggyConnection, test_user.id)
        if conn:
            sync_service.db.delete(conn)
            sync_service.db.commit()
        
        with pytest.raises(ValueError, match="No active Swiggy connection"):
            await sync_service.sync_orders_from_swiggy(test_user.id, "ADDR_123")


class TestIdempotency:
    """Tests for idempotency via payload hashing."""

    def test_payload_hash_consistency(self):
        """Test that same payload produces same hash."""
        data = {"orderId": "123", "total": 100, "items": [{"name": "Test"}]}
        
        hash1 = SwiggySyncLog.compute_payload_hash(data)
        hash2 = SwiggySyncLog.compute_payload_hash(data)
        
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex length

    def test_payload_hash_different_for_different_data(self):
        """Test that different payloads produce different hashes."""
        data1 = {"orderId": "123", "total": 100}
        data2 = {"orderId": "123", "total": 200}
        
        hash1 = SwiggySyncLog.compute_payload_hash(data1)
        hash2 = SwiggySyncLog.compute_payload_hash(data2)
        
        assert hash1 != hash2


class TestFoodMappings:
    """Tests for food item mapping functionality."""

    @pytest.mark.asyncio
    async def test_create_mapping(self, sync_service, test_user):
        """Test creating a food item mapping."""
        mapping = await sync_service._create_or_update_mapping(
            user_id=test_user.id,
            restaurant_id="REST_456",
            item={
                "itemId": "ITEM_789",
                "name": "Paneer Biryani",
            },
        )
        
        assert mapping is not None
        assert mapping.swiggy_restaurant_id == "REST_456"
        assert mapping.swiggy_menu_item_id == "ITEM_789"
        assert mapping.swiggy_item_name == "Paneer Biryani"
        # Confidence is 0.0 when no MealMind food matches
        assert mapping.confidence == 0.0

    @pytest.mark.asyncio
    async def test_update_existing_mapping(self, sync_service, test_user):
        """Test updating an existing mapping."""
        # Create initial mapping
        await sync_service._create_or_update_mapping(
            user_id=test_user.id,
            restaurant_id="REST_456",
            item={"itemId": "ITEM_789", "name": "Paneer Biryani"},
        )
        
        # Update with new name
        mapping = await sync_service._create_or_update_mapping(
            user_id=test_user.id,
            restaurant_id="REST_456",
            item={"itemId": "ITEM_789", "name": "Paneer Biryani (Spicy)"},
        )
        
        assert mapping.swiggy_item_name == "Paneer Biryani (Spicy)"

    @pytest.mark.asyncio
    async def test_mapping_links_to_mealmind_food(self, sync_service, test_user, db_session):
        """Test mapping links to MealMind food when name matches."""
        # Create MealMind food first
        food = MealMindFood(
            user_id=test_user.id,
            name="Paneer Biryani",
            canonical_name="paneer biryani",
            calories_per_100g=200.0,
            protein_g_per_100g=8.0,
            carbs_g_per_100g=30.0,
            fat_g_per_100g=5.0,
            source="manual",
        )
        db_session.add(food)
        db_session.commit()
        db_session.refresh(food)
        
        # Create mapping - should link to existing food
        mapping = await sync_service._create_or_update_mapping(
            user_id=test_user.id,
            restaurant_id="REST_456",
            item={"itemId": "ITEM_789", "name": "Paneer Biryani"},
        )
        
        assert mapping.mealmind_food_id == food.id
        assert mapping.confidence > 0.5
        assert mapping.verified_by_user is True


class TestSyncStatus:
    """Tests for sync status reporting."""

    def test_get_sync_status_no_connection(self, sync_service, test_user):
        """Test sync status with no connection."""
        status = sync_service.get_sync_status(test_user.id)
        
        assert status.connection_status == "disconnected"
        assert status.total_orders_synced == 0

    def test_get_sync_status_with_connection(self, sync_service, test_user, test_connection):
        """Test sync status with active connection."""
        status = sync_service.get_sync_status(test_user.id)
        
        assert status.connection_status == "connected"
        assert status.next_auto_sync is not None

    def test_get_sync_status_expired_token(self, sync_service, test_user, test_connection, db_session):
        """Test sync status with expired token."""
        test_connection.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db_session.add(test_connection)
        db_session.commit()
        
        status = sync_service.get_sync_status(test_user.id)
        
        assert status.connection_status == "expired"


class TestSyncHistory:
    """Tests for sync history retrieval."""

    def test_get_sync_history_empty(self, sync_service, test_user):
        """Test getting history when empty."""
        logs = sync_service.get_sync_history(test_user.id)
        assert logs == []

    def test_get_sync_history_with_logs(self, sync_service, test_user):
        """Test getting history with logs."""
        # Create some logs
        for i in range(3):
            log = SwiggySyncLog(
                user_id=test_user.id,
                sync_type="orders_from_swiggy",
                direction="swiggy_to_mealmind",
                external_id=f"order_{i}",
                payload_hash=f"hash_{i}",
                status="success",
                items_synced=1,
                items_failed=0,
            )
            sync_service.db.add(log)
        sync_service.db.commit()
        
        logs = sync_service.get_sync_history(test_user.id, limit=10)
        assert len(logs) == 3
        
        # Test pagination
        logs_page1 = sync_service.get_sync_history(test_user.id, limit=2, offset=0)
        assert len(logs_page1) == 2
        
        logs_page2 = sync_service.get_sync_history(test_user.id, limit=2, offset=2)
        assert len(logs_page2) == 1


class TestDisconnect:
    """Tests for disconnecting Swiggy."""

    def test_disconnect_swiggy(self, sync_service, test_user, test_connection):
        """Test disconnecting Swiggy clears connection."""
        result = sync_service.disconnect_swiggy(test_user.id)
        
        assert result is True
        
        conn = sync_service.db.get(SwiggyConnection, test_connection.id)
        assert conn.status == "DISCONNECTED"
        assert conn.access_token == ""


class TestNutritionTracking:
    """Tests for nutrition tracking models."""

    def test_create_mealmind_food(self, sync_service, test_user, db_session):
        """Test creating a MealMind food."""
        food = MealMindFood(
            user_id=test_user.id,
            name="Paneer Biryani",
            canonical_name="paneer biryani",
            calories_per_100g=200.0,
            protein_g_per_100g=8.0,
            carbs_g_per_100g=30.0,
            fat_g_per_100g=5.0,
            fiber_g_per_100g=2.0,
            source="manual",
        )
        db_session.add(food)
        db_session.commit()
        db_session.refresh(food)
        
        assert food.id is not None
        assert food.name == "Paneer Biryani"

    def test_create_nutrition_log(self, sync_service, test_user, db_session):
        """Test creating a daily nutrition log."""
        food = MealMindFood(
            user_id=test_user.id,
            name="Test Food",
            canonical_name="test food",
            calories_per_100g=100.0,
            protein_g_per_100g=5.0,
            carbs_g_per_100g=15.0,
            fat_g_per_100g=2.0,
            source="manual",
        )
        db_session.add(food)
        db_session.commit()
        db_session.refresh(food)
        
        log = DailyNutritionLog(
            user_id=test_user.id,
            log_date=datetime.now(timezone.utc).date(),
            meal_type="lunch",
            food_id=food.id,
            quantity_g=200.0,
            calories=200.0,
            protein_g=10.0,
            carbs_g=30.0,
            fat_g=4.0,
            source="manual_entry",
        )
        db_session.add(log)
        db_session.commit()
        db_session.refresh(log)
        
        assert log.id is not None
        assert log.calories == 200.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])