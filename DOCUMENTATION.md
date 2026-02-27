# Trading Systems Documentation

> **Last Updated:** 2026-02-25
> **Status:** Alpaca Trading - ALL FEATURES WORKING
> **New:** Real-time streaming quotes via WebSocket (IEX feed)
> **Research:** Order types for market open/close volatility (not yet implemented)

## Quick Start for New Sessions

1. Read this file first for full context
2. Start the server: `cd ~/Projects/Alpaca && python server.py`
3. Open http://localhost:5001
4. Toggle between Paper/Live mode directly in the UI header

## Current Status (2026-02-25)

### ✅ NEW: Real-Time Streaming Quotes

WebSocket market data streaming for live quotes without pressing "Get Quote" button.

**Key Benefits:**
- Real-time quote updates automatically in UI
- Does NOT count towards API rate limits (separate WebSocket subscription limit)
- IEX data feed (free with Basic plan) - covers ~20% of US market volume
- Up to 30 concurrent symbol subscriptions on Basic plan
- Price flash animation provides visual feedback on updates

**How to Use:**
1. Enter a symbol in the Quote input field
2. Click "Stream" button to start real-time quotes
3. Button changes to "Stop" and "STREAMING" badge appears
4. Click "Stop" to end streaming for that symbol
5. Switching symbols auto-unsubscribes from previous symbol

**Architecture Flow:**
```
Alpaca Market Data WS (IEX) → market_data_streaming.py → SSE /api/stream → Frontend UI
```

### WebSocket vs REST API Rate Limits (IMPORTANT)

**WebSocket subscriptions are SEPARATE from REST API rate limits!**

| Plan | REST API Rate Limit | WebSocket Symbol Subscriptions | Data Feed |
|------|---------------------|-------------------------------|-----------|
| Basic (free) | 200 calls/min | 30 symbols max | IEX only |
| Algo Trader Plus ($99/mo) | 10,000 calls/min | Unlimited | Full SIP |

**Key Insight:** Streaming quotes via WebSocket does NOT count towards your 200 API calls/min limit. This means you can have real-time quotes without worrying about rate limits.

### Current File Structure
```
Alpaca/
├── config.py                  # API credentials and trading mode (paper/live)
├── alpaca_client.py           # REST API wrapper (orders, positions, quotes)
├── streaming.py               # Trade updates WebSocket (order fills, status)
├── market_data_streaming.py   # Market data WebSocket (real-time quotes) [NEW]
├── server.py                  # Flask web server + SSE broadcasting
├── templates/
│   └── index.html            # Main UI template
├── static/
│   ├── css/
│   │   └── style.css         # UI styles (dark theme, streaming badge)
│   └── js/
│       └── app.js            # Frontend application (SSE, streaming quotes)
└── DOCUMENTATION.md          # This file
```

### Current API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Main UI |
| `/api/stream` | GET | SSE endpoint for real-time updates |
| `/api/account` | GET | Account details (cash, buying power) |
| `/api/positions` | GET | All open positions |
| `/api/quote/<symbol>` | GET | Snapshot quote (REST API) |
| `/api/quotes/subscribe` | POST | Subscribe to streaming quotes |
| `/api/quotes/unsubscribe` | POST | Unsubscribe from streaming quotes |
| `/api/quotes/subscriptions` | GET | Get active subscriptions + stream status |
| `/api/orders` | GET | Get orders (open by default, includes held) |
| `/api/orders/<id>` | GET | Get specific order |
| `/api/orders/place` | POST | Place order with optional exit strategy |
| `/api/orders/<id>/cancel` | POST | Cancel order |
| `/api/orders/<id>/fill-status` | GET | Check fill status |
| `/api/exit-strategy/<id>/check-trigger` | GET | Check trigger price for exit strategy |
| `/api/mode` | GET/POST | Get/Set trading mode (paper/live) |

### ✅ All Exit Strategies Working

| Strategy | Status | Notes |
|----------|--------|-------|
| Bracket (TP + SL) | ✅ Working | Uses Alpaca native bracket orders |
| Profit Target | ✅ Working | Places limit sell on fill |
| Confirmation Stop | ✅ Working | Wait for trigger, place stop-limit |
| Trailing Stop | ✅ Working | Wait for trigger, place trailing stop |

### Recent Fixes Applied

1. **Exit strategy persistence** - Strategies now survive Flask restarts via `/tmp/alpaca_exit_strategies.json`
2. **Bracket orders** - Using Alpaca's native bracket orders (atomic TP + SL)
3. **Held orders visibility** - Stop-limit orders (status "held") now show in open orders
4. **Trailing stop error handling** - UI now shows actual errors (min trail = 0.1% of price)
5. **Trigger status persistence** - Status changes to `waiting_trigger` are now persisted
6. **Robust trigger checking** - Auto-updates status if order fills before status is updated

### Known Limitations

- **Trailing stop minimum**: Alpaca requires trail amount >= 0.1% of stock price
- **No automated tests**: Manual testing only
- **Browser-dependent monitoring**: Trailing stop monitoring stops if browser is closed
- **IEX data only**: Basic plan only covers ~20% of market volume (IEX exchange)
- **30 symbol limit**: Basic plan limits to 30 concurrent streaming subscriptions
- **State persistence**: Uses `/tmp` files which don't persist on Railway deployments

### Future Improvements

1. **State Persistence**: Move from `/tmp` files to database for Railway deployment
2. **SIP Data**: Upgrade to Algo Trader Plus ($99/mo) for full market data
3. **Multi-symbol streaming**: Allow streaming multiple symbols simultaneously
4. **Authentication**: Add user authentication for multi-user support
5. **Price Alerts**: Add configurable price alerts with notifications
6. **Historical Charts**: Add price chart visualization
7. **Volatility Order Types** (Research completed, not yet implemented):
   - IOC/FOK options for volatility management
   - MOO/LOO for market open volatility
   - MOC/LOC for market close positioning
   - Extended hours trading toggle

---

## Project Locations

| Project | Path | Status |
|---------|------|--------|
| E*TRADE | `~/Projects/etrade` | Legacy (API reliability issues) |
| Alpaca | `~/Projects/Alpaca` | **Active** (Paper → Live tomorrow) |

---

## E*TRADE System

### Architecture
```
etrade/
├── server.py              # Flask server with REST API
├── etrade_client.py       # OAuth 1.0a API wrapper
├── token_manager.py       # Redis-based token storage
├── trailing_stop_manager.py # Exit strategy management
├── config.py              # Configuration (gitignored)
├── templates/index.html   # Web UI
├── static/js/app.js       # Frontend logic
└── static/css/style-luxe.css # Styling
```

### Authentication
- **Type**: OAuth 1.0a (complex)
- **Flow**: Request token → Authorize URL → Verifier → Access token
- **Storage**: Redis on Railway (tokens persist across restarts)
- **Token Lifetime**: ~2 hours, auto-refresh handled

### API Issues
- **Intermittent 500 errors** on orders endpoint
- Error message: "The requested service is not currently available"
- Quote API works while orders API fails (endpoint-specific outages)
- Observed ~45 second outages during testing

### Exit Strategies Implemented
1. **Profit Target**: Simple limit sell at %/$ above fill price
2. **Confirmation Stop Limit**: Wait for trigger price, place STOP LIMIT order
3. **Trailing Stop Limit ($)**: Wait for trigger price, place TRAILING_STOP_CNST order

### E*TRADE Order Types
- `MARKET` - Market order
- `LIMIT` - Limit order
- `STOP` - Stop market order
- `STOP_LIMIT` - Stop limit order
- `TRAILING_STOP_CNST` - Trailing stop (uses stopPrice for trail amount, stopLimitPrice for limit offset)

### Key Endpoints
```
GET  /                              # Main UI
GET  /api/auth/status               # Check auth status
POST /api/auth/login                # Start OAuth flow
GET  /api/accounts                  # List accounts
GET  /api/accounts/{id}/balance     # Get balance
GET  /api/accounts/{id}/positions   # Get positions
GET  /api/accounts/{id}/orders      # Get orders
POST /api/orders/place              # Place order
POST /api/orders/{id}/cancel        # Cancel order
GET  /api/quote/{symbol}            # Get quote
```

### Deployment
- **Platform**: Railway
- **URL**: https://etrade-trading.up.railway.app
- **Redis**: Used for token storage

---

## Alpaca System

### Architecture
```
Alpaca/
├── server.py              # Flask server with REST API + SSE
├── alpaca_client.py       # Alpaca SDK wrapper (REST API)
├── streaming.py           # Trade updates WebSocket (order fills)
├── market_data_streaming.py # Market data WebSocket (real-time quotes) [NEW]
├── config.py              # Credentials + mode persistence
├── templates/index.html   # Web UI
├── static/js/app.js       # Frontend logic with SSE + streaming
└── static/css/style.css   # Dark theme styling
```

### Two Separate WebSocket Connections

1. **Trade Updates WebSocket** (`streaming.py`)
   - URL: `wss://paper-api.alpaca.markets/stream` (paper)
   - URL: `wss://api.alpaca.markets/stream` (live)
   - Purpose: Real-time order status updates (fills, cancellations)
   - Used for: Exit strategy execution

2. **Market Data WebSocket** (`market_data_streaming.py`) [NEW]
   - URL: `wss://stream.data.alpaca.markets/v2/iex` (Basic plan)
   - URL: `wss://stream.data.alpaca.markets/v2/sip` (Algo Trader Plus)
   - Purpose: Real-time quote updates
   - Used for: Live streaming quotes in UI

### Authentication
- **Type**: API Keys (simple)
- **Headers**: `APCA-API-KEY-ID` and `APCA-API-SECRET-KEY`
- **No OAuth dance required**

### Credentials (Paper Trading) - CURRENT
```
Paper endpoint: https://paper-api.alpaca.markets
Paper Key: PKCDLH6JNAUB2NXXE3THXHHSHG
Paper Secret: 5v1dmhhjbXZWkgk6rm99VjTHS49J6MF8jGFkVDGzByYD
```

### Credentials (Live Trading) - READY FOR TOMORROW
```
Live endpoint: https://api.alpaca.markets
Live Key: AKCZ3G6PIQJP4WX5TNK2EOOLVE
Live Secret: 7VJ1jxaHU6Wqi7xHcy8rdR6j1wuLM1mZJ1yWgSa9StrM
```

### Switching to Live Trading

1. Stop the server (Ctrl+C)
2. Edit `config.py`:
   ```python
   USE_PAPER = False  # Change from True to False
   ```
3. Restart the server: `python server.py`
4. Verify "LIVE" badge shows in UI header

**IMPORTANT:** Test thoroughly in paper mode first! All strategies are working in paper.

### Alpaca API Reliability
- **Uptime**: 99.9% claimed
- **Latency**: ~1.5ms order processing
- **No OAuth complexity**
- **Official Python SDK**: `alpaca-trade-api`

### WebSocket Streaming
Alpaca provides real-time trade updates via WebSocket, eliminating the need for polling.

**WebSocket URLs:**
- Paper: `wss://paper-api.alpaca.markets/stream`
- Live: `wss://api.alpaca.markets/stream`

**Implementation:**
1. `streaming.py` - WebSocket client that connects and subscribes to `trade_updates`
2. `server.py` - SSE endpoint at `/api/stream` pushes updates to frontend
3. `app.js` - EventSource connection receives real-time updates

**Trade Events:**
- `new` - Order created
- `fill` - Order completely filled
- `partial_fill` - Order partially filled
- `canceled` - Order cancelled
- `expired` - Order expired
- `rejected` - Order rejected

**Flow:**
```
Alpaca WebSocket → streaming.py → server.py callback → SSE broadcast → Frontend EventSource
```

**Hybrid Approach:**
- WebSocket/SSE for real-time fill notifications (instant updates)
- Polling as backup for fill timeout and trigger monitoring (reliability)
- UI refreshes automatically on both fill detection and cancellation

### Exit Strategies
1. **Bracket (Immediate TP + SL)**: Native Alpaca bracket order with take profit and stop loss
2. **Profit Target**: On fill, immediately place LIMIT SELL at fill_price + offset ($ or %)
3. **Confirmation Stop Limit**: Wait for trigger price, then place STOP LIMIT order
4. **Trailing Stop Limit**: Wait for trigger price, then place TRAILING STOP order

**Limit Price Options:**
- Manual Entry: Enter specific price
- Use Bid Price: Fetch current bid and use as limit price
- Use Ask Price: Fetch current ask and use as limit price

**Monitoring Features:**
- Real-time status display with countdown timer
- Console logging for debugging (F12 → Console)
- Fill timeout with automatic order cancellation
- Clear feedback: "Order cancelled" or "Cancel failed"

### Key Endpoints
```
GET  /                         # Main UI
GET  /api/stream               # SSE endpoint for real-time updates
GET  /api/account              # Account details
GET  /api/positions            # All positions
GET  /api/quote/{symbol}       # Get quote
GET  /api/orders               # Get orders
POST /api/orders/place         # Place order (any type)
POST /api/orders/{id}/cancel   # Cancel order
GET  /api/orders/{id}/fill-status  # Check fill status
GET  /api/exit-strategy/{id}/check-trigger  # Check trigger price
```

### Running Locally
```bash
cd ~/Projects/Alpaca
pip install -r requirements.txt
python server.py
# Open http://localhost:5001
```

**Requirements:**
- `alpaca-trade-api` - Official Alpaca SDK
- `flask` - Web server
- `websocket-client` - WebSocket streaming

### Deployment (Future)
- **Platform**: Railway (same as E*TRADE)
- **Procfile**: Already created
- **requirements.txt**: Already created
- **Note**: WebSocket connection starts automatically on server startup

---

## Exit Strategy Logic (Alpaca)

### Bracket Order (Native)
Alpaca supports native bracket orders with immediate TP + SL:
- Place order with `order_class: 'bracket'`
- `take_profit: {limit_price: X}` - limit order for profit target
- `stop_loss: {stop_price: Y, limit_price: Z}` - stop-limit order for loss limit
- Executed atomically on Alpaca's servers, no client-side monitoring needed
- For market orders, entry price is estimated from current quote (bid/ask)

**Implementation Details:**
- Entry order + TP + SL are placed as a single atomic unit
- Alpaca handles the coordination - no "insufficient qty" errors
- TP is a limit order at entry_price + offset
- SL is a stop-limit with stop at entry_price - offset, limit slightly below stop
- For BUY: TP above entry (profit), SL below entry (loss limit)
- For SELL (short): TP below entry (profit when drops), SL above entry (loss limit)

### Profit Target
1. Place BUY order (market or limit)
2. Monitor for fill (every 1s via polling, WebSocket notification as backup)
3. On fill timeout → cancel order, show "Order cancelled"
4. On fill → immediately place LIMIT SELL:
   - profit_price = fill_price + offset (dollar or percent)
   - Example: Fill @ $65.00, offset $0.50 → Sell @ $65.50

### Confirmation Stop Limit
1. Place BUY order (market or limit)
2. Monitor for fill (every 1s via polling, WebSocket notification as backup)
3. On fill timeout → cancel order, show "Order cancelled"
4. On fill → calculate trigger_price = fill_price + trigger_offset
5. Poll current price (every 1s, timeout = trigger_timeout)
6. When price >= trigger_price → place STOP_LIMIT sell:
   - stop_price = current_price - stop_offset
   - limit_price = stop_price - $0.01

### Trailing Stop Limit
1. Place BUY order (market or limit)
2. Monitor for fill (every 1s via polling, WebSocket notification as backup)
3. On fill timeout → cancel order, show "Order cancelled"
4. On fill → calculate trigger_price = fill_price + trigger_offset
5. Poll current price (every 1s, timeout = trigger_timeout)
6. When price >= trigger_price → place TRAILING_STOP sell:
   - trail_price = trail_amount (dollar) or trail_percent (percentage)
   - Automatically follows price up

### Timeout Handling
- Fill timeout: Cancel order, show "⚠️ Fill timeout. Order cancelled."
- Trigger timeout: Position remains open without stop, show warning
- All timeouts count wall-clock time (even during API errors)
- 500ms delay after cancellation before UI refresh (ensures Alpaca processes it)

---

## Key Differences

| Feature | E*TRADE | Alpaca |
|---------|---------|--------|
| Auth | OAuth 1.0a | API Keys |
| Reliability | Intermittent 500s | 99.9% uptime |
| Latency | Variable | ~1.5ms |
| SDK | Custom | Official Python |
| Real-time Updates | Polling | WebSocket + SSE |
| Bracket Orders | Manual monitoring | Native support |
| Trailing Stop | TRAILING_STOP_CNST | Native trail_price |
| Token Storage | Redis | Not needed |
| Deployment | Railway | Local (Railway planned) |

---

## Development Notes

### Alpaca-Specific Notes

**Console Debugging:**
Browser console (F12) shows detailed monitoring logs:
```
SSE connected
Starting Confirmation Stop monitoring for order xxx, fill timeout: 15s
Fill check: 1/15s {filled: false, status: 'accepted'}
...
Fill timeout reached, cancelling order xxx
Cancel result: {success: true, ...}
```

**Hybrid Monitoring:**
- WebSocket receives fill events instantly (real-time)
- Polling checks fill status every 1s (backup + timeout tracking)
- Both work together for reliability

**UI Refresh Timing:**
- 500ms delay after cancel before refreshing (Alpaca processing time)
- 30s background refresh (down from 5s, since SSE provides real-time)

### Polling Rate
- All polling uses 1 second intervals (`setInterval(fn, 1000)`)
- This prevents rate limiting issues

### Fill Detection (E*TRADE)
E*TRADE returns filledQuantity at Instrument level, not OrderDetail:
```
Order → OrderDetail[] → Instrument[] → filledQuantity
```

### Error Handling Pattern
```javascript
if (data.api_error) {
    elapsed++;
    updateStatus(`API error (${elapsed}/${timeout}s)`);
    if (elapsed >= timeout) {
        // Handle timeout
    }
    return;
}
```

### CSS Variables (style-luxe.css)
```css
--bg-void: #0a0a0b;
--bg-base: #0f0f11;
--accent-gold: #c9a227;
--bull: #22c55e;
--bear: #ef4444;
--text-primary: #fafafa;
--text-secondary: #b8b8c0;
```

---

---

## Alpaca API Reference

### Order Types

| Type | Description | Required Fields |
|------|-------------|-----------------|
| `market` | Execute immediately at best available price | symbol, qty, side, type='market' |
| `limit` | Execute at specified price or better | symbol, qty, side, type='limit', limit_price |
| `stop` | Market order triggered at stop price | symbol, qty, side, type='stop', stop_price |
| `stop_limit` | Limit order triggered at stop price | symbol, qty, side, type='stop_limit', stop_price, limit_price |
| `trailing_stop` | Follows price by trail amount | symbol, qty, side, type='trailing_stop', trail_price OR trail_percent |

### Order Classes (Advanced Orders)

| Class | Description | Usage |
|-------|-------------|-------|
| `bracket` | Entry + TP + SL in one atomic order | `order_class: 'bracket'` + `take_profit` + `stop_loss` |
| `oco` | One-Cancels-Other (TP limit + SL stop-limit) | `order_class: 'oco'` - both legs must be limit orders |
| `oto` | One-Triggers-Other | `order_class: 'oto'` - second order triggers after first fills |

### Bracket Order Structure
```python
{
    'symbol': 'AAPL',
    'qty': 10,
    'side': 'buy',
    'type': 'market',  # or 'limit' with limit_price
    'time_in_force': 'day',
    'order_class': 'bracket',
    'take_profit': {'limit_price': '175.00'},  # TP price
    'stop_loss': {
        'stop_price': '170.00',     # Trigger price
        'limit_price': '169.99'     # Limit price (slightly worse to ensure fill)
    }
}
```

### Trailing Stop Parameters
```python
{
    'type': 'trailing_stop',
    'trail_price': '0.50',      # Dollar trail amount
    # OR
    'trail_percent': '1.0',     # Percentage trail
    'hwm': '175.00'             # Optional: High water mark reference
}
```

### Time-in-Force Options

| TIF | Description |
|-----|-------------|
| `day` | Valid until market close (default) |
| `gtc` | Good-til-cancelled |
| `opg` | Market-on-open (only for session='regt') |
| `cls` | Market-on-close |
| `ioc` | Immediate-or-cancel (fill what you can) |
| `fok` | Fill-or-kill (all or nothing) |

### Order Statuses

| Status | Description |
|--------|-------------|
| `new` | Order accepted, waiting to fill |
| `held` | Stop/stop-limit order waiting for trigger |
| `partially_filled` | Partially executed |
| `filled` | Completely executed |
| `canceled` | Cancelled by user or system |
| `expired` | Order expired (end of day for 'day' TIF) |
| `rejected` | Rejected by exchange |
| `pending_new` | Being processed |
| `pending_cancel` | Cancellation in progress |
| `pending_replace` | Modification in progress |

### Important Notes

1. **Bracket orders are atomic**: TP and SL are placed together with entry, avoiding "insufficient qty" errors
2. **OCO requires both legs to be limit orders**: Cannot use stop-limit for SL in OCO
3. **Stop-loss needs limit_price**: Alpaca requires both stop_price and limit_price for stop-limit
4. **Held orders**: Stop/stop-limit orders show status "held" not "open" - must include in orders list

---

## Order Types for Market Open/Close Volatility (Research)

> **Status:** Research completed, NOT YET IMPLEMENTED
> **Purpose:** Document order types useful during market open/close when there's heavy volume and price swings

### Market Timing Order Types

| Order Type | Code | Description | Best For |
|------------|------|-------------|----------|
| **Market-On-Open** | MOO | Executes at opening auction price | Capturing opening volatility |
| **Market-On-Close** | MOC | Executes at closing auction price | End-of-day exits/entries |
| **Limit-On-Open** | LOO | Limit order at opening auction | Opening with price protection |
| **Limit-On-Close** | LOC | Limit order at closing auction | Closing with price protection |

### Time-in-Force for Volatility Management

| TIF | Description | Volatility Use Case |
|-----|-------------|---------------------|
| **IOC** (Immediate or Cancel) | Fill what you can immediately, cancel rest | High volatility - partial fills acceptable |
| **FOK** (Fill or Kill) | All or nothing - must fill completely | Risk management - exact position size required |
| **OPG** (Opening) | Only executes at market open | MOO/LOO orders |
| **CLS** (Closing) | Only executes at market close | MOC/LOC orders |

### Extended Hours Trading

Alpaca supports extended hours trading with limitations:

| Session | Time (ET) | Requirements |
|---------|-----------|--------------|
| Pre-market | 4:00am - 9:30am | LIMIT orders only, DAY TIF, `extended_hours=True` |
| Regular | 9:30am - 4:00pm | All order types |
| After-hours | 4:00pm - 8:00pm | LIMIT orders only, DAY TIF, `extended_hours=True` |

**Important Extended Hours Rules:**
- Only LIMIT orders with `time_in_force='day'` supported
- Must set `extended_hours=True` in order request
- Unfilled overnight orders transition to pre-market session
- Orders unfilled by 8 PM ET are canceled

### Volatility Strategy Recommendations

#### At Market Open (9:30am ET)

**Scenario: Heavy volume, large price swings**

1. **MOO (Market-On-Open)** - `time_in_force='opg'`
   - Captures opening price volatility
   - No price protection - fills at auction price
   - Best for: Strong directional conviction

2. **LOO (Limit-On-Open)** - `time_in_force='opg'` with `limit_price`
   - Price protection at open
   - May not fill if price gaps past limit
   - Best for: Want opening execution but with price cap

3. **IOC (Immediate or Cancel)**
   - Partial fills acceptable during volatile opens
   - Avoids leaving orders in book during rapid moves
   - Best for: Large orders, uncertain liquidity

#### At Market Close (4:00pm ET)

**Scenario: End-of-day positioning, MOC imbalances**

1. **MOC (Market-On-Close)** - `time_in_force='cls'`
   - NYSE deadline: 15:50 ET
   - Nasdaq deadline: 15:55 ET
   - Cannot cancel after 15:45 ET (NYSE)
   - Best for: Must close position by end of day

2. **LOC (Limit-On-Close)** - `time_in_force='cls'` with `limit_price`
   - Price protection at close
   - Best for: Want closing execution with price cap

3. **Bracket Orders Before Close**
   - Set TP/SL before volatile close
   - Protects against end-of-day swings
   - Best for: Existing positions needing protection

### Python Implementation Examples

```python
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest, TrailingStopOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass

# Market-On-Open (MOO)
moo_order = LimitOrderRequest(
    symbol="SPY",
    qty=10,
    side=OrderSide.BUY,
    limit_price=450.00,  # Optional protection
    time_in_force=TimeInForce.OPG  # Opening auction only
)

# Market-On-Close (MOC)
moc_order = MarketOrderRequest(
    symbol="SPY",
    qty=10,
    side=OrderSide.SELL,
    time_in_force=TimeInForce.CLS  # Closing auction only
)

# Extended Hours (Pre-market/After-hours)
extended_order = LimitOrderRequest(
    symbol="SPY",
    qty=10,
    side=OrderSide.BUY,
    limit_price=450.00,
    time_in_force=TimeInForce.DAY,
    extended_hours=True  # Required for extended hours
)

# IOC during high volatility
ioc_order = LimitOrderRequest(
    symbol="SPY",
    qty=100,
    side=OrderSide.BUY,
    limit_price=450.00,
    time_in_force=TimeInForce.IOC  # Fill what you can, cancel rest
)

# FOK for exact position sizing
fok_order = LimitOrderRequest(
    symbol="SPY",
    qty=100,
    side=OrderSide.BUY,
    limit_price=450.00,
    time_in_force=TimeInForce.FOK  # All or nothing
)
```

### Key Findings for Implementation

1. **MOO/MOC Orders**: Use `time_in_force='opg'` or `'cls'` - simple to implement
2. **Extended Hours**: Just add `extended_hours=True` to limit orders
3. **IOC/FOK**: Already available in Alpaca - just need UI option
4. **Bracket Before Volatility**: Already implemented - useful before market open/close

### Recommended Implementation Priority

| Priority | Feature | Effort | Impact |
|----------|---------|--------|--------|
| 1 | IOC/FOK option in UI | Low | High - manage volatility risk |
| 2 | Extended hours toggle | Low | Medium - pre-market entries |
| 3 | MOO/LOO order type | Medium | High - capture opening volatility |
| 4 | MOC/LOC order type | Medium | Medium - closing positions |
| 5 | Volatility alerts | High | Medium - notify on high volatility |

### Risk Management During Volatility

1. **Use wider stops** during market open (first 15-30 min)
2. **Avoid market orders** in first/last 15 minutes if possible
3. **Use bracket orders** to automate TP/SL during volatile periods
4. **Consider IOC** for large orders to avoid slippage
5. **Monitor bid-ask spreads** - widen during volatility

---

## Session History & Fixes

### 2026-02-24: All Exit Strategies Working

**Complete testing confirmed all strategies working:**
- ✅ Bracket orders (native Alpaca bracket with TP + SL)
- ✅ Profit target (limit sell on fill)
- ✅ Confirmation stop limit (trigger → stop-limit)
- ✅ Trailing stop (trigger → trailing stop)

**Additional fixes:**
1. **Trailing stop error visibility** - UI now shows actual error when trailing stop fails (e.g., "trail_price must be >= 0.1% of stock price")
2. **Trail amount minimum** - Updated HTML input minimum to $0.07 and added note about 0.1% minimum
3. **Position details color** - Changed from tertiary to secondary text color for better visibility

### 2026-02-24: Bracket Order Fixes

**Problem 1: Exit strategies lost on Flask restart**
- Flask debug mode runs in dual-process mode, which clears in-memory `_pending_exit_strategies`
- Orders filled but no TP/SL placed: "No exit strategy found for filled order"

**Fix:** Added persistence to `/tmp/alpaca_exit_strategies.json`
```python
EXIT_STRATEGIES_FILE = '/tmp/alpaca_exit_strategies.json'

def _load_exit_strategies():
    global _pending_exit_strategies
    if os.path.exists(EXIT_STRATEGIES_FILE):
        with open(EXIT_STRATEGIES_FILE, 'r') as f:
            _pending_exit_strategies = json.load(f)

def _save_exit_strategies():
    with open(EXIT_STRATEGIES_FILE, 'w') as f:
        json.dump(_pending_exit_strategies, f, indent=2)

# Load on module import (survives Flask debug reload)
_load_exit_strategies()
```

**Problem 2: "insufficient qty available for order"**
- Tried placing TP and SL separately after fill
- Alpaca reserves shares for first order, second fails

**Fix:** Use native Alpaca bracket orders instead of manual TP/SL placement
- For market orders, estimate fill price from quote (bid for SELL, ask for BUY)
- Calculate TP/SL offsets from estimated fill price
- Single atomic order handles entry + TP + SL

**Problem 3: "oco orders must be limit orders"**
- OCO requires both legs to be limit orders
- Stop-loss is stop-limit, not pure limit
- Cannot use OCO for TP limit + SL stop-limit combination

**Fix:** Use bracket orders (OTOCO) instead of OCO

**Problem 4: SL orders not showing in open orders**
- Stop-limit orders have status "held" not "open"
- `/api/orders` endpoint only fetched "open" orders

**Fix:** Include held orders in open orders response
```python
if status == 'open':
    result = client.get_orders('open')
    held_result = client.get_orders('held')
    if result.get('success') and held_result.get('success'):
        result['orders'].extend(held_result['orders'])
```

**Problem 5: JavaScript error "Cannot read properties of null"**
- Code tried to access non-existent elements `bracket-tp-price` and `bracket-sl-price`
- Actual elements are `bracket-tp-offset` and `bracket-sl-offset`

**Fix:** Removed the problematic code that tried to read non-existent elements

**Problem 6: Trailing stop trigger timeout even when price hit trigger**
- Exit strategy status was not being persisted when updated from `waiting_fill` to `waiting_trigger`
- Check-trigger endpoint returned "Not waiting for trigger" error because status was still `waiting_fill`
- Trigger timeout counted down while backend couldn't process trigger checks

**Fix:**
1. Added `_save_exit_strategies()` calls when status changes to `waiting_trigger`
2. Added `_save_exit_strategies()` when fill_price is set
3. Made check-trigger endpoint more robust - if status is still `waiting_fill`, it checks if order is now filled and updates status automatically

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.5.0 | 2026-02-25 | **VOLATILITY RESEARCH** - Documented order types for market open/close volatility (MOO/MOC/LOO/LOC, IOC/FOK, extended hours), implementation recommendations |
| 1.4.0 | 2026-02-25 | **STREAMING QUOTES** - Added real-time quote streaming via IEX WebSocket, separate from REST API rate limits, Stream/Stop button in UI |
| 1.3.0 | 2026-02-24 | **ALL STRATEGIES WORKING** - Trailing stop error handling, UI fixes, ready for live trading |
| 1.2.0 | 2026-02-24 | Fixed bracket orders using native Alpaca API, added exit strategy persistence, fixed held orders display, fixed JS error |
| 1.1.0 | 2026-02-24 | Added bid/ask limit price selection, fixed profit target implementation |
| 1.0.0 | 2026-02-23 | Alpaca system complete with WebSocket + SSE streaming |
| 0.3.0 | 2026-02-23 | Added all exit strategies (Bracket, Confirmation Stop, Trailing Stop) |
| 0.2.0 | 2026-02-23 | Implemented WebSocket streaming for real-time updates |
| 0.1.0 | 2026-02-23 | Initial Alpaca system (paper trading) |

---

## Ready for Live Trading (2026-02-25)

All features tested and working in paper mode. To switch to live:

```bash
# 1. Stop server
# 2. Edit config.py: USE_PAPER = False
# 3. Restart: python server.py
# 4. Verify "LIVE" badge in UI
```

**Live credentials are in config.py and documented above.**

---

## MCP Trading System (Natural Language)

A separate, independent trading system for AI-powered natural language commands.

### Location
```
~/Projects/Alpaca/mcp-trading/
```

### Features
- Trade using natural language commands
- AI-powered market analysis
- Works with Claude Code, Cursor, VS Code
- Same Alpaca API (paper/live)

### Quick Start
```bash
cd ~/Projects/Alpaca/mcp-trading
./setup.sh
```

### Example Commands
- "What's my account balance?"
- "Buy 5 shares of AAPL at market"
- "Show me NVDA option contracts expiring next month"
- "Place a trailing stop on TSLA with 2% trail"

See `mcp-trading/README.md` and `mcp-trading/QUICK_REFERENCE.md` for details.

---

## Latest Session Changes (2026-02-25)

### New Files Created
- `market_data_streaming.py` - WebSocket client for real-time market data (IEX feed)

### Files Modified
- `server.py` - Added market data streaming integration, quote subscription endpoints, SSE quote broadcasting
- `templates/index.html` - Added Stream/Stop button, streaming badge
- `static/js/app.js` - Added streaming quote handlers, subscribe/unsubscribe functions
- `static/css/style.css` - Added streaming button styles, price flash animation
- `DOCUMENTATION.md` - Updated with streaming quotes documentation

### New API Endpoints
- `POST /api/quotes/subscribe` - Subscribe to real-time quotes
- `POST /api/quotes/unsubscribe` - Unsubscribe from quotes
- `GET /api/quotes/subscriptions` - Get active subscriptions and stream status

### Key Findings
1. **WebSocket subscriptions don't count towards REST API rate limits** - This is a separate quota
2. **Basic plan allows 30 symbol subscriptions** - Currently using IEX feed (free)
3. **SIP feed requires Algo Trader Plus ($99/mo)** - For full market data coverage

---

### E*TRADE Version History (Legacy)
| Version | Date | Changes |
|---------|------|---------|
| 1.6.2 | 2026-02-23 | Fixed timeout to count wall-clock time |
| 1.6.0 | 2026-02-23 | Added Trailing Stop Limit ($) |
| 1.5.0 | 2026-02-22 | Added Confirmation Stop Limit |
| 1.0.0 | 2026-02-20 | Initial E*TRADE system |
