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

## 🚀 Quick Start

### Prerequisites
- **Python 3.11+**
- **PostgreSQL 14+** (Recommended: [Neon.tech](https://neon.tech) - Serverless PostgreSQL)
- **Node.js 18+** (for React frontend)
- **Swiggy Account** (for OAuth integration)

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/mealmind.git
cd mealmind
```

2. **Backend Setup**
```bash
# Create virtual environment
python -m venv .venv

# Activate (Windows)
.venv\Scripts\activate

# Activate (Unix/Mac)
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

3. **Frontend Setup**
```bash
cd frontend
npm install
cd ..
```

4. **Environment Configuration**

Copy `.env.example` to `.env` and configure:

```env
# Database (Use Neon PostgreSQL for production)
DATABASE_URL=postgresql+psycopg://user:password@host/database

# Backend
BACKEND_PORT=8000
FRONTEND_URL=http://localhost:5173

# Swiggy OAuth (Get from Swiggy Builders Club)
SWIGGY_CLIENT_ID=your_client_id
SWIGGY_CLIENT_SECRET=your_client_secret
SWIGGY_REDIRECT_URI=http://localhost:8000/api/auth/callback

# Security (Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
ENCRYPTION_KEY=your_fernet_key
```

5. **Database Migration (if migrating from SQLite)**
```bash
python scripts/migration/migrate_sqlite_to_postgres.py
```

### Running the Application

**Start Backend** (Terminal 1):
```bash
python -m src.main
```
Backend runs on `http://localhost:8000`

**Start Frontend** (Terminal 2):
```bash
cd frontend
npm run dev
```
Frontend runs on `http://localhost:5173`

### First Use
1. Open http://localhost:5173 in your browser
2. Click **Connect Swiggy** to initiate OAuth
3. Authorize the application on Swiggy
4. You'll be redirected back - orders sync automatically!
5. Explore all features: Food Delivery, Instamart, Dineout, Analytics

---

## 🛡️ Security & Tenant Isolation

Enterprise-grade security is baked into MealMind:
- **Zero-Leakage Design:** The `get_user_token(user, db)` strictly isolates sessions. One user cannot trigger orders or view data on another user's Swiggy account.
- **Encrypted Storage:** User tokens are never stored in plaintext. They are encrypted at rest using Fernet symmetric encryption.
- **Explicit Consent:** No automatic order placement or table booking is permitted by the system. The UI explicitly renders cart totals and requires a final tap confirmation before triggering any state-mutating MCP commands (e.g. `checkout` or `book_table`).

---

## 🧪 Testing

### Backend Tests (Pytest)
```bash
pytest -v
```

### Frontend Tests (Vitest)
```bash
cd frontend
npm run test
```

### Test Coverage
```bash
# Backend coverage
pytest --cov=src --cov-report=html

# Frontend coverage
cd frontend
npm run test:coverage
```

---

## 📁 Project Structure

```
mealmind/
├── frontend/              # React web application
│   ├── src/
│   │   ├── components/   # Reusable UI components
│   │   ├── pages/        # Page components
│   │   ├── services/     # API service layer
│   │   └── lib/          # Utility functions
│   └── tests/            # Frontend tests
├── src/                  # Python backend
│   ├── api.py           # FastAPI endpoints
│   ├── repository.py    # Database operations
│   ├── scheduler.py     # Token refresh scheduler
│   ├── security.py      # Encryption & auth
│   └── ...
├── scripts/             # Utility scripts
│   ├── migration/       # Database migration scripts
│   └── debug/           # Debug and test scripts
├── docs/                # Documentation
│   ├── SETUP.md         # Detailed setup guide
│   └── ARCHITECTURE.md  # Architecture documentation
└── tests/               # Backend tests
```

## 🤝 Contributing

Contributions are welcome! Follow these steps:

1. Fork the project
2. Create feature branch: `git checkout -b feature/AmazingFeature`
3. Make changes and test thoroughly
4. Commit with conventional commits: `git commit -m 'feat: Add AmazingFeature'`
5. Push to branch: `git push origin feature/AmazingFeature`
6. Open a Pull Request (will be squash-merged for clean history)

**Commit Convention:**
- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation changes
- `test:` Adding/updating tests
- `refactor:` Code refactoring
- `chore:` Maintenance tasks

---

## 📄 License

Distributed under the MIT License. See `LICENSE` for more information.