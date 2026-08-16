"""
SQLite database engine and session helpers.

The DB file lives at ``data/swiggy.db`` relative to the project root.
Tables are created explicitly by the application startup hook — never
as an import side-effect.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Any, Generator

from sqlmodel import Session, SQLModel, create_engine

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DATA_DIR = _PROJECT_ROOT / "data"


# ---------------------------------------------------------------------------
# Engine (lazy singleton)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_engine() -> Any:
    """
    Return a cached SQLAlchemy engine pointing at the local SQLite file.
    
    Reads database path from DATABASE_URL environment variable.
    Defaults to 'data/swiggy.db' if not set.
    """
    # Read from environment variable with default
    db_path = os.environ.get("DATABASE_URL", "data/swiggy.db")
    
    # If it's a relative path, resolve it relative to project root
    if not db_path.startswith("sqlite:///"):
        path_obj = Path(db_path)
        if not path_obj.is_absolute():
            path_obj = _PROJECT_ROOT / path_obj
        
        # Ensure parent directory exists
        path_obj.parent.mkdir(parents=True, exist_ok=True)
        
        url = f"sqlite:///{path_obj}"
    else:
        # Already a full SQLite URL
        url = db_path
    
    return create_engine(
        url,
        echo=False,
        connect_args={"check_same_thread": False},
    )


# ---------------------------------------------------------------------------
# Table bootstrap
# ---------------------------------------------------------------------------

def create_db_and_tables() -> None:
    """Idempotently create every table declared via SQLModel metadata."""
    # Importing models here ensures their table metadata is registered
    # before we call create_all — avoids import-order surprises.
    from . import models as _models  # noqa: F401

    SQLModel.metadata.create_all(get_engine())


# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------

@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Yield a transactional SQLModel session (auto-closed on exit)."""
    session = Session(get_engine())
    try:
        yield session
    finally:
        session.close()
