import os
import pytest
from pathlib import Path
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine
from src.database import get_engine

TEST_DB_PATH = Path("data/test_global.db")

# Ensure data directory exists
TEST_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# Remove existing test DB if any before ANY imports happen
if TEST_DB_PATH.exists():
    try:
        TEST_DB_PATH.unlink()
    except OSError:
        pass

# Force all tests to use an isolated file-based database by default
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH.absolute()}"

@pytest.fixture(autouse=True, scope="session")
def isolate_database():
    """Ensure tests run against an isolated test database, never production."""
    os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH.absolute()}"
    
    # Clear any cached engines in src.database
    get_engine.cache_clear()
    
    # Provide the isolated engine
    engine = get_engine()
    
    SQLModel.metadata.create_all(engine)
    
    yield engine
    
    engine.dispose()
    
    # Clean up after all tests
    if TEST_DB_PATH.exists():
        try:
            TEST_DB_PATH.unlink()
        except OSError:
            pass
