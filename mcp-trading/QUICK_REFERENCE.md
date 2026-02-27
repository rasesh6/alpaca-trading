# MCP Trading Quick Reference

## Account & Portfolio

| Command | Description |
|---------|-------------|
| "What's my account balance?" | View account details |
| "Show me my positions" | List all holdings |
| "What's my buying power?" | Check available funds |
| "Show me my portfolio history" | View P/L over time |

## Stock Orders

| Command | Description |
|---------|-------------|
| "Buy 5 shares of AAPL at market" | Market buy order |
| "Sell 10 TSLA with limit $300" | Limit sell order |
| "Buy 100 MSFT at $450 limit" | Limit buy order |
| "Cancel all open orders" | Cancel everything |
| "Cancel order abc123" | Cancel specific order |
| "Close my GOOGL position" | Liquidate position |
| "Close 50% of my NVDA position" | Partial close |

## Stop Orders

| Command | Description |
|---------|-------------|
| "Buy 10 AAPL with stop at $180" | Stop market order |
| "Sell 5 TSLA stop-limit at $280, limit $279" | Stop-limit order |
| "Place trailing stop on NVDA, 2% trail" | Trailing stop % |
| "Trailing stop on MSFT, $5 trail amount" | Trailing stop $ |

## Market Data

| Command | Description |
|---------|-------------|
| "What's the latest quote for NVDA?" | Real-time bid/ask |
| "Show AAPL price history for 5 days" | Historical bars |
| "What was TSLA's closing price yesterday?" | Specific data |
| "Get a snapshot of MSFT" | Comprehensive view |
| "Show me 1-minute bars for AMZN last 2 hours" | Intraday data |

## Options

| Command | Description |
|---------|-------------|
| "Show AAPL options expiring next month" | List contracts |
| "Get Greeks for AAPL250613C00200000" | Option Greeks |
| "Buy 1 AAPL call expiring next Friday" | Single leg |
| "Place bull call spread on SPY" | Multi-leg strategy |

## Crypto

| Command | Description |
|---------|-------------|
| "Buy 0.01 BTC/USD at market" | Market crypto buy |
| "Sell 0.01 ETH/USD limit $110,000" | Limit crypto sell |

## Market Info

| Command | Description |
|---------|-------------|
| "Is the market open?" | Market status |
| "Show me the market calendar for next week" | Trading days |
| "Recent dividends for AAPL, MSFT" | Corporate actions |

## Combined Commands

| Command | Description |
|---------|-------------|
| "Check market status and show my balance, then buy 5 AAPL" | Multi-step |
| "If TSLA is above $300, sell my position" | Conditional |
| "Show my positions and their P/L" | Portfolio review |

## Tips

1. **Be specific**: "Buy 5 shares of AAPL at market" vs "buy aapl"
2. **Review before confirm**: AI will show order details
3. **Use paper first**: Test all commands in paper mode
4. **Check status**: "Show my open orders" after placing

## Paper vs Live

The MCP server uses the credentials configured in `config.json`.
- `config.json` = Paper trading (default)
- `config.live.json` = Live trading

To switch, update `~/.claude/settings.json` with the appropriate credentials.
