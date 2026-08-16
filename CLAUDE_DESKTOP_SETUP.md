# Claude Desktop MCP Integration Setup

## Quick Setup Guide

### 1. Configure Claude Desktop

1. Open Claude Desktop
2. Go to **Settings** → **Developer**
3. Click **"Edit Config"** to open `claude_desktop_config.json`
4. Add your server configuration:

```json
{
  "mcpServers": {
    "swiggy-orders": {
      "command": "node",
      "args": ["/path/to/nodejs-mcp-server/index.js"],
      "env": {
        "NODE_ENV": "production"
      }
    }
  }
}
```

**Important:** Replace the path with the absolute path to your `index.js` file.

### 2. Update Configuration

Make sure your `config/default.json` has valid Swiggy session cookies:

```bash
npm run config
```

### 3. Test the Server

Before connecting to Claude Desktop, test the server:

```bash
# Test MCP mode
echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}' | node index.js mcp

# Should return clean JSON without any logging
```

### 4. Restart Claude Desktop

After updating the configuration:
1. Save the `claude_desktop_config.json` file
2. **Completely restart Claude Desktop** (quit and reopen)
3. The MCP server should now be available

## Troubleshooting

### Common Issues

1. **"Server disconnected" errors:**
   - Check that the path to `index.js` is absolute and correct
   - Ensure Node.js is in your system PATH
   - Verify your cookies are valid in `config/default.json`

2. **JSON parsing errors:**
   - Make sure you're using the latest version of this server
   - Check that no console.log statements are going to stdout

3. **Permission errors:**
   - Ensure Claude Desktop has permission to execute Node.js
   - Check file permissions on your server directory

### Debug Steps

1. **Check Claude Desktop logs:**
   - macOS: `~/Library/Logs/Claude/mcp.log`
   - Look for error messages about your server

2. **Test server manually:**
   ```bash
   # This should show valid JSON only
   node index.js mcp < /dev/null
   ```

3. **Verify configuration:**
   ```bash
   # This should work without MCP mode
   node index.js config
   ```

### Server Features

Once connected, you'll have access to these tools in Claude Desktop:

- **fetch_swiggy_orders**: Fetch and analyze your Swiggy order history
- **analyze_food_habits**: Get detailed insights into your food ordering patterns
- **get_swiggy_stats**: View server statistics and storage info
- **export_swiggy_data**: Export your order data

### Example Usage in Claude

Once the MCP server is connected, you can ask Claude:

> "Can you fetch my Swiggy orders from the last 30 days and analyze my food habits?"

Claude will automatically use the MCP tools to fetch and analyze your data.

## Configuration Reference

Your `claude_desktop_config.json` should follow this format:

```json
{
  "mcpServers": {
    "server-name": {
      "command": "node",
      "args": ["absolute/path/to/index.js"],
      "env": {
        "NODE_ENV": "production"
      }
    }
  }
}
```

**Key points:**
- Use absolute paths only
- Server name can be anything you want
- The `env` section is optional but recommended
