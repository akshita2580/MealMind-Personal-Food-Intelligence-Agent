"""
FastAPI error handlers for REST API layer.

Implements consistent error responses with proper HTTP status codes:
- HTTP 400 for invalid requests
- HTTP 422 for Pydantic validation errors
- HTTP 502 for upstream API errors
- HTTP 401 for authentication errors

All error responses:
- Return structured JSON with error details
- Log errors to stderr
- Never include cookie values in logs or responses (requirement 2.5, 12.6)
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from .fetcher import AuthenticationError, SwiggyAPIError

# Configure logging to stderr (requirement 12.6)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Error response models
# ---------------------------------------------------------------------------

def _create_error_response(
    status_code: int,
    error_type: str,
    message: str,
    details: Any = None
) -> JSONResponse:
    """
    Create a standardized JSON error response.
    
    Args:
        status_code: HTTP status code
        error_type: Error type identifier (e.g., "validation_error", "api_error")
        message: Human-readable error message
        details: Optional additional error details
    
    Returns:
        JSONResponse with standardized error format
    """
    content = {
        "error": error_type,
        "message": message,
    }
    
    if details is not None:
        content["details"] = details
    
    return JSONResponse(
        status_code=status_code,
        content=content,
    )


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------

async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError
) -> JSONResponse:
    """
    Handle Pydantic validation errors (HTTP 422).
    
    Implements requirement 10.6: Return 422 with validation error details.
    Implements requirement 12.6: Log errors without cookie values.
    """
    # Extract validation error details
    errors = exc.errors()
    
    # Log error without request body (which might contain cookies)
    logger.error(
        "Validation error on %s %s: %d validation errors",
        request.method,
        request.url.path,
        len(errors),
    )
    
    # Format validation errors for response
    formatted_errors = []
    for error in errors:
        formatted_errors.append({
            "loc": error.get("loc", []),
            "msg": error.get("msg", ""),
            "type": error.get("type", ""),
        })
    
    return _create_error_response(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        error_type="validation_error",
        message="Request validation failed",
        details=formatted_errors,
    )


async def pydantic_validation_exception_handler(
    request: Request,
    exc: ValidationError
) -> JSONResponse:
    """
    Handle Pydantic ValidationError raised in application code (HTTP 422).
    
    This catches ValidationError exceptions that are raised outside of
    FastAPI's automatic request validation (e.g., in repository or business logic).
    """
    errors = exc.errors()
    
    logger.error(
        "Pydantic validation error on %s %s: %d validation errors",
        request.method,
        request.url.path,
        len(errors),
    )
    
    formatted_errors = []
    for error in errors:
        formatted_errors.append({
            "loc": error.get("loc", []),
            "msg": error.get("msg", ""),
            "type": error.get("type", ""),
        })
    
    return _create_error_response(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        error_type="validation_error",
        message="Data validation failed",
        details=formatted_errors,
    )


async def authentication_exception_handler(
    request: Request,
    exc: AuthenticationError
) -> JSONResponse:
    """
    Handle authentication errors (HTTP 401).
    
    Implements requirement 12.2: Clear error for invalid/expired cookies.
    Implements requirement 12.6: Log errors without cookie values.
    """
    # Log without including request body (which contains cookies)
    logger.error(
        "Authentication error on %s %s: %s",
        request.method,
        request.url.path,
        exc.message,
    )
    
    return _create_error_response(
        status_code=status.HTTP_401_UNAUTHORIZED,
        error_type="authentication_error",
        message=exc.message,
    )


async def swiggy_api_exception_handler(
    request: Request,
    exc: SwiggyAPIError
) -> JSONResponse:
    """
    Handle Swiggy API errors (HTTP 502 Bad Gateway).
    
    Implements requirement 12.1: Clear error for upstream API failures.
    Implements requirement 12.6: Log errors without cookie values.
    """
    # Log without including request body (which might contain cookies)
    logger.error(
        "Swiggy API error on %s %s: [%d] %s",
        request.method,
        request.url.path,
        exc.status_code,
        exc.message,
    )
    
    return _create_error_response(
        status_code=status.HTTP_502_BAD_GATEWAY,
        error_type="upstream_api_error",
        message=f"Failed to fetch from Swiggy API: {exc.message}",
        details={
            "upstream_status": exc.status_code,
        }
    )


async def value_error_exception_handler(
    request: Request,
    exc: ValueError
) -> JSONResponse:
    """
    Handle ValueError exceptions (HTTP 400 Bad Request).
    
    Implements requirement 12.4: Return HTTP 400 for invalid requests.
    """
    logger.error(
        "Value error on %s %s: %s",
        request.method,
        request.url.path,
        str(exc),
    )
    
    return _create_error_response(
        status_code=status.HTTP_400_BAD_REQUEST,
        error_type="invalid_request",
        message=str(exc),
    )


async def generic_exception_handler(
    request: Request,
    exc: Exception
) -> JSONResponse:
    """
    Handle unexpected exceptions (HTTP 500 Internal Server Error).
    
    Implements requirement 12.6: Log errors without cookie values.
    """
    # Log full exception details for debugging (without request body)
    logger.exception(
        "Unexpected error on %s %s: %s: %s",
        request.method,
        request.url.path,
        type(exc).__name__,
        str(exc),
    )
    
    return _create_error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        error_type="internal_error",
        message="An unexpected error occurred. Please try again later.",
    )


# ---------------------------------------------------------------------------
# Handler registration helper
# ---------------------------------------------------------------------------

def register_error_handlers(app: Any) -> None:
    """
    Register all custom error handlers with a FastAPI app.
    
    This should be called during application setup in main.py.
    
    Args:
        app: FastAPI application instance
    """
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(ValidationError, pydantic_validation_exception_handler)
    app.add_exception_handler(AuthenticationError, authentication_exception_handler)
    app.add_exception_handler(SwiggyAPIError, swiggy_api_exception_handler)
    app.add_exception_handler(ValueError, value_error_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
