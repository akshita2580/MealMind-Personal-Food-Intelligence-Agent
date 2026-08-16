#!/bin/bash
# Setup Script for Swiggy MCP Server - Clean Node.js Implementation
# Version: 2.0.0

echo "🚀 Swiggy AI Insights - Setup"
echo "=============================="

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

echo "📁 Project directory: $PROJECT_DIR"

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo "❌ Node.js is not installed"
    echo "📝 Please install Node.js 18+ from: https://nodejs.org/"
    echo ""
    echo "For macOS with Homebrew:"
    echo "  brew install node"
    echo ""
    echo "For macOS with nvm:"
    echo "  curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash"
    echo "  nvm install 18"
    echo "  nvm use 18"
    exit 1
fi

# Check Node.js version
NODE_VERSION=$(node --version | cut -d'v' -f2)
REQUIRED_MAJOR=18
NODE_MAJOR=$(echo $NODE_VERSION | cut -d'.' -f1)

if [ $NODE_MAJOR -lt $REQUIRED_MAJOR ]; then
    echo "❌ Node.js version $NODE_VERSION is too old"
    echo "📝 Please upgrade to Node.js 18+ first"
    exit 1
fi

echo "✅ Node.js version: $NODE_VERSION"

# Check if npm is available
if ! command -v npm &> /dev/null; then
    echo "❌ npm is not installed"
    echo "📝 npm should come with Node.js. Please reinstall Node.js"
    exit 1
fi

echo "✅ npm version: $(npm --version)"

# Create necessary directories
echo ""
echo "📁 Creating directories..."
mkdir -p data logs

# Install dependencies
echo ""
echo "📦 Installing Node.js dependencies..."
npm install

if [ $? -ne 0 ]; then
    echo "❌ Failed to install dependencies"
    exit 1
fi

echo "✅ Dependencies installed successfully"

# Make scripts executable
chmod +x scripts/*.sh

# Security-first design - no config needed!
echo ""
echo "🔒 Security Note: This project never stores cookies in config files!"
echo "Claude will prompt you for cookies when needed - much safer!"
echo ""

echo ""
echo "🎉 Setup completed successfully!"
echo ""
echo "📋 Next steps:"
echo "1. Start the MCP server: npm run mcp"
echo "2. Configure Claude Desktop with the config example"
echo "3. Ask Claude to analyze your Swiggy orders!"
echo "4. Claude will prompt for cookies when needed (secure!)"
echo "5. Optional: Test performance: npm run test"
echo ""
echo "📚 Available commands:"
echo "  npm start          - Start the REST API server"
echo "  npm run mcp        - Start the MCP server for Cursor AI"
echo "  npm run dev        - Start in development mode with auto-restart"
echo "  npm run test       - Run performance tests"
echo ""
echo "🔗 AI Integration with Claude/Cursor:"
echo "  1. Copy the absolute path: $(pwd)/index.js"
echo "  2. Update config/cursor-mcp.json with this path"
echo "  3. Add the MCP config to your Claude/Cursor AI settings"
echo ""
echo "🆘 Need help?"
echo "  - Check the README.md file"
echo "  - Make sure your cookies are fresh (login again if needed)"
echo "  - Verify the server is running on the correct port"
echo ""
echo "🚀 Ready to unlock your food intelligence!"
