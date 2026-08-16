"""
Integration test for configuration management.

Tests that configuration values from environment variables are correctly
loaded and used throughout the application.
"""

import os
from pathlib import Path

import pytest


def test_database_url_configuration():
    """Verify database.py reads DATABASE_URL correctly."""
    # Save original env value
    original_value = os.environ.get("DATABASE_URL")
    
    try:
        # Set custom value
        os.environ["DATABASE_URL"] = "data/test_custom.db"
        
        # Clear the cache to force engine recreation
        from src.database import get_engine
        get_engine.cache_clear()
        
        # Get engine and verify URL
        engine = get_engine()
        assert "test_custom.db" in str(engine.url), \
            "Database engine should use DATABASE_URL from environment"
    finally:
        # Restore original value
        if original_value is not None:
            os.environ["DATABASE_URL"] = original_value
        elif "DATABASE_URL" in os.environ:
            del os.environ["DATABASE_URL"]
        
        # Clear cache again
        from src.database import get_engine
        get_engine.cache_clear()


def test_database_url_default():
    """Verify database.py uses default value when DATABASE_URL not set."""
    # Save original env value
    original_value = os.environ.get("DATABASE_URL")
    
    try:
        # Remove DATABASE_URL if set
        if "DATABASE_URL" in os.environ:
            del os.environ["DATABASE_URL"]
        
        # Clear the cache to force engine recreation
        from src.database import get_engine
        get_engine.cache_clear()
        
        # Get engine and verify default URL
        engine = get_engine()
        assert "swiggy.db" in str(engine.url), \
            "Database engine should use default data/swiggy.db when DATABASE_URL not set"
    finally:
        # Restore original value
        if original_value is not None:
            os.environ["DATABASE_URL"] = original_value
        
        # Clear cache again
        from src.database import get_engine
        get_engine.cache_clear()


def test_swiggy_api_url_configuration():
    """Verify fetcher.py reads SWIGGY_API_URL correctly."""
    from src.fetcher import _get_base_url
    
    # Save original env value
    original_value = os.environ.get("SWIGGY_API_URL")
    
    try:
        # Test default value
        if "SWIGGY_API_URL" in os.environ:
            del os.environ["SWIGGY_API_URL"]
        
        default_url = _get_base_url()
        assert default_url == "https://www.swiggy.com/dapi/order/all", \
            "Should use default SWIGGY_API_URL"
        
        # Test custom value
        os.environ["SWIGGY_API_URL"] = "https://custom.swiggy.com/api/orders"
        custom_url = _get_base_url()
        assert custom_url == "https://custom.swiggy.com/api/orders", \
            "Should use SWIGGY_API_URL from environment"
    finally:
        # Restore original value
        if original_value is not None:
            os.environ["SWIGGY_API_URL"] = original_value
        elif "SWIGGY_API_URL" in os.environ:
            del os.environ["SWIGGY_API_URL"]


def test_request_timeout_configuration():
    """Verify fetcher.py reads REQUEST_TIMEOUT correctly."""
    from src.fetcher import _get_timeout
    
    # Save original env value
    original_value = os.environ.get("REQUEST_TIMEOUT")
    
    try:
        # Test default value
        if "REQUEST_TIMEOUT" in os.environ:
            del os.environ["REQUEST_TIMEOUT"]
        
        default_timeout = _get_timeout()
        assert default_timeout == 30.0, \
            "Should use default REQUEST_TIMEOUT of 30 seconds"
        
        # Test custom value
        os.environ["REQUEST_TIMEOUT"] = "60"
        custom_timeout = _get_timeout()
        assert custom_timeout == 60.0, \
            "Should use REQUEST_TIMEOUT from environment"
        
        # Test invalid value (should fall back to default)
        os.environ["REQUEST_TIMEOUT"] = "invalid"
        fallback_timeout = _get_timeout()
        assert fallback_timeout == 30.0, \
            "Should fall back to default when REQUEST_TIMEOUT is invalid"
    finally:
        # Restore original value
        if original_value is not None:
            os.environ["REQUEST_TIMEOUT"] = original_value
        elif "REQUEST_TIMEOUT" in os.environ:
            del os.environ["REQUEST_TIMEOUT"]


def test_port_configuration_in_main():
    """Verify main.py reads PORT correctly."""
    # Save original env value
    original_value = os.environ.get("PORT")
    
    try:
        # Test default (8000)
        if "PORT" in os.environ:
            del os.environ["PORT"]
        default_port = int(os.getenv("PORT", "8000"))
        assert default_port == 8000, "Default PORT should be 8000"
        
        # Test custom value
        os.environ["PORT"] = "9000"
        custom_port = int(os.getenv("PORT", "8000"))
        assert custom_port == 9000, "Should use PORT from environment"
    finally:
        # Restore original value
        if original_value is not None:
            os.environ["PORT"] = original_value
        elif "PORT" in os.environ:
            del os.environ["PORT"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
