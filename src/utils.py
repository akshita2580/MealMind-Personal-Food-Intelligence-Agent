"""
JSON serialization utilities for Order data.

Provides pretty-printing and parsing functions that maintain round-trip
equivalence for Order Pydantic models.
"""

import json
from typing import Any

from pydantic import ValidationError

from src.models import OrderOut


def pretty_print_order(order: OrderOut) -> str:
    """
    Serialize an Order Pydantic model to formatted JSON string.

    Args:
        order: OrderOut Pydantic model instance

    Returns:
        Formatted JSON string with 2-space indentation

    Example:
        >>> order = OrderOut(order_id="123", restaurant_name="Test", ...)
        >>> json_str = pretty_print_order(order)
        >>> print(json_str)
        {
          "order_id": "123",
          "restaurant_name": "Test",
          ...
        }
    """
    # Convert Pydantic model to dict, then to JSON with 2-space indentation
    order_dict = order.model_dump(mode="json")
    return json.dumps(order_dict, indent=2, ensure_ascii=False)


def parse_order_json(json_str: str) -> OrderOut:
    """
    Parse a JSON string into an Order Pydantic model.

    Args:
        json_str: JSON string representing an order

    Returns:
        OrderOut Pydantic model instance

    Raises:
        json.JSONDecodeError: If json_str is not valid JSON
        ValidationError: If JSON doesn't match OrderOut schema

    Example:
        >>> json_str = '{"order_id": "123", "restaurant_name": "Test", ...}'
        >>> order = parse_order_json(json_str)
        >>> print(order.order_id)
        123
    """
    # Parse JSON string to dict
    data = json.loads(json_str)
    
    # Validate and construct OrderOut from dict
    return OrderOut.model_validate(data)


def round_trip_order(order: OrderOut) -> OrderOut:
    """
    Round-trip serialization helper for testing and validation.

    Converts Order → JSON → Order to verify serialization fidelity.

    Args:
        order: Original OrderOut instance

    Returns:
        New OrderOut instance created from serialization round-trip

    Example:
        >>> original = OrderOut(order_id="123", ...)
        >>> round_tripped = round_trip_order(original)
        >>> assert original == round_tripped
    """
    json_str = pretty_print_order(order)
    return parse_order_json(json_str)
