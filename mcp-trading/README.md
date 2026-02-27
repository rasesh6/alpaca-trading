# Alpaca MCP Trading System

Natural language trading system using Alpaca's official MCP Server.

## Overview

This is a **separate, independent** trading system from the Flask web UI.
- **Flask Web UI** (`../server.py`) - Manual trading with visual interface
- **MCP Trading** (this folder) - Natural language commands via AI assistants

## Architecture

```
mcp-trading/
├── README.md              # This file
├── .env                   # API credentials (shared with main system)
├── config.json            # MCP server configuration
├── setup.sh               # Setup script
└── custom_tools/          # Optional custom MCP tools
    └── __init__.py
```

## Quick Start

### 1. Install Prerequisites

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Restart terminal after installation
```

### 2. Initialize MCP Server

```bash
cd ~/Projects/Alpaca/mcp-trading
uvx alpaca-mcp-server init
```

This will prompt for your Alpaca API keys. Use the same keys from `../config.py`.

### 3. Configure Claude Code

Add the MCP server to Claude Code:

```bash
claude mcp add alpaca --scope user --transport stdio uvx alpaca-mcp-server serve \
  --env ALPACA_API_KEY=YOUR_KEY \
  --env ALPACA_SECRET_KEY=YOUR_SECRET
```

Or manually edit `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "alpaca": {
      "type": "stdio",
      "command": "uvx",
      "args": ["alpaca-mcp-server", "serve"],
      "env": {
        "ALPACA_API_KEY": "your_paper_key",
        "ALPACA_SECRET_KEY": "your_paper_secret"
      }
    }
  }
}
```

### 4. Verify Installation

```bash
claude
> /mcp
```

You should see the `alpaca` server listed with available tools.

## Available Commands (Examples)

### Basic Trading
- "What's my current account balance?"
- "Show me my positions"
- "Buy 5 shares of AAPL at market price"
- "Sell 10 shares of TSLA with a limit price of $300"
- "Cancel all open orders"

### Market Data
- "What's the latest quote for NVDA?"
- "Show me AAPL's daily price history for the last 5 days"
- "What was the closing price of TSLA yesterday?"

### Options Trading
- "Show me available option contracts for AAPL expiring next month"
- "What are the option Greeks for TSLA250620P00500000?"
- "Place a bull call spread using AAPL June options"

### Crypto Trading
- "Buy 0.01 BTC/USD at market"
- "Place a limit order to sell 0.01 ETH/USD at $110,000"

### Advanced
- "Get today's market clock and show me my buying power"
- "Show me recent dividends for AAPL, MSFT, and GOOGL"

## Switching Between Paper and Live

### Paper Trading (Default)
```
ALPACA_PAPER_TRADE=True
```

### Live Trading
Update the environment variables in the MCP configuration:
```
ALPACA_API_KEY=your_live_key
ALPACA_SECRET_KEY=your_live_secret
ALPACA_PAPER_TRADE=False
```

**IMPORTANT**: The MCP client config overrides the `.env` file.

## API Reference

The MCP server provides these tools:

### Account & Positions
- `get_account_info()` - View balance, margin, status
- `get_all_positions()` - List all holdings
- `get_open_position(symbol)` - Specific position details

### Trading
- `place_stock_order()` - Market, limit, stop, stop-limit, trailing-stop
- `place_crypto_order()` - Crypto market/limit orders
- `place_option_order()` - Single or multi-leg options
- `cancel_order_by_id()` - Cancel specific order
- `cancel_all_orders()` - Cancel all open orders
- `close_position()` - Close part or all of position

### Market Data
- `get_stock_bars()` - Historical OHLCV data
- `get_stock_latest_quote()` - Real-time bid/ask
- `get_stock_snapshot()` - Comprehensive snapshot
- `get_crypto_bars()` - Crypto historical data
- `get_option_contracts()` - Search options
- `get_option_snapshot()` - Option Greeks and quotes

### Market Info
- `get_clock()` - Market open/close status
- `get_calendar()` - Trading days and holidays
- `get_corporate_actions()` - Dividends, splits, earnings

## Security Notes

1. **API Keys**: Treat as sensitive credentials
2. **Review Orders**: Always review AI-proposed trades before execution
3. **Paper First**: Test thoroughly in paper mode
4. **Complex Strategies**: Be extra careful with multi-leg options

## Troubleshooting

### uv/uvx not found
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
# Restart terminal
```

### Server not appearing in Claude Code
```bash
claude mcp list
claude mcp add alpaca --scope user --transport stdio uvx alpaca-mcp-server serve
```

### Credentials not working
- Check that API keys are correct
- Ensure MCP client config has the right environment variables
- MCP client env overrides .env file

## Resources

- [Alpaca MCP Server GitHub](https://github.com/alpacahq/alpaca-mcp-server)
- [Alpaca Documentation](https://alpaca.markets/learn)
- [Model Context Protocol](https://modelcontextprotocol.io)
