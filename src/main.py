"""
Application entry-point for the Swiggy MCP server (Python edition).

Usage
-----
    # Run the FastAPI HTTP server (includes MCP over SSE at /mcp):
    python -m src.main

    # Run the MCP server over stdio (for Claude Desktop / Cursor):
    python -m src.main --stdio

    # Or via uvicorn directly:
    uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from dotenv import load_dotenv
from fastapi import FastAPI

from .api import router as api_router
from .database import create_db_and_tables
from .error_handlers import register_error_handlers
from .mcp_server import mcp

# ---------------------------------------------------------------------------
# Load environment variables from .env file (requirement 13.3)
# ---------------------------------------------------------------------------
try:
    load_dotenv()
except Exception:
    # .env file is optional - continue without it
    pass

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifecycle hook for FastAPI."""
    # Ensure database and tables exist before handling requests
    create_db_and_tables()
    yield
    # Any teardown code would go here


app = FastAPI(
    title="Swiggy Orders API",
    description=(
        "REST + MCP server for querying your Swiggy food-delivery history. "
        "Sync orders, get analytics, search by restaurant / cuisine / location."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# Register custom error handlers (requirement 8.8, 10.6, 12.4, 12.6)
register_error_handlers(app)

# Mount the REST API router
app.include_router(api_router)

# Mount FastMCP as a sub-application (serves MCP over SSE at /mcp)
app.mount("/mcp", mcp.http_app())


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli() -> None:
    """CLI entry point for the Swiggy MCP server."""
    parser = argparse.ArgumentParser(description="Swiggy MCP Server (Python)")
    parser.add_argument(
        "--stdio",
        action="store_true",
        help="Run the MCP server over stdio instead of HTTP (for Claude Desktop).",
    )
    parser.add_argument("--host", default="0.0.0.0", help="HTTP host (default 0.0.0.0)")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("PORT", "8000")),
        help="HTTP port (default from PORT env var or 8000)"
    )
    args = parser.parse_args()

    if args.stdio:
        # Before entering stdio mode, ensure DB is ready
        create_db_and_tables()
        # Run MCP over stdio — blocks until the client disconnects
        mcp.run(transport="stdio")
    else:
        import uvicorn
        
        # We pass the app object directly to uvicorn to avoid import string
        # resolution issues when installed via pip.
        uvicorn.run(
            app,
            host=args.host,
            port=args.port,
            log_level="info",
        )


if __name__ == "__main__":
    _cli()
