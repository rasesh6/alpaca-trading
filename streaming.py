"""
Alpaca WebSocket Streaming Client

Real-time order updates via WebSocket instead of polling.
"""
import json
import logging
import threading
import websocket
from config import API_KEY, SECRET_KEY, USE_PAPER

logger = logging.getLogger(__name__)

# WebSocket URLs
PAPER_WS_URL = "wss://paper-api.alpaca.markets/stream"
LIVE_WS_URL = "wss://api.alpaca.markets/stream"


class AlpacaStream:
    """WebSocket client for real-time trade updates"""

    def __init__(self, on_trade_update=None):
        self.api_key = API_KEY
        self.secret_key = SECRET_KEY
        self.ws_url = PAPER_WS_URL if USE_PAPER else LIVE_WS_URL
        self.on_trade_update = on_trade_update
        self.ws = None
        self.connected = False
        self._thread = None
        self._stop_event = threading.Event()

    def connect(self):
        """Connect to WebSocket and start listening"""
        if self._thread and self._thread.is_alive():
            logger.warning("WebSocket already connected")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        """Run WebSocket connection in background thread"""
        logger.info(f"Connecting to Alpaca WebSocket: {self.ws_url}")

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
        logger.info("WebSocket connected, authenticating...")
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
            stream = data.get("stream")

            if stream == "authorization":
                status = data.get("data", {}).get("status")
                if status == "authorized":
                    logger.info("WebSocket authorized successfully")
                    self.connected = True
                    # Subscribe to trade updates
                    self._subscribe_trade_updates()
                else:
                    logger.error(f"WebSocket authorization failed: {data}")

            elif stream == "listening":
                streams = data.get("data", {}).get("streams", [])
                logger.info(f"WebSocket listening to streams: {streams}")

            elif stream == "trade_updates":
                self._handle_trade_update(data)

            else:
                logger.debug(f"WebSocket message: {data}")

        except Exception as e:
            logger.error(f"Error processing WebSocket message: {e}")

    def _subscribe_trade_updates(self):
        """Subscribe to trade_updates stream"""
        if self.ws:
            subscribe_msg = {
                "action": "listen",
                "data": {
                    "streams": ["trade_updates"]
                }
            }
            self.ws.send(json.dumps(subscribe_msg))
            logger.info("Subscribed to trade_updates stream")

    def _handle_trade_update(self, data):
        """Handle trade update events"""
        event_data = data.get("data", {})
        event = event_data.get("event")
        order = event_data.get("order", {})

        logger.info(f"Trade update: {event} for order {order.get('id', 'unknown')}")

        # Call the callback if set
        if self.on_trade_update:
            try:
                self.on_trade_update({
                    "event": event,
                    "order_id": order.get("id"),
                    "symbol": order.get("symbol"),
                    "side": order.get("side"),
                    "qty": float(order.get("qty", 0)),
                    "filled_qty": float(order.get("filled_qty", 0)),
                    "filled_avg_price": float(order.get("filled_avg_price")) if order.get("filled_avg_price") else None,
                    "status": order.get("status"),
                    "order": order,
                    "timestamp": event_data.get("timestamp"),
                    "price": float(event_data.get("price")) if event_data.get("price") else None,
                    "position_qty": event_data.get("position_qty"),
                })
            except Exception as e:
                logger.error(f"Error in trade update callback: {e}")

    def _on_error(self, ws, error):
        """Handle WebSocket errors"""
        logger.error(f"WebSocket error: {error}")

    def _on_close(self, ws, close_status_code, close_msg):
        """Handle WebSocket close"""
        logger.info(f"WebSocket closed: {close_status_code} - {close_msg}")
        self.connected = False

        # Reconnect if not stopped
        if not self._stop_event.is_set():
            logger.info("Attempting to reconnect in 5 seconds...")
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
        logger.info("WebSocket disconnected")


# Global streaming instance
_stream = None
_trade_update_callbacks = []


def get_stream():
    """Get the global streaming instance"""
    global _stream
    if _stream is None:
        _stream = AlpacaStream(on_trade_update=_dispatch_trade_update)
    return _stream


def _dispatch_trade_update(update):
    """Dispatch trade updates to all registered callbacks"""
    for callback in _trade_update_callbacks:
        try:
            callback(update)
        except Exception as e:
            logger.error(f"Error in trade update callback: {e}")


def register_trade_callback(callback):
    """Register a callback for trade updates"""
    _trade_update_callbacks.append(callback)


def unregister_trade_callback(callback):
    """Unregister a trade update callback"""
    if callback in _trade_update_callbacks:
        _trade_update_callbacks.remove(callback)


def start_streaming():
    """Start the WebSocket stream"""
    stream = get_stream()
    if not stream.connected:
        stream.connect()
    return stream


def stop_streaming():
    """Stop the WebSocket stream"""
    global _stream
    if _stream:
        _stream.disconnect()
        _stream = None


def restart_streaming():
    """Restart the WebSocket stream with new credentials (after mode switch)"""
    global _stream
    logger.info("Restarting WebSocket stream with new credentials...")

    # Stop existing stream
    if _stream:
        _stream.disconnect()
        _stream = None

    # Get current values directly from config (not reload)
    from config import API_KEY, SECRET_KEY, USE_PAPER, get_trading_mode
    is_paper = get_trading_mode()
    ws_url = PAPER_WS_URL if is_paper else LIVE_WS_URL

    # Start new stream with updated credentials
    _stream = AlpacaStream(on_trade_update=_dispatch_trade_update)
    _stream.api_key = API_KEY
    _stream.secret_key = SECRET_KEY
    _stream.ws_url = ws_url
    _stream.connect()
    logger.info(f"WebSocket stream restarted (paper={is_paper}, url={ws_url})")
    return _stream
