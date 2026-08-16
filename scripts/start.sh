#!/bin/bash
# Start Script for Swiggy MCP Server - Clean Node.js Implementation
# Version: 2.0.0

echo "🍕 Starting Swiggy MCP Server - Node.js Edition"
echo "=============================================="

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo "❌ Node.js is not installed. Please run: npm run setup"
    exit 1
fi

# Check Node.js version
NODE_VERSION=$(node --version | cut -d'v' -f2)
REQUIRED_MAJOR=18
NODE_MAJOR=$(echo $NODE_VERSION | cut -d'.' -f1)

if [ $NODE_MAJOR -lt $REQUIRED_MAJOR ]; then
    echo "❌ Node.js version $NODE_VERSION is too old. Please upgrade to Node.js 18+"
    exit 1
fi

echo "✅ Node.js version: $NODE_VERSION"

# Check if dependencies are installed
if [ ! -d "node_modules" ]; then
    echo "📦 Installing dependencies..."
    npm install
    if [ $? -ne 0 ]; then
        echo "❌ Failed to install dependencies"
        exit 1
    fi
fi

# Check if config file exists
CONFIG_FILE="config/default.json"
if [ ! -f "$CONFIG_FILE" ]; then
    echo "❌ Configuration file $CONFIG_FILE not found"
    echo "💡 Please run: npm run setup"
    exit 1
fi

# Validate configuration
echo "🔍 Validating configuration..."
if grep -q "YOUR_SESSION_COOKIES_HERE" "$CONFIG_FILE"; then
    echo "❌ Please update your session cookies in $CONFIG_FILE"
    echo "💡 See setup instructions: npm run setup"
    exit 1
fi

# Check if port is available
PORT=${1:-8001}
if command -v lsof &> /dev/null; then
    if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo "⚠️  Port $PORT is already in use"
        echo "💡 Try: lsof -ti:$PORT | xargs kill"
        echo "Or use a different port: ./scripts/start.sh 8002"
        exit 1
    fi
fi

# Set environment variables
export NODE_ENV=${NODE_ENV:-production}
export PORT=$PORT

# Determine mode
MODE=${2:-"server"}
case $MODE in
    "server")
        echo "🚀 Starting REST API server on port $PORT..."
        echo "🌐 Server will be available at: http://localhost:$PORT"
        echo "📊 Health check: http://localhost:$PORT/health"
        echo "📈 Stats: http://localhost:$PORT/stats"
        echo ""
        echo "📝 Logs will be shown below (Ctrl+C to stop)"
        echo ""
        npm start
        ;;
    "mcp")
        echo "🔗 Starting MCP server for Cursor AI integration..."
        echo "📡 MCP server ready for connections"
        echo ""
        echo "📝 Add this to your Cursor AI MCP settings:"
        echo "   Command: node"
        echo "   Args: [\"$(pwd)/simple-index.js\"]"
        echo ""
        npm run mcp
        ;;
    "dev")
        echo "🔧 Starting in development mode with auto-restart..."
        echo "🌐 Server will be available at: http://localhost:$PORT"
        echo ""
        npm run dev
        ;;
    *)
        echo "❌ Invalid mode: $MODE"
        echo "💡 Usage: ./scripts/start.sh [port] [mode]"
        echo "   Modes: server (default), mcp, dev"
        exit 1
        ;;
esac
