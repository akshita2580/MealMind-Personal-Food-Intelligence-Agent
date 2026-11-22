<div align="center">
  <h1>🍽️ MealMind</h1>
  <p><strong>Your Personal Food Intelligence & MCP Swiggy Agent</strong></p>

  <p>
    <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="Python 3.10+"></a>
    <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/FastAPI-0.115+-009688.svg?logo=fastapi&logoColor=white" alt="FastAPI"></a>
    <a href="https://sqlmodel.tiangolo.com/"><img src="https://img.shields.io/badge/SQLModel-Database-black.svg" alt="SQLModel"></a>
    <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
  </p>
</div>

---

## 📖 Overview

**MealMind** is a comprehensive, AI-powered food intelligence agent built around the Swiggy ecosystem (Food Delivery, Instamart Groceries, and Dineout Reservations).

By integrating directly with Swiggy's official **Builders Club Model Context Protocol (MCP) servers**, MealMind allows you to order food, buy groceries, book tables, and analyze your spending habits entirely from a modern **React web application** or from your favorite AI IDE (like Cursor/Claude Desktop).

---

## ✨ Core Ecosystem Capabilities

| Vertical | Features | Status |
| :--- | :--- | :---: |
| 🍕 **Food Delivery** | Restaurant search, interactive menus, cart management, and seamless web checkout (UPI/Cash). | ✅ |
| 🥦 **Instamart** | Grocery product search, variation parsing, isolated cart session, and order placement. | ✅ |
| 🍽️ **Dineout** | Location-based venue search, dynamic date/time slot fetching, guest count configuration, and secure table booking. | ✅ |
| 🧠 **Intelligence** | Background syncing of order history, peak ordering analytics, monthly trend analysis, and custom insights engine. | ✅ |

---

## 🏗️ System Architecture

MealMind operates with a dual-architecture design. It **consumes** Swiggy's external MCP servers to execute real-world actions, while simultaneously acting as its **own Custom MCP Server** to serve analytics back to external AI agents.

```mermaid
graph TD
    User([👤 User]) -->|Web UI| ReactApp[⚛️ React Frontend]
    User -->|Prompts| ExtAI[🧠 External AI Assistant<br>e.g. Cursor, Claude]
    
    ReactApp <-->|OAuth 2.1 / DCR| SwiggyAuth[🔐 Swiggy Authentication]
    ReactApp -->|REST API| FastAPI[🚀 FastAPI Backend]
    
    FastAPI --> MCP_Transport[🚀 mcp_transport.py<br>Robust JSON-RPC Client]
    
    MCP_Transport -->|JSON-RPC| SwiggyFood(🍔 mcp.swiggy.com/food)
    MCP_Transport -->|JSON-RPC| SwiggyIM(🥦 mcp.swiggy.com/im)
    MCP_Transport -->|JSON-RPC| SwiggyDineout(🍽️ mcp.swiggy.com/dineout)
    
    ExtAI <-->|Local JSON-RPC| CustomMCP[🖥️ MealMind Custom MCP Server]
    CustomMCP <--> InsightEngine[📊 Insight Engine & DB]
    FastAPI <--> InsightEngine
```

### 🧩 Component Breakdown

1. **Presentation Layer (React Web UI)**
   - Modern React + TypeScript + Tailwind CSS frontend
   - Interactive cart management with real-time Swiggy cart synchronization
   - Multi-schema cart update fallback for robust Swiggy API compatibility

2. **Swiggy Integration Layer**
   - **`mcp_transport.py`**: A hardened generic HTTP/JSON-RPC client that handles strict `asyncio` timeouts, exception translation, and varied content extraction formats.
   - **Wrappers**: `swiggy_mcp_client.py`, `swiggy_instamart_mcp.py`, and `swiggy_dineout_mcp.py` provide strongly-typed async functions for every official Swiggy tool.

3. **Data, Analytics & Security**
   - **Dynamic Client Registration (`dcr.py`)**: Automatically negotiates and registers the OAuth client with Swiggy on startup.
   - **Token Encryption (`security.py`)**: OAuth tokens (`SwiggyConnection`) are encrypted at rest using `cryptography.fernet`.
   - **`insight_engine.py`**: Aggregates historical order data to rank top dishes, analyze peak hours, and generate LLM-friendly insight reports.
   - **PostgreSQL**: Primary database for production deployments (SQLite supported for local development).

---

## 🚀 Getting Started

### 1. Prerequisites
- **Python 3.10+**
- **PostgreSQL 14+** (or use SQLite for local development)
- **Node.js 18+** (for React frontend)

### 2. Environment Configuration
Create a `.env` file in the project root:

```env
# Database Configuration (PostgreSQL)
# Example for local PostgreSQL; use your provider's URL in deployment.
# Format: postgresql+psycopg://user:password@host:port/database
DATABASE_URL=postgresql+psycopg://postgres:password@localhost:5432/mealmind

# Server Configuration
PORT=8000

# Swiggy API Configuration
SWIGGY_API_URL=https://www.swiggy.com/dapi/order/all
REQUEST_TIMEOUT=30

# OAuth Canonical Callback URI
# Default: http://127.0.0.1:8000/api/auth/swiggy/callback
SWIGGY_REDIRECT_URI=http://127.0.0.1:8000/api/auth/swiggy/callback

# Environment (development or production)
ENVIRONMENT=development

# Encryption Key for securing tokens (Required in production)
# Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
ENCRYPTION_KEY=

# Official Swiggy MCP servers
SWIGGY_FOOD_MCP_URL=https://mcp.swiggy.com/food
SWIGGY_INSTAMART_MCP_URL=https://mcp.swiggy.com/im
SWIGGY_DINEOUT_MCP_URL=https://mcp.swiggy.com/dineout
```

For an existing SQLite database, install the requirements and run:
```bash
python scripts/migrate_sqlite_to_postgres.py
```
after configuring `DATABASE_URL` to your PostgreSQL URL. The migration copies `data/swiggy.db` into empty PostgreSQL tables and leaves the SQLite file untouched.

### 3. Installation & Boot

```bash
# Clone the repository
git clone https://github.com/yourusername/mealmind.git
cd mealmind

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install Python dependencies
pip install -r requirements.txt

# Install frontend dependencies
cd frontend
npm install
cd ..

# Start the backend server
python -m src.main

# In another terminal, start the frontend dev server
cd frontend
npm run dev
```

### 4. Connect & Play
1. Open http://localhost:5173 in your browser
2. Click **Connect Swiggy** to initiate the secure OAuth flow
3. Once authenticated, explore the web interface to order food, book tables, or view your personal food insights!

---

## 🛡️ Security & Tenant Isolation

Enterprise-grade security is baked into MealMind:
- **Zero-Leakage Design:** The `get_user_token(user, db)` strictly isolates sessions. One user cannot trigger orders or view data on another user's Swiggy account.
- **Encrypted Storage:** User tokens are never stored in plaintext. They are encrypted at rest using Fernet symmetric encryption.
- **Explicit Consent:** No automatic order placement or table booking is permitted by the system. The UI explicitly renders cart totals and requires a final tap confirmation before triggering any state-mutating MCP commands (e.g. `checkout` or `book_table`).

---

## 🧪 Testing

MealMind ships with a comprehensive mock testing suite that verifies API endpoints, edge cases, and MCP error handling without hitting production endpoints.

```bash
# Install test dependencies
pip install pytest pytest-asyncio

# Run the test suite
pytest -v
```

---

## 🤝 Contributing

Contributions are welcome! Whether it's adding a new Swiggy vertical, improving the insights engine, or squashing bugs:
1. Fork the project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'feat: Add some AmazingFeature'`)
4. Ensure tests pass (`pytest`)
5. Push to the Branch (`git push origin feature/AmazingFeature`)
6. Open a Pull Request

---

## 📄 License

Distributed under the MIT License. See `LICENSE` for more information.