"""Database engine and session helpers for SQLite and PostgreSQL.

Set ``DATABASE_URL`` to a SQLAlchemy URL. PostgreSQL URLs may use either
``postgresql://`` or ``postgres://``; they are normalized to psycopg 3.
Tables are created explicitly by the application startup hook.
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
    Return a cached SQLAlchemy engine pointing at the local database file or URL.
    
    Reads a database path or SQLAlchemy URL from ``DATABASE_URL``.
    The SQLite file remains the development fallback for older deployments.
    """
    # Read from environment variable with default
    db_path = os.environ.get("DATABASE_URL", "data/swiggy.db")
    
    # Normalize common hosted PostgreSQL URL schemes for the psycopg 3 driver.
    if "://" in db_path:
        if db_path.startswith("postgres://"):
            url = "postgresql+psycopg://" + db_path[len("postgres://"):]
        elif db_path.startswith("postgresql://"):
            url = "postgresql+psycopg://" + db_path[len("postgresql://"):]
        else:
            url = db_path
    else:
        # If it's a relative path, resolve it relative to project root
        path_obj = Path(db_path)
        if not path_obj.is_absolute():
            path_obj = _PROJECT_ROOT / path_obj
        
        # Ensure parent directory exists
        path_obj.parent.mkdir(parents=True, exist_ok=True)
        
        url = f"sqlite:///{path_obj}"
    
    if url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
    elif url.startswith("postgresql+"):
        # Existing model timestamps are naive UTC. Keep PostgreSQL's session
        # timezone fixed so aware upstream timestamps are stored consistently.
        connect_args = {"options": "-c timezone=UTC"}
    else:
        connect_args = {}
    return create_engine(
        url,
        echo=False,
        connect_args=connect_args,
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
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
