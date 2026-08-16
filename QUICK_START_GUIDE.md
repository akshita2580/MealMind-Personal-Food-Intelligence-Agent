# ⚡ Quick Start Guide - Swiggy MCP Server

**Get up and running in 5 minutes!**

---

## 📦 1. Installation (2 minutes)

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/swiggy-mcp-server.git
cd swiggy-mcp-server

# Create virtual environment
python -m venv .venv

# Activate it
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -e .
```

---

## 🚀 2. Start the Server (30 seconds)

### Option A: REST API Mode
```bash
python -m src.main

# Server running at: http://localhost:8000
# API docs at: http://localhost:8000/docs
```

### Option B: MCP Mode (for Claude/Cursor)
```bash
python -m src.main --stdio
```

---

## ✅ 3. Verify Installation (30 seconds)

```bash
# Check server health
curl http://localhost:8000/api/health

# Expected response:
# {"status":"ok","service":"swiggy-mcp-server","database":{...}}
```

---

## 🔑 4. Get Swiggy Cookies (1 minute)

1. Open https://www.swiggy.com in your browser
2. Log in to your account
3. Open Developer Tools (F12)
4. Go to Network tab
5. Refresh the page
6. Click any request to swiggy.com
7. Find "Cookie" in Request Headers
8. Copy the entire cookie string

**Example cookie string:**
```
_guest_tid=abc123; _device_id=xyz789; ...
```

---

## 🎯 5. Sync Your First Orders (1 minute)

### Via REST API:
```bash
curl -X POST http://localhost:8000/api/sync \
  -H "Content-Type: application/json" \
  -d '{
    "cookies": "YOUR_COOKIE_STRING_HERE",
    "max_orders": 100
  }'
```

### Via MCP (in Claude Desktop):
```
You: "Sync my last 100 Swiggy orders"
[Provide cookies when prompted]
```

---

## 🔍 6. Query Your Data (30 seconds)

### REST API Examples:
```bash
# Get recent orders
curl "http://localhost:8000/api/orders?limit=10"

# Get analytics
curl "http://localhost:8000/api/analytics?analysis_type=summary"

# Search for pizza orders
curl "http://localhost:8000/api/search?query=pizza"
```

### MCP Examples (in Claude):
```
You: "Show me my last 10 orders"
You: "Which restaurants do I order from most?"
You: "Analyze my spending patterns"
You: "Search for biryani orders"
```

---

## 🔌 7. Configure MCP Client (Optional, 2 minutes)

### For Claude Desktop:

**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`  
**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "swiggy-orders": {
      "command": "python",
      "args": ["-m", "src.main", "--stdio"],
      "cwd": "C:\\path\\to\\swiggy-mcp-server"
    }
  }
}
```

### For Cursor:

Add to `.kiro/settings/mcp.json`:
```json
{
  "mcpServers": {
    "swiggy-orders": {
      "command": "python",
      "args": ["-m", "src.main", "--stdio"],
      "cwd": "/path/to/swiggy-mcp-server"
    }
  }
}
```

**Restart** Claude Desktop or Cursor after configuration.

---

## 🎉 You're Done!

### What's Next?

✅ **Sync more orders**: Increase `max_orders` to fetch your full history  
✅ **Explore analytics**: Try different `analysis_type` options  
✅ **Build dashboards**: Use the REST API to create visualizations  
✅ **Ask questions**: Use natural language with your AI assistant  

---

## 🆘 Common Issues

### Issue: "Invalid or expired cookies"
**Solution:** Get fresh cookies from Swiggy website (they expire periodically)

### Issue: "Port 8000 already in use"
**Solution:** Use a different port: `python -m src.main --port 8080`

### Issue: "Module not found"
**Solution:** Make sure you activated the virtual environment and ran `pip install -e .`

### Issue: "Database locked"
**Solution:** Close any other connections to the database file

---

## 📚 Learn More

- **Full Documentation**: [README.md](README.md)
- **Complete Features**: [FEATURES.md](FEATURES.md)
- **Implementation Status**: [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md)
- **Troubleshooting**: See README.md § Troubleshooting

---

## 🔐 Security Reminder

🛡️ **Your cookies are NEVER stored!**
- Accepted only as runtime parameters
- Used once and immediately discarded
- Never written to disk, database, or logs
- Zero-persistence design

---

**Happy analyzing! 🍽️📊**

*Questions? Open an issue on GitHub or check the documentation.*
