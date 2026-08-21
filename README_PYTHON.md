# Swiggy MCP Server - Python Re-architecture

**Ported from Original (JavaScript/Node.js):**
- Core MCP tool functionality: `sync_orders`, `get_orders`, `get_restaurants`, `get_analytics`, `search_orders`
- Swiggy API integration logic (pagination, rate limiting, retry mechanism)
- Order analytics algorithms (spending trends, timing patterns, cuisine analysis)
- Data persistence and deduplication strategy

**New in Python Re-architecture:**
- **SQLite + SQLModel ORM** instead of JSON file storage
  - Normalized schema with separate tables for orders, restaurants, cuisines, items
  - Database indexes for efficient date-range and text search queries
  - ACID guarantees for concurrent access
- **FastAPI REST API layer** exposing all MCP functionality via HTTP
  - JSON responses with Pydantic validation
  - OpenAPI/Swagger documentation
  - Independent of MCP protocol for broader integration
- **FastMCP integration** (Python MCP SDK) instead of @modelcontextprotocol/sdk
- **Pydantic v2 models** for request/response validation and serialization
- **Async/await patterns** throughout using httpx and asyncio
- **Type hints and modern Python idioms** (3.11+ syntax)
- **Security enhancement**: cookies handled as runtime-only parameters (never persisted)

### Why Re-architect Instead of Fork?

This is a **learning project and resume piece**, not a production fork. The goal is to:
1. Demonstrate understanding of MCP protocol implementation
2. Showcase Python backend skills (FastAPI, SQLModel, async patterns)
3. Make intentional design decisions (e.g., SQLite vs JSON) that I can explain in interviews
4. Add new capabilities (REST API) that weren't in the original

---

## Original Project

**Repository**: https://github.com/imachiever/swiggy-mcp-server  
**Language**: JavaScript/Node.js  
**MCP SDK**: @modelcontextprotocol/sdk  
**Storage**: JSON file with in-memory caching  

---

## This Re-architecture

**Language**: Python 3.11+  
**MCP SDK**: FastMCP  
**Web Framework**: FastAPI  
**ORM**: SQLModel  
**Database**: SQLite  
**Storage**: Relational database with normalized schema  

### Key Design Decisions

1. **SQLite over JSON**
   - **Why**: Enables efficient date-range queries without loading entire dataset
   - **Trade-off**: Slightly more complex setup vs. file-based storage
   - **Interview answer**: "JSON is fine for prototypes, but relational DBs scale better for filtering and aggregation"

2. **FastAPI REST layer**
   - **Why**: MCP tools are great for AI agents, but humans and other services need HTTP APIs
   - **Trade-off**: More code surface area
   - **Interview answer**: "Multi-interface design pattern — same business logic, multiple access methods"

3. **Pydantic for everything**
   - **Why**: Single source of truth for schemas, automatic validation
   - **Interview answer**: "Type safety prevents runtime errors and documents expected data shapes"

4. **Async by default**
   - **Why**: Network I/O (Swiggy API) and DB queries benefit from async
   - **Interview answer**: "Non-blocking I/O improves throughput for I/O-bound workloads"

---

## Project Status

🚧 **Work in Progress** — This is a resume/portfolio project under active development.

**Completed:**
- [ ] Python project structure
- [ ] Pydantic models
- [ ] SQLite schema design
- [ ] Swiggy API client (httpx + retry logic)
- [ ] Data persistence layer
- [ ] MCP tools implementation
- [ ] FastAPI REST endpoints
- [ ] Testing and documentation

---
