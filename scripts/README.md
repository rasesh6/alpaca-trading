# Alpaca Trading Scripts

Quick execution scripts for common trading patterns. No prompts, instant execution.

## Available Scripts

### `scalp.py` - Quick Scalp with Auto-Profit
Buy at bid, auto-sell at profit target.

```bash
# Basic usage
python scalp.py SYMBOL QUANTITY PROFIT_TARGET

# Examples
python scalp.py SOXL 100 0.10          # Buy 100 SOXL, sell at +$0.10
python scalp.py AAPL 10 0.05           # Buy 10 AAPL, sell at +$0.05
python scalp.py SPY 5 0.25 --timeout 30  # 30 second fill timeout

# Options
--timeout SECONDS      Fill timeout (default: 15)
--sell-timeout SECONDS Sell order timeout (default: 300)
--limit-offset AMOUNT  Buy at bid + offset
--live                 Use live trading
--no-sell              Don't auto-sell
--verbose              Detailed output
```

### `bracket.py` - Bracket Order (Entry + TP + SL)
Place entry order with automatic take profit and stop loss.

```bash
# Basic usage (dollar offsets)
python bracket.py SYMBOL QUANTITY [TP_OFFSET] [SL_OFFSET]

# Examples
python bracket.py SOXL 100 0.50 0.25    # TP +$0.50, SL -$0.25
python bracket.py AAPL 10 1.0 0.5       # TP +$1.00, SL -$0.50

# Percentage-based
python bracket.py SPY 5 --tp-pct 1 --sl-pct 0.5  # TP +1%, SL -0.5%

# Market entry
python bracket.py SOXL 100 0.50 0.25 --market

# Options
--market              Use market order for entry
--limit PRICE         Use limit order at specified price
--tp-pct PCT          Take profit as percentage
--sl-pct PCT          Stop loss as percentage
--live                Use live trading
```

### `quote.py` - Quick Quote Lookup
Get current bid/ask for one or more symbols.

```bash
python quote.py SYMBOL [SYMBOL ...]

# Examples
python quote.py SOXL
python quote.py AAPL MSFT GOOGL
```

### `position.py` - Position Management
View and manage open positions.

```bash
# Show all positions
python position.py

# Close specific position
python position.py close SOXL

# Close partial position
python position.py close SOXL 50      # Close 50%

# Close all positions
python position.py close-all

# Options
--live                Use live trading
```

## Quick Reference

| Task | Command |
|------|---------|
| Scalp 100 SOXL for $0.10 profit | `python scalp.py SOXL 100 0.10` |
| Bracket order with TP/SL | `python bracket.py SOXL 100 0.50 0.25` |
| Get quote | `python quote.py SOXL` |
| Show positions | `python position.py` |
| Close position | `python position.py close SOXL` |

## Paper vs Live

All scripts default to **paper trading**. Use `--live` flag for live trading.

```bash
# Paper (default)
python scalp.py SOXL 100 0.10

# Live
python scalp.py SOXL 100 0.10 --live
```

## Workflow Example

```bash
# 1. Check quote
python quote.py SOXL

# 2. Check positions
python position.py

# 3. Execute scalp
python scalp.py SOXL 100 0.10

# 4. Check result
python position.py

# 5. Close if needed
python position.py close SOXL
```

## Tips

1. **Test in paper first** - All scripts default to paper trading
2. **Use verbose mode** - Add `--verbose` or `-v` for detailed output
3. **Quick quotes** - Use `quote.py` for instant price checks
4. **Monitor positions** - Use `position.py` to track P/L
5. **Set appropriate timeouts** - Use `--timeout` for volatile stocks
