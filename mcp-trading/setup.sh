#!/bin/bash
# Alpaca MCP Trading System Setup Script

set -e

echo "=========================================="
echo "  Alpaca MCP Trading System Setup"
echo "=========================================="
echo ""

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "Installing uv package manager..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    echo ""
    echo "IMPORTANT: Restart your terminal after uv installation, then run this script again."
    exit 0
fi

echo "✓ uv is installed: $(uv --version)"
echo ""

# Initialize MCP server
echo "Initializing Alpaca MCP Server..."
echo "This will use the credentials from .env file"
echo ""

uvx alpaca-mcp-server init

echo ""
echo "=========================================="
echo "  Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Add MCP server to Claude Code:"
echo "   claude mcp add alpaca --scope user --transport stdio uvx alpaca-mcp-server serve \\"
echo "     --env ALPACA_API_KEY=PKCDLH6JNAUB2NXXE3THXHHSHG \\"
echo "     --env ALPACA_SECRET_KEY=5v1dmhhjbXZWkgk6rm99VjTHS49J6MF8jGFkVDGzByYD"
echo ""
echo "2. Or manually add to ~/.claude/settings.json:"
echo "   See config.json in this folder"
echo ""
echo "3. Restart Claude Code and verify:"
echo "   claude"
echo "   > /mcp"
echo ""
echo "4. Try a command:"
echo "   > What's my account balance?"
echo ""
