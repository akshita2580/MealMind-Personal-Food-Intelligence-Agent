# 🍽️ Swiggy MCP Server — Python Edition

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com/)
[![FastMCP](https://img.shields.io/badge/FastMCP-2.0+-orange.svg)](https://github.com/jlowin/fastmcp)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Transform your Swiggy food delivery history into deterministic, explainable food insights.**

A production-ready Python implementation featuring enterprise-grade security, dual API interfaces, and comprehensive analytics capabilities.

## ✨ Key Features

- 🔒 **Security-First**: Zero-persistence cookie design — credentials never touch disk
- 🐍 **Modern Python Stack**: FastAPI, FastMCP, SQLModel, Pydantic, httpx
- 🤖 **Dual APIs**: MCP tools for AI assistants + REST endpoints for web clients
- 🧠 **Food Intelligence**: AI-powered insights about spending, behavior, loyalty, and preferences
- 📊 **Rich Analytics**: Spending trends, timing patterns, cuisine preferences, restaurant insights
- 💾 **Optimized Storage**: SQLite with normalized schema and strategic indexing
- 🎯 **Type-Safe**: Full Pydantic validation and type hints throughout
- 🔄 **Robust Sync**: Exponential backoff, retry logic, pagination handling
- 📝 **Production-Ready**: Comprehensive error handling, logging, configuration management

---

## 🎯 What Can You Do?

### 💬 Ask Your AI Assistant

With MCP integration in Claude Desktop or Cursor:

```
You: "Sync my Swiggy orders from the last 6 months"
Assistant: [syncs 500+ orders in seconds]

You: "Give me insights about my food ordering habits"
Assistant: [analyzes patterns and shows personalized recommendations]

You: "Which restaurants do I order from most often?"
Assistant: [shows top 10 restaurants with order counts and spending]

You: "Show me my monthly food spending trends for 2024"
Assistant: [displays spending analytics with monthly breakdowns]

You: "What are my peak ordering hours?"
Assistant: [reveals timing patterns and day distribution]

You: "Search for all orders with biryani"
Assistant: [finds matching orders across restaurant names and item names]
```

### 🌐 Use the REST API

Build custom dashboards, mobile apps, or integrations:

```bash
# Sync orders
curl -X POST http://localhost:8000/api/sync \
  -H "Content-Type: application/json" \
  -d '{"cookies": "...", "max_orders": 1000}'

# Get analytics
curl "http://localhost:8000/api/analytics?analysis_type=spending"

# Search orders
curl "http://localhost:8000/api/search?query=pizza&limit=20"
```

### 🔐 Security Guarantee

**Your session cookies are NEVER stored to disk, database, logs, or cache.**

They're accepted as runtime arguments only when syncing orders, then immediately discarded. This **zero-persistence design** eliminates credential leak risks entirely — even in crash scenarios or error conditions.

✅ No cookie fields in database tables  
✅ No cookie values in error logs  
✅ No cookie persistence in configuration files  
✅ SecretStr masking in all request models  
✅ Custom error handlers prevent cookie exposure  

---

## 📋 Table of Contents

- [Quick Start](#-quick-start)
- [Installation](#installation)
- [Running the Server](#running-the-server)
- [MCP Integration](#-mcp-integration)
- [Available MCP Tools](#-available-mcp-tools)
- [REST API Endpoints](#-rest-api-endpoints)
- [Getting Swiggy Cookies](#-how-to-get-your-swiggy-session-cookies)
- [Configuration](#️-configuration)
- [Project Structure](#project-structure)
- [Database Schema](#-database-schema)
- [Development](#-development)
- [Testing](#-testing)
- [Troubleshooting](#-troubleshooting)
- [Performance & Limitations](#-performance--limitations)
- [Contributing](#-contributing)
- [License](#-license)

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.10 or higher** ([Download](https://www.python.org/downloads/))
- **pip** (comes with Python)
- **Git** (optional, for cloning)

### Installation

#### Option 1: Install from Source (Recommended)

```bash
# Clone the repository
git clone https://github.com/akshita2580/swiggy-mcp-server.git
cd swiggy-mcp-server

# Create virtual environment (recommended)
python -m venv .venv

# Activate virtual environment
# On Windows:
.venv\Scripts\activate
# On macOS/Linux:
source .venv/bin/activate

# Install in editable mode
pip install -e .
```

#### Option 2: Install Dependencies Manually

```bash
# Install from requirements.txt
pip install -r requirements.txt

# Or install individually
pip install fastapi fastmcp sqlmodel httpx uvicorn pydantic python-dotenv
```

#### Option 3: Install from PyPI (When Published)

```bash
pip install swiggy-mcp-server
```

### Running the Server

#### As MCP Server (for Claude Desktop / Cursor)

```bash
# Run over stdio (standard MCP transport)
python -m src.main --stdio

# Or use the CLI command if installed
swiggy-mcp --stdio
```

#### As REST API Server

```bash
# Run HTTP server on default port 8000
python -m src.main

# Specify custom host/port
python -m src.main --host 0.0.0.0 --port 8080

# Or use uvicorn directly for development
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

### Verify Installation

```bash
# Check server health
curl http://localhost:8000/api/health

# Expected response:
# {
#   "status": "ok",
#   "service": "swiggy-mcp-server",
#   "database": {
#     "total_orders": 0,
#     "date_coverage": "No data"
#   }
# }
```

---

## 🔌 MCP Integration

### What is MCP?

The [Model Context Protocol (MCP)](https://modelcontextprotocol.io) enables AI assistants like Claude to access external data sources and tools. This server exposes your Swiggy order data through MCP, allowing natural language queries like "Show me my spending trends" or "Which restaurant do I order from most?".

### Claude Desktop Configuration

1. **Locate your config file:**
   - **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

2. **Add the server configuration:**

```json
{
  "mcpServers": {
    "swiggy-orders": {
      "command": "python",
      "args": ["-m", "src.main", "--stdio"],
      "cwd": "C:\\absolute\\path\\to\\swiggy-mcp-server",
      "env": {
        "DATABASE_URL": "data/swiggy.db"
      }
    }
  }
}
```

3. **Restart Claude Desktop** — The server will appear in the MCP tools list

4. **Test the connection:**
   ```
   You: "Can you see my Swiggy order tools?"
   Claude: "Yes! I can see 6 Swiggy tools: sync_orders, get_orders, 
            get_restaurants, get_analytics, search_orders, and get_food_insights."
   ```

### Cursor AI Configuration

1. **Open Cursor settings** → MCP Configuration

2. **Add to your MCP config** (`.kiro/settings/mcp.json` or workspace settings):

```json
{
  "mcpServers": {
    "swiggy-orders": {
      "command": "python",
      "args": ["-m", "src.main", "--stdio"],
      "cwd": "/absolute/path/to/swiggy-mcp-server"
    }
  }
}
```

3. **Reload Cursor** — The tools will be available in the AI chat

### Alternative: Using the CLI Entry Point

If you installed via `pip install -e .`, you can use the CLI command:

```json
{
  "mcpServers": {
    "swiggy-orders": {
      "command": "swiggy-mcp",
      "args": ["--stdio"]
    }
  }
}
```

---

## 🛠️ Available MCP Tools

All 6 tools are automatically available in your AI assistant once the MCP server is configured.

### 1. 🔄 `sync_orders` — Fetch and Store Orders

Retrieves orders from Swiggy API and persists them to the local database.

**Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `cookies` | string | ✅ Yes | — | Swiggy session cookies (runtime-only) |
| `max_orders` | integer | ❌ No | 1000 | Maximum orders to fetch (1-5000) |

**Example Conversation:**
```
You: "Sync my last 500 Swiggy orders"
Assistant: [calls sync_orders with cookies and max_orders=500]

✅ Sync Complete
• New Orders Fetched: 487
• Total Orders in Storage: 1,234
• Date Coverage: 2023-06-15 to 2025-01-08
```

**Features:**
- ✅ Pagination handling (fetches all pages automatically)
- ✅ Deduplication (updates existing orders, prevents duplicates)
- ✅ Retry logic (3 attempts with exponential backoff)
- ✅ Rate limiting (0.5s delay between pages)
- ✅ Progress tracking (logs page fetches)

### 2. 📋 `get_orders` — Query Orders with Filters

Retrieve orders from local storage with flexible filtering options.

**Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `start_date` | string | ❌ No | — | Start date (YYYY-MM-DD) |
| `end_date` | string | ❌ No | — | End date (YYYY-MM-DD) |
| `restaurant_name` | string | ❌ No | — | Filter by restaurant (case-insensitive) |
| `limit` | integer | ❌ No | 50 | Max orders to return (1-500) |

**Example Conversations:**
```
You: "Show me orders from Pizza Hut in January 2025"
Assistant: [calls get_orders with start_date="2025-01-01", 
           end_date="2025-01-31", restaurant_name="Pizza Hut"]

You: "What did I order last week?"
Assistant: [calls get_orders with start_date=7 days ago, end_date=today]
```

**Returns:**
- Order details (ID, time, total, status)
- Restaurant information (name, location, cuisines)
- Item breakdown (name, quantity, price, veg/non-veg)
- Payment method
- Sorted by date (newest first)

---

### 3. `get_restaurants`
List restaurants with aggregated statistics.

**Parameters:**
- `start_date` (string, optional): Start date filter
- `end_date` (string, optional): End date filter
- `min_orders` (int, optional): Minimum orders to include restaurant (default: 1)

**Returns:** Restaurants sorted by order count with:
- Order count and total spending
- Average order value
- Cuisines and locations
- First and last order dates

### 4. `get_analytics`
Generate comprehensive analytics reports.

**Parameters:**
- `start_date` (string, optional): Start date filter
- `end_date` (string, optional): End date filter
- `analysis_type` (string, optional): One of:
  - `summary` — Overall statistics (default)
  - `spending` — Monthly spending trends
  - `timing` — Peak hours and day distribution
  - `restaurants` — Top 10 restaurants by order count
  - `cuisines` — Cuisine preferences and spending

**Example:**
```
User: "Analyze my food spending patterns for 2024"
Assistant: [calls get_analytics with start_date="2024-01-01", end_date="2024-12-31", analysis_type="spending"]
```

### 5. 🔍 `search_orders` — Search Across All Order Data

Search orders by restaurant name, cuisine, location, or item name.

**Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `query` | string | ✅ Yes | — | Search term (case-insensitive) |
| `limit` | integer | ❌ No | 20 | Maximum results (1-100) |

**Example Conversations:**
```
You: "Find all orders with biryani"
Assistant: [calls search_orders with query="biryani"]

You: "Search for pizzas ordered in December"
Assistant: [searches orders matching "pizza" and filters by date]
```

**Search Scope:**
- Restaurant names
- Cuisine types
- Locality/location names
- Food item names

---

### 6. 🧠 `get_food_insights` — Food Intelligence Insight Engine

Generate structured, explainable insights from locally stored order history. This milestone does not call an external LLM and does not fetch from Swiggy; it works only from stored database data. Optional `period` values include `today`, `yesterday`, `this week`, `last week`, `this month`, and `last month`.

**Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `start_date` | string | ❌ No | — | Start date (YYYY-MM-DD) |
| `end_date` | string | ❌ No | — | End date (YYYY-MM-DD) |

**Example Conversations:**
```
You: "Give me insights about my food ordering habits"
Assistant: [calls get_food_insights to analyze patterns]

🍽️ Food Intelligence Insights

💰 Spending Patterns
✓ Total Food Spending: You've spent ₹45,230 on 156 orders
ℹ️ Average Order Value: Your average order is ₹290
⚠️ Spending Increased: Your spending increased by 23% last month

📊 Ordering Behavior  
ℹ️ Ordering Frequency: You order 4.2 times per week
ℹ️ You Order Most on Fridays: Friday is your most common day (42 orders, 27%)
ℹ️ Peak Hour: 13:00 (lunch) - 38 orders
ℹ️ Weekday Ordering: You place 68% of orders on weekdays

❤️ Restaurant Loyalty
ℹ️ Favorite: Pizza Palace - 28 orders (18%)
✅ High Restaurant Loyalty: Strong loyalty with 12 restaurants

🌶️ Cuisine Preferences
ℹ️ Favorite Cuisine: North Indian (45 orders, 29%)
✅ High Cuisine Diversity: You enjoy 15 different cuisines!

🍔 Favorite Foods
ℹ️ Favorite Item: Margherita Pizza (ordered 8 times)
ℹ️ You Have Favorite Dishes: 5 items ordered 3+ times each
```

**Insight Categories:**

**💰 Spending Insights:**
- Total spending and average order value
- Monthly spending trends (increasing/decreasing/stable)
- Highest and lowest spending months
- Recorded savings only when stored discount data is available

**📊 Behavior Insights:**
- Order frequency (orders per week/month)
- Most common ordering day
- Peak ordering hour (with meal period classification)
- Weekday vs weekend patterns
- Meal time distribution (breakfast/lunch/dinner/late-night)
- Late-night ordering habits (10 PM - 6 AM)

**❤️ Loyalty Insights:**
- Favorite restaurant (most ordered)
- Restaurant loyalty score (repeat restaurants)
- Restaurant diversity (variety exploration)
- Average order value for the top restaurant in supporting data

**🌶️ Cuisine Insights:**
- Favorite cuisine preference
- Cuisine diversity score
- Month-to-month cuisine preference changes when enough cuisine tags exist

**🍔 Food Item Insights:**
- Most repeated dishes
- Favorite menu items
- Food preference patterns

**Data Requirements:**
- Minimum 10 orders for pattern analysis
- Specific thresholds for different insight types (e.g., 14 orders for day patterns, 8 for loyalty)
- Returns "Insufficient Data" message if thresholds not met

**Features:**
- ✅ Deterministic & explainable (no black-box AI)
- ✅ Data-quality aware (minimum threshold enforcement)
- ✅ Actionable recommendations
- ✅ Severity levels (INFO, SUCCESS, WARNING, ALERT)
- ✅ Supports date range filtering
- ✅ Handles edge cases (empty history, insufficient data)

---

## 📡 REST API Endpoints

All MCP tools have equivalent REST endpoints at `http://localhost:8000/api`:

### POST `/api/sync`
```bash
curl -X POST http://localhost:8000/api/sync \
  -H "Content-Type: application/json" \
  -d '{
    "cookies": "your_session_cookies",
    "max_orders": 1000,
    "max_pages": 50
  }'
```

### GET `/api/orders`
```bash
curl "http://localhost:8000/api/orders?start_date=2025-01-01&limit=10"
```

### GET `/api/restaurants`
```bash
curl "http://localhost:8000/api/restaurants?min_orders=5"
```

### GET `/api/analytics`
```bash
curl "http://localhost:8000/api/analytics?analysis_type=spending"
```

### GET `/api/search`
```bash
curl "http://localhost:8000/api/search?query=pizza&limit=20"
```

### GET `/api/insights`
```bash
# Get all insights for your order history
curl "http://localhost:8000/api/insights"

# Get insights for specific date range
curl "http://localhost:8000/api/insights?start_date=2024-01-01&end_date=2024-12-31"

# Get insights for a natural period
curl "http://localhost:8000/api/insights?period=last%20month"
```

**Response Format:**
```json
{
  "period": {
    "start": "2024-01-01",
    "end": "2024-12-31",
    "label": "2024-01-01 to 2024-12-31"
  },
  "total_orders": 156,
  "insights": [
    {
      "type": "SPENDING_TOTAL",
      "severity": "INFO",
      "title": "Total Food Spending",
      "message": "You've spent ₹45,230 on 156 orders.",
      "value": 45230,
      "unit": "₹",
      "period": "2024-01-01 to 2024-12-31",
      "supporting_data": {
        "order_count": 156,
        "start_date": "2024-01-01",
        "end_date": "2024-12-31"
      }
    }
    // ... more insights
  ],
  "generated_at": "2025-01-08T15:30:00Z"
}
```

### GET `/api/health`
```bash
curl http://localhost:8000/api/health
```

---

## 🔒 How to Get Your Swiggy Session Cookies

**Important:** Cookies are only needed when syncing orders. They're used once at runtime and never stored.

1. **Open Swiggy** in your browser and log in
2. **Navigate to** https://www.swiggy.com/my-account/orders
3. **Open Developer Tools** (F12 or Right-click → Inspect)
4. **Go to Network tab** and refresh the page
5. **Find any request** to `swiggy.com` domain
6. **Copy the `Cookie` header** value from Request Headers
7. **Provide to AI assistant** when it asks for cookies to sync orders

**Security Note:** Never commit cookies to version control or share them publicly. They expire periodically, so you'll need to refresh them when they become invalid.

---

## ⚙️ Configuration

### Environment Variables

Create a `.env` file in the project root:

```bash
# Environment (development or production)
ENVIRONMENT=development

# Encryption Key for securing tokens (Required in production)
ENCRYPTION_KEY=your_secure_fernet_key

# Database location (default: data/swiggy.db)
DATABASE_URL=data/swiggy.db

# REST API port (default: 8000)
PORT=8000

# Swiggy API base URL (default: https://www.swiggy.com/dapi/order/all)
SWIGGY_API_URL=https://www.swiggy.com/dapi/order/all

# Request timeout in seconds (default: 30)
REQUEST_TIMEOUT=30

# OAuth Canonical Callback URI
SWIGGY_REDIRECT_URI=http://localhost:8000/api/auth/swiggy/callback
```

### Security & Token Storage

- In `development` (without `ENCRYPTION_KEY`), a local key is automatically generated and saved to `.dev_encryption_key` so local sessions persist across restarts. **DO NOT commit this file.**
- In `production`, the server will **fail to start** if `ENCRYPTION_KEY` is not provided.
- OAuth access tokens are always stored securely as ciphertext.
- OAuth states are strictly single-use, non-replayable, and automatically cleaned up upon success, failure, or expiration.

> **Important Limitation:**
> OAuth authentication does NOT currently make the existing cookie-based `sync_orders` work. OAuth is used for account linking, but you must still provide cookies to the `sync_orders` endpoint to sync order history.

### Dynamic Client Registration (DCR)

Swiggy OAuth uses Dynamic Client Registration (DCR). When a user initiates a connection:
- DCR is performed automatically using the official Swiggy endpoint.
- The registration is saved locally to `.swiggy_oauth_client.json`.
- The `SWIGGY_REDIRECT_URI` environment variable controls the registered redirect URI. If it changes, the application automatically re-registers.
- **Manual configuration of `SWIGGY_CLIENT_ID` and `SWIGGY_CLIENT_SECRET` is no longer required**. Since the official DCR endpoint uses a public-client configuration (`token_endpoint_auth_method=none`), no client secret is needed.
- If you need to force a new registration, simply delete the `.swiggy_oauth_client.json` file and restart the server.


### Project Structure

```
swiggy-mcp-server/
├── src/                          # Source code
│   ├── main.py                   # Application entry point
│   ├── mcp_server.py             # MCP tool definitions
│   ├── api.py                    # FastAPI REST routes
│   ├── models.py                 # Pydantic & SQLModel schemas
│   ├── database.py               # SQLite engine & session management
│   ├── repository.py             # Data access layer
│   ├── fetcher.py                # Swiggy API client
│   ├── error_handlers.py         # FastAPI error handlers
│   └── utils.py                  # JSON serialization utilities
├── data/                         # Database storage
│   └── swiggy.db                 # SQLite database
├── tests/                        # Unit tests
├── pyproject.toml                # Project metadata & dependencies
├── requirements.txt              # Dependency list
└── README.md                     # This file
```

---

## 🧪 Development

### Setup Development Environment

```bash
# Clone repository
git clone https://github.com/akshita2580/swiggy-mcp-server.git
cd swiggy-mcp-server

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies with dev tools
pip install -e ".[dev]"

# Or manually install dev dependencies
pip install -r requirements.txt
pip install pytest black ruff mypy
```

### Code Quality Tools

```bash
# Format code with black
black src/ --line-length 100

# Sort imports and check style with ruff
ruff check src/ --fix

# Type checking with mypy
mypy src/

# Run tests
pytest tests/ -v
```

### Development Mode

```bash
# Run with auto-reload
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# Enable debug logging
export NODE_ENV=development
python -m src.main
```

---

## 📊 Database Schema

### Tables

**orders** — Main order records
- `order_id` (string, primary key)
- `restaurant_id`, `restaurant_name`, `restaurant_locality`, `restaurant_city`
- `restaurant_cuisines` (comma-separated)
- `order_time` (datetime, indexed)
- `order_total`, `order_discount`, `delivery_charge`, `gst`
- `order_status`, `payment_method`, `delivery_address`
- `raw_json` (full API response)
- `created_at` (timestamp)

**order_items** — Line items within orders
- `id` (int, primary key)
- `order_id` (foreign key → orders)
- `item_id`, `name`, `quantity`, `price`, `is_veg`

**order_cuisines** — Normalized cuisine tags
- `id` (int, primary key)
- `order_id` (foreign key → orders, indexed)
- `cuisine_name` (indexed)

---

## 🐛 Troubleshooting

### Server Won't Start

```bash
# Check Python version
python --version  # Should be 3.10+

# Reinstall dependencies
pip install --upgrade -r requirements.txt

# Check port availability
lsof -i :8000  # On macOS/Linux
netstat -ano | findstr :8000  # On Windows
```

### Authentication Errors

- **Error: "Invalid or expired session cookies"**
  - Get fresh cookies from Swiggy website
  - Ensure you're logged in to Swiggy
  - Copy the complete Cookie header value

### Database Issues

```bash
# Reset database
rm data/swiggy.db

# Restart server (tables will be auto-created)
python -m src.main
```

### MCP Connection Issues

- Verify absolute paths in MCP config
- Check server starts without errors: `python -m src.main --stdio`
- Restart Claude Desktop / Cursor after config changes
- Check logs in `~/.config/Claude/logs/` (Claude Desktop)

---

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Code Style Guidelines

- Use **black** for formatting (line-length 100)
- Use **ruff** for linting and import sorting
- Add **type hints** to all public functions
- Write **docstrings** for modules and public functions
- Add **tests** for new features

---

## 📝 License

MIT License — See [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- **Swiggy** for the order data API
- **FastMCP** team for the excellent MCP framework
- **FastAPI** for the modern async web framework
- **SQLModel** for the elegant ORM layer
- **Python community** for the amazing ecosystem

---

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/akshita2580/swiggy-mcp-server/issues)
- **Documentation**: This README and inline code comments
- **Examples**: See `test/` directory for usage examples

---

**Built with ❤️ using Python, FastAPI, and FastMCP**

*Analyze your food delivery data with AI — securely and privately*
