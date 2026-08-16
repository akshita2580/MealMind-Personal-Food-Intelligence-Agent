"""
Service layer for Swiggy MCP Server.

This package contains business logic services that sit between
the repository layer and the API/MCP interfaces.
"""

from .insight_engine import (
    InsightEngine,
    Insight,
    InsightType,
    InsightSeverity,
    build_food_insights_response,
    generate_food_insights,
    resolve_insight_period,
)

__all__ = [
    "InsightEngine",
    "Insight",
    "InsightType",
    "InsightSeverity",
    "build_food_insights_response",
    "generate_food_insights",
    "resolve_insight_period",
]
