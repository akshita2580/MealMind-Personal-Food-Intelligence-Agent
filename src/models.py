"""
Pydantic & SQLModel schemas for the Swiggy MCP server.

Three layers live here:
  1. **Database tables** – SQLModel classes persisted in SQLite.
  2. **API response schemas** – plain Pydantic models returned by FastAPI.
  3. **Shared input schemas** – used by *both* MCP tools and REST endpoints.

Cookies are intentionally absent from every model — they are only ever
accepted as a transient function argument and never touch storage.
"""

from datetime import datetime, timezone
from pydantic import BaseModel, Field, SecretStr
from sqlmodel import Field as SMField, Relationship, SQLModel


# ---------------------------------------------------------------------------
# Database tables
# ---------------------------------------------------------------------------

class Order(SQLModel, table=True):
    """A single Swiggy order — the central entity."""

    __tablename__ = "orders"

    order_id: str = SMField(primary_key=True)
    restaurant_id: str = SMField(default="", index=True)
    restaurant_name: str = SMField(default="", index=True)  # indexed for query performance
    restaurant_locality: str = ""
    restaurant_city: str = ""
    restaurant_cuisines: str = ""          # comma-separated for simplicity
    order_time: datetime | None = SMField(default=None, index=True)  # indexed for date range queries
    order_total: float = 0.0
    order_status: str = "Delivered"
    payment_method: str = ""
    delivery_address: str = ""
    order_discount: float = 0.0
    delivery_charge: float = 0.0
    gst: float = 0.0
    raw_json: str = ""                     # full original payload
    created_at: datetime = SMField(default_factory=lambda: datetime.now(timezone.utc))  # timestamp when record was created

    items: list["OrderItem"] = Relationship(back_populates="order")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @property
    def cuisine_list(self) -> list[str]:
        """Return cuisines as a Python list."""
        if not self.restaurant_cuisines:
            return []
        return [c.strip() for c in self.restaurant_cuisines.split(",") if c.strip()]


class OrderItem(SQLModel, table=True):
    """A single line-item inside a Swiggy order."""

    __tablename__ = "order_items"

    id: int | None = SMField(default=None, primary_key=True)
    order_id: str = SMField(index=True, foreign_key="orders.order_id")
    item_id: str = ""
    name: str = ""
    quantity: int = 1
    price: float = 0.0
    is_veg: bool = True

    order: Order | None = Relationship(back_populates="items")


class OrderCuisine(SQLModel, table=True):
    """A cuisine tag associated with an order (normalized many-to-many)."""

    __tablename__ = "order_cuisines"

    id: int | None = SMField(default=None, primary_key=True)
    order_id: str = SMField(index=True, foreign_key="orders.order_id")
    cuisine_name: str = SMField(index=True)


class User(SQLModel, table=True):
    """A FoodIQ user, mapped to a Telegram account."""

    __tablename__ = "users"

    id: int | None = SMField(default=None, primary_key=True)
    telegram_id: str = SMField(unique=True, index=True)
    created_at: datetime = SMField(default_factory=lambda: datetime.now(timezone.utc))


class SwiggyConnection(SQLModel, table=True):
    """An active Swiggy OAuth connection for a user."""

    __tablename__ = "swiggy_connections"

    id: int | None = SMField(default=None, primary_key=True)
    user_id: int = SMField(foreign_key="users.id", unique=True)
    status: str = "CONNECTED"
    access_token: str = ""  # Stored encrypted at rest
    expires_at: datetime | None = None
    created_at: datetime = SMField(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = SMField(default_factory=lambda: datetime.now(timezone.utc))


class OAuthState(SQLModel, table=True):
    """Temporary state for securing the OAuth flow against CSRF and tracking PKCE.
    
    IMPORTANT: All datetime fields are stored as naive UTC datetimes in SQLite.
    When creating: use datetime.now(timezone.utc).replace(tzinfo=None)
    When reading: treat as UTC and add timezone if needed.
    """

    __tablename__ = "oauth_states"

    state: str = SMField(primary_key=True)
    telegram_id: str = SMField(index=True)
    code_verifier: str = ""
    expires_at: datetime  # Naive UTC datetime
    created_at: datetime = SMField(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))



# ---------------------------------------------------------------------------
# API / MCP shared input schemas
# ---------------------------------------------------------------------------

class SyncOrdersRequest(BaseModel):
    """Input for sync_orders (MCP tool & POST /sync)."""

    cookies: SecretStr = Field(..., description="Swiggy session cookies string")
    max_orders: int = Field(default=1000, ge=1, le=5000, description="Maximum orders to fetch")
    max_pages: int = Field(default=50, ge=1, le=200, description="Maximum API pages to fetch")


class GetOrdersRequest(BaseModel):
    """Input for get_orders."""

    start_date: str | None = Field(default=None, description="YYYY-MM-DD")
    end_date: str | None = Field(default=None, description="YYYY-MM-DD")
    restaurant_name: str | None = None
    limit: int = Field(default=50, ge=1, le=500)


class GetRestaurantsRequest(BaseModel):
    """Input for get_restaurants."""

    start_date: str | None = None
    end_date: str | None = None
    min_orders: int = Field(default=1, ge=1)


class GetAnalyticsRequest(BaseModel):
    """Input for get_analytics."""

    start_date: str | None = None
    end_date: str | None = None
    analysis_type: str = Field(
        default="summary",
        description="One of: summary, spending, timing, restaurants, cuisines",
    )


class SearchOrdersRequest(BaseModel):
    """Input for search_orders."""

    query: str = Field(..., min_length=1, description="Search term")
    limit: int = Field(default=20, ge=1, le=200)


# ---------------------------------------------------------------------------
# API response schemas
# ---------------------------------------------------------------------------

class ItemOut(BaseModel):
    """Flat representation of an order item for API consumers."""

    item_id: str
    name: str
    quantity: int
    price: float
    is_veg: bool

    model_config = {"from_attributes": True}


class OrderOut(BaseModel):
    """Flat representation of an order for API consumers."""

    order_id: str
    restaurant_name: str
    restaurant_locality: str
    restaurant_city: str
    cuisines: list[str]
    order_time: str | None
    order_total: float
    order_status: str
    payment_method: str
    items: list[ItemOut] = []

    model_config = {"from_attributes": True}


class RestaurantStats(BaseModel):
    name: str
    order_count: int
    total_spent: float
    avg_order_value: float
    cuisines: list[str]
    localities: list[str]
    first_order: str
    last_order: str


class SyncResult(BaseModel):
    new_orders_fetched: int
    total_orders_in_db: int
    date_coverage: str


class AnalyticsSummary(BaseModel):
    total_orders: int = 0
    total_spent: float = 0.0
    average_order_value: float = 0.0
    first_order: str | None = None
    last_order: str | None = None


class MonthlyTrend(BaseModel):
    month: str
    orders: int
    total_spent: float
    avg_order: float


class PeakHour(BaseModel):
    hour: str
    orders: int


class DayDistribution(BaseModel):
    day: str
    orders: int


class CuisineStats(BaseModel):
    cuisine: str
    orders: int
    total_spent: float
    avg_order: float
    percentage: float


class AnalyticsResult(BaseModel):
    """Combined analytics result with optional variant fields."""
    summary: AnalyticsSummary
    monthly_trends: list[MonthlyTrend] | None = None
    peak_hours: list[PeakHour] | None = None
    day_distribution: list[DayDistribution] | None = None
    top_restaurants: list[RestaurantStats] | None = None
    top_cuisines: list[CuisineStats] | None = None


# ---------------------------------------------------------------------------
# Union type for analytics responses (Requirement 10.5)
# ---------------------------------------------------------------------------

class SummaryAnalyticsResponse(BaseModel):
    """Analytics response for 'summary' analysis type."""
    analysis_type: str = "summary"
    summary: AnalyticsSummary


class SpendingAnalyticsResponse(BaseModel):
    """Analytics response for 'spending' analysis type."""
    analysis_type: str = "spending"
    summary: AnalyticsSummary
    monthly_trends: list[MonthlyTrend]


class TimingAnalyticsResponse(BaseModel):
    """Analytics response for 'timing' analysis type."""
    analysis_type: str = "timing"
    summary: AnalyticsSummary
    peak_hours: list[PeakHour]
    day_distribution: list[DayDistribution]


class RestaurantsAnalyticsResponse(BaseModel):
    """Analytics response for 'restaurants' analysis type."""
    analysis_type: str = "restaurants"
    summary: AnalyticsSummary
    top_restaurants: list[RestaurantStats]


class CuisinesAnalyticsResponse(BaseModel):
    """Analytics response for 'cuisines' analysis type."""
    analysis_type: str = "cuisines"
    summary: AnalyticsSummary
    top_cuisines: list[CuisineStats]


# Union type supporting multiple analysis variants (Requirement 10.5)
AnalyticsResponse = (
    SummaryAnalyticsResponse 
    | SpendingAnalyticsResponse 
    | TimingAnalyticsResponse 
    | RestaurantsAnalyticsResponse 
    | CuisinesAnalyticsResponse
)


# ---------------------------------------------------------------------------
# Food Intelligence Insight Models (Milestone 1)
# ---------------------------------------------------------------------------

class InsightResponse(BaseModel):
    """
    Single food intelligence insight response.
    
    Returned by the Insight Engine to provide personalized,
    actionable insights about food ordering behavior.
    """
    
    type: str = Field(..., description="Type of insight (enum value)")
    severity: str = Field(..., description="Severity level: INFO, SUCCESS, WARNING, ALERT")
    title: str = Field(..., description="Short summary (< 60 chars)")
    message: str = Field(..., description="Detailed explanation")
    value: float | int | str | None = Field(None, description="Primary metric value")
    unit: str | None = Field(None, description="Unit of measurement (%, orders, ₹, etc.)")
    period: str | None = Field(None, description="Time period (monthly, weekly, all-time)")
    supporting_data: dict = Field(
        default_factory=dict,
        description="Additional context and metadata"
    )
    
    model_config = {"from_attributes": True}


class InsightsListResponse(BaseModel):
    """
    Response containing multiple food intelligence insights.
    
    Returned by GET /api/insights endpoint and get_food_insights MCP tool.
    """
    
    period: dict[str, str | None] = Field(
        ...,
        description="Date range for the insights"
    )
    total_orders: int = Field(..., description="Total orders analyzed")
    insights: list[InsightResponse] = Field(..., description="List of generated insights")
    generated_at: str = Field(..., description="Timestamp when insights were generated")
    
    model_config = {"from_attributes": True}
