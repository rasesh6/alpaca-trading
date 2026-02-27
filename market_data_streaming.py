"""
Alpaca Market Data WebSocket Streaming

Real-time quote updates via WebSocket (IEX data feed for Basic plan).
WebSocket subscriptions are SEPARATE from REST API rate limits.

Basic Plan Limits:
- 30 concurrent symbol subscriptions
- IEX data only (not full SIP)
- Does NOT count towards 200 API calls/min limit

Algo Trader Plus ($99/mo):
- Unlimited symbol subscriptions
- Full SIP data
- Does NOT count towards 10,000 API calls/min limit
"""
import json
import logging
import threading
import websocket
from config import API_KEY, SECRET_KEY

logger = logging.getLogger(__name__)

# Market Data WebSocket URLs
# IEX: Free with Basic plan (limited symbols, IEX exchange only)
# SIP: Requires Algo Trader Plus subscription ($99/mo)
IEX_WS_URL = "wss://stream.data.alpaca.markets/v2/iex"
SIP_WS_URL = "wss://stream.data.alpaca.markets/v2/sip"


class MarketDataStream:
    """WebSocket client for real-time market data quotes"""

    def __init__(self, use_sip=False):
        self.api_key = API_KEY
        self.secret_key = SECRET_KEY
        # Default to IEX for Basic plan
        self.ws_url = SIP_WS_URL if use_sip else IEX_WS_URL
        self.use_sip = use_sip
        self.ws = None
        self.connected = False
        self.authenticated = False
        self._thread = None
        self._stop_event = threading.Event()
        self._subscribed_symbols = set()
        self._on_quote_callback = None
        self._lock = threading.Lock()

    def set_credentials(self, api_key, secret_key):
        """Update credentials (called after mode switch)"""
        self.api_key = api_key
        self.secret_key = secret_key

    def connect(self, on_quote_callback=None):
        """Connect to WebSocket and start listening"""
        if self._thread and self._thread.is_alive():
            logger.warning("Market data WebSocket already connected")
            return

        self._on_quote_callback = on_quote_callback
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        """Run WebSocket connection in background thread"""
        logger.info(f"Connecting to Alpaca Market Data WebSocket: {self.ws_url}")

        self.ws = websocket.WebSocketApp(
            self.ws_url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close
        )
        self.ws.run_forever()

    def _on_open(self, ws):
        """Authenticate when connection opens"""
        logger.info("Market data WebSocket connected, authenticating...")
        auth_msg = {
            "action": "auth",
            "key": self.api_key,
            "secret": self.secret_key
        }
        ws.send(json.dumps(auth_msg))

    def _on_message(self, ws, message):
        """Handle incoming WebSocket messages"""
        try:
            data = json.loads(message)

            # Handle array of messages
            if isinstance(data, list):
                for msg in data:
                    self._process_message(msg)
            else:
                self._process_message(data)

        except Exception as e:
            logger.error(f"Error processing market data message: {e}")

    def _process_message(self, data):
        """Process a single WebSocket message"""
        msg_type = data.get("T")

        if msg_type == "success":
            # Connection/auth success
            if data.get("msg") == "authenticated":
                logger.info("Market data WebSocket authenticated successfully")
                self.authenticated = True
                self.connected = True
                # Resubscribe to any previously subscribed symbols
                if self._subscribed_symbols:
                    self._subscribe(list(self._subscribed_symbols))

        elif msg_type == "subscription":
            # Subscription confirmation
            trades = data.get("trades", [])
            quotes = data.get("quotes", [])
            bars = data.get("bars", [])
            logger.info(f"Market data subscriptions - quotes: {quotes}, trades: {trades}, bars: {bars}")

        elif msg_type == "q":
            # Quote update
            self._handle_quote(data)

        elif msg_type == "error":
            logger.error(f"Market data WebSocket error: {data.get('msg', data)}")

        else:
            logger.debug(f"Market data message type {msg_type}: {data}")

    def _handle_quote(self, data):
        """Handle quote update"""
        try:
            # Alpaca IEX quote fields:
            # S=Symbol, bp=Bid Price, bs=Bid Size, bx=Bid Exchange
            # ap=Ask Price, as=Ask Size, ax=Ask Exchange, t=Timestamp
            bid_price = data.get("bp")
            ask_price = data.get("ap")

            quote = {
                "symbol": data.get("S"),
                "bid": float(bid_price) if bid_price else None,
                "bid_size": data.get("bs"),
                "bid_exchange": data.get("bx"),
                "ask": float(ask_price) if ask_price else None,
                "ask_size": data.get("as"),
                "ask_exchange": data.get("ax"),
                "timestamp": data.get("t"),
            }

            # Calculate mid price
            if quote["bid"] and quote["ask"]:
                quote["last"] = (quote["bid"] + quote["ask"]) / 2
            elif quote["bid"]:
                quote["last"] = quote["bid"]
            elif quote["ask"]:
                quote["last"] = quote["ask"]
            else:
                quote["last"] = None

            # Call the callback if set
            if self._on_quote_callback:
                try:
                    self._on_quote_callback(quote)
                except Exception as e:
                    logger.error(f"Error in quote callback: {e}")

        except Exception as e:
            logger.error(f"Error parsing quote: {e}")

    def subscribe(self, symbols):
        """Subscribe to quotes for given symbols"""
        if not isinstance(symbols, list):
            symbols = [symbols]

        symbols = [s.upper() for s in symbols]

        with self._lock:
            for s in symbols:
                self._subscribed_symbols.add(s)

        if self.ws and self.authenticated:
            self._subscribe(symbols)

    def _subscribe(self, symbols):
        """Send subscription message"""
        if not symbols:
            return

        subscribe_msg = {
            "action": "subscribe",
            "quotes": symbols
        }
        self.ws.send(json.dumps(subscribe_msg))
        logger.info(f"Subscribed to quotes for: {symbols}")

    def unsubscribe(self, symbols):
        """Unsubscribe from quotes for given symbols"""
        if not isinstance(symbols, list):
            symbols = [symbols]

        symbols = [s.upper() for s in symbols]

        with self._lock:
            for s in symbols:
                self._subscribed_symbols.discard(s)

        if self.ws and self.authenticated:
            unsubscribe_msg = {
                "action": "unsubscribe",
                "quotes": symbols
            }
            self.ws.send(json.dumps(unsubscribe_msg))
            logger.info(f"Unsubscribed from quotes for: {symbols}")

    def get_subscribed_symbols(self):
        """Get list of currently subscribed symbols"""
        with self._lock:
            return list(self._subscribed_symbols)

    def _on_error(self, ws, error):
        """Handle WebSocket errors"""
        logger.error(f"Market data WebSocket error: {error}")

    def _on_close(self, ws, close_status_code, close_msg):
        """Handle WebSocket close"""
        logger.info(f"Market data WebSocket closed: {close_status_code} - {close_msg}")
        self.connected = False
        self.authenticated = False

        # Reconnect if not stopped
        if not self._stop_event.is_set():
            logger.info("Attempting to reconnect market data in 5 seconds...")
            import time
            time.sleep(5)
            if not self._stop_event.is_set():
                self._run()

    def disconnect(self):
        """Disconnect WebSocket"""
        self._stop_event.set()
        if self.ws:
            self.ws.close()
        self.connected = False
        self.authenticated = False
        logger.info("Market data WebSocket disconnected")


# Global streaming instance
_market_stream = None
_quote_callbacks = []


def get_market_stream():
    """Get the global market data streaming instance"""
    global _market_stream
    if _market_stream is None:
        _market_stream = MarketDataStream(use_sip=False)  # Use IEX for Basic plan
    return _market_stream


def _dispatch_quote(quote):
    """Dispatch quote updates to all registered callbacks"""
    for callback in _quote_callbacks:
        try:
            callback(quote)
        except Exception as e:
            logger.error(f"Error in quote callback: {e}")


def register_quote_callback(callback):
    """Register a callback for quote updates"""
    _quote_callbacks.append(callback)


def unregister_quote_callback(callback):
    """Unregister a quote update callback"""
    if callback in _quote_callbacks:
        _quote_callbacks.remove(callback)


def start_market_streaming():
    """Start the market data WebSocket stream"""
    stream = get_market_stream()
    if not stream.connected:
        stream.connect(on_quote_callback=_dispatch_quote)
    return stream


def stop_market_streaming():
    """Stop the market data WebSocket stream"""
    global _market_stream
    if _market_stream:
        _market_stream.disconnect()
        _market_stream = None


def restart_market_streaming():
    """Restart the market data stream with new credentials (after mode switch)"""
    global _market_stream
    logger.info("Restarting market data stream with new credentials...")

    # Stop existing stream
    if _market_stream:
        _market_stream.disconnect()
        _market_stream = None

    # Get current values directly from config
    from config import API_KEY, SECRET_KEY

    # Start new stream with updated credentials
    _market_stream = MarketDataStream(use_sip=False)
    _market_stream.api_key = API_KEY
    _market_stream.secret_key = SECRET_KEY
    _market_stream.connect(on_quote_callback=_dispatch_quote)
    logger.info(f"Market data stream restarted (using IEX feed)")
    return _market_stream


def subscribe_quotes(symbols):
    """Subscribe to quotes for given symbols"""
    stream = get_market_stream()
    stream.subscribe(symbols)


def unsubscribe_quotes(symbols):
    """Unsubscribe from quotes for given symbols"""
    stream = get_market_stream()
    stream.unsubscribe(symbols)


def get_subscribed_symbols():
    """Get list of currently subscribed symbols"""
    stream = get_market_stream()
    return stream.get_subscribed_symbols()
