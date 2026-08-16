"""
Unit tests for JSON serialization utilities.

Tests pretty_print_order, parse_order_json, and round-trip property.
"""

import json
import pytest
from pydantic import ValidationError

from src.models import OrderOut, ItemOut
from src.utils import pretty_print_order, parse_order_json, round_trip_order


def test_pretty_print_order_formatting():
    """Test that pretty_print_order produces 2-space indented JSON."""
    order = OrderOut(
        order_id="ORD123",
        restaurant_name="Test Restaurant",
        restaurant_locality="Test Locality",
        restaurant_city="Test City",
        cuisines=["Italian", "Pizza"],
        order_time="2024-01-15T18:30:00",
        order_total=599.50,
        order_status="Delivered",
        payment_method="UPI",
        items=[]
    )
    
    json_str = pretty_print_order(order)
    
    # Verify it's valid JSON
    parsed = json.loads(json_str)
    assert parsed["order_id"] == "ORD123"
    
    # Verify 2-space indentation by checking the string format
    lines = json_str.split("\n")
    assert len(lines) > 1  # Multi-line output
    # Check that second line has 2-space indent
    assert lines[1].startswith("  ")


def test_pretty_print_order_with_items():
    """Test pretty printing with order items included."""
    order = OrderOut(
        order_id="ORD456",
        restaurant_name="Pizza Palace",
        restaurant_locality="Downtown",
        restaurant_city="Mumbai",
        cuisines=["Italian"],
        order_time="2024-01-16T19:00:00",
        order_total=899.00,
        order_status="Delivered",
        payment_method="Card",
        items=[
            ItemOut(
                item_id="ITEM1",
                name="Margherita Pizza",
                quantity=2,
                price=450.00,
                is_veg=True
            )
        ]
    )
    
    json_str = pretty_print_order(order)
    parsed = json.loads(json_str)
    
    assert len(parsed["items"]) == 1
    assert parsed["items"][0]["name"] == "Margherita Pizza"


def test_parse_order_json_valid():
    """Test parsing valid Order JSON string."""
    json_str = """
    {
      "order_id": "ORD789",
      "restaurant_name": "Burger King",
      "restaurant_locality": "Andheri",
      "restaurant_city": "Mumbai",
      "cuisines": ["Fast Food", "Burgers"],
      "order_time": "2024-01-17T20:15:00",
      "order_total": 399.00,
      "order_status": "Delivered",
      "payment_method": "Cash",
      "items": []
    }
    """
    
    order = parse_order_json(json_str)
    
    assert order.order_id == "ORD789"
    assert order.restaurant_name == "Burger King"
    assert order.order_total == 399.00
    assert order.cuisines == ["Fast Food", "Burgers"]


def test_parse_order_json_invalid_json():
    """Test that invalid JSON raises JSONDecodeError."""
    invalid_json = "{not valid json"
    
    with pytest.raises(json.JSONDecodeError):
        parse_order_json(invalid_json)


def test_parse_order_json_missing_required_fields():
    """Test that JSON missing required fields raises ValidationError."""
    # Missing required fields like order_id, restaurant_name, etc.
    incomplete_json = '{"order_id": "123"}'
    
    with pytest.raises(ValidationError):
        parse_order_json(incomplete_json)


def test_round_trip_order_simple():
    """Test round-trip serialization preserves Order data."""
    original = OrderOut(
        order_id="RTT001",
        restaurant_name="Sushi Bar",
        restaurant_locality="Bandra",
        restaurant_city="Mumbai",
        cuisines=["Japanese", "Sushi"],
        order_time="2024-01-18T21:00:00",
        order_total=1299.50,
        order_status="Delivered",
        payment_method="UPI",
        items=[]
    )
    
    round_tripped = round_trip_order(original)
    
    # Verify all fields match
    assert round_tripped.order_id == original.order_id
    assert round_tripped.restaurant_name == original.restaurant_name
    assert round_tripped.restaurant_locality == original.restaurant_locality
    assert round_tripped.restaurant_city == original.restaurant_city
    assert round_tripped.cuisines == original.cuisines
    assert round_tripped.order_time == original.order_time
    assert round_tripped.order_total == original.order_total
    assert round_tripped.order_status == original.order_status
    assert round_tripped.payment_method == original.payment_method
    assert round_tripped.items == original.items


def test_round_trip_order_with_items():
    """Test round-trip with complex order including items."""
    original = OrderOut(
        order_id="RTT002",
        restaurant_name="Biryani House",
        restaurant_locality="Powai",
        restaurant_city="Mumbai",
        cuisines=["Indian", "Biryani"],
        order_time="2024-01-19T22:30:00",
        order_total=699.00,
        order_status="Delivered",
        payment_method="Card",
        items=[
            ItemOut(
                item_id="ITEM_B1",
                name="Chicken Biryani",
                quantity=1,
                price=399.00,
                is_veg=False
            ),
            ItemOut(
                item_id="ITEM_R1",
                name="Raita",
                quantity=2,
                price=150.00,
                is_veg=True
            )
        ]
    )
    
    round_tripped = round_trip_order(original)
    
    # Verify items are preserved
    assert len(round_tripped.items) == 2
    assert round_tripped.items[0].name == "Chicken Biryani"
    assert round_tripped.items[0].quantity == 1
    assert round_tripped.items[1].name == "Raita"
    assert round_tripped.items[1].quantity == 2


def test_round_trip_property_equivalence():
    """Test that multiple round-trips produce equivalent results."""
    original = OrderOut(
        order_id="EQUIV001",
        restaurant_name="Test",
        restaurant_locality="Test Loc",
        restaurant_city="Test City",
        cuisines=["Test Cuisine"],
        order_time="2024-01-20T10:00:00",
        order_total=500.00,
        order_status="Delivered",
        payment_method="UPI",
        items=[]
    )
    
    # First round-trip
    first_trip = round_trip_order(original)
    
    # Second round-trip
    second_trip = round_trip_order(first_trip)
    
    # All three should be equivalent
    assert original.model_dump() == first_trip.model_dump()
    assert first_trip.model_dump() == second_trip.model_dump()


def test_pretty_print_handles_unicode():
    """Test that pretty_print_order handles Unicode characters correctly."""
    order = OrderOut(
        order_id="UNI001",
        restaurant_name="हिंदी Restaurant 中文",
        restaurant_locality="मुंबई",
        restaurant_city="Mumbai",
        cuisines=["Indian", "中国菜"],
        order_time="2024-01-21T12:00:00",
        order_total=750.00,
        order_status="Delivered",
        payment_method="UPI",
        items=[]
    )
    
    json_str = pretty_print_order(order)
    
    # Verify Unicode is preserved
    assert "हिंदी Restaurant 中文" in json_str
    assert "मुंबई" in json_str
    
    # Verify it can be parsed back
    parsed = parse_order_json(json_str)
    assert parsed.restaurant_name == "हिंदी Restaurant 中文"
    assert parsed.restaurant_locality == "मुंबई"


def test_pretty_print_handles_null_order_time():
    """Test that null order_time is handled correctly."""
    order = OrderOut(
        order_id="NULL001",
        restaurant_name="Test",
        restaurant_locality="Test Loc",
        restaurant_city="Test City",
        cuisines=["Test"],
        order_time=None,  # Null order time
        order_total=500.00,
        order_status="Delivered",
        payment_method="UPI",
        items=[]
    )
    
    json_str = pretty_print_order(order)
    parsed = parse_order_json(json_str)
    
    assert parsed.order_time is None
