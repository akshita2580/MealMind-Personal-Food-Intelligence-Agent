"""
Pytest configuration for MealMind tests.
"""

import pytest
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    import asyncio
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# Configure asyncio for pytest
def pytest_configure(config):
    config.addinivalue_line("markers", "asyncio: mark test as async")


def pytest_collection_modifyitems(config, items):
    """Automatically mark async tests."""
    for item in items:
        if "asyncio" in item.keywords or "async" in str(item.fspath):
            item.add_marker(pytest.mark.asyncio)