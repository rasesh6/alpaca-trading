"""
Interactive Brokers Data Provider for ML Trading
Fetches historical bars and real-time NBBO quotes via IB Gateway
"""
import os
import time
import logging
import random
import threading
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import pandas as pd

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# Global counter for unique client IDs
_client_id_counter = 0
_client_id_lock = threading.Lock()

def _get_unique_client_id() -> int:
    """Generate a unique client ID for IB connections"""
    global _client_id_counter
    with _client_id_lock:
        # Use random base + counter to avoid any caching issues
        import random
        base = random.randint(1, 100) * 1000
        _client_id_counter += 1
        return base + (_client_id_counter % 999)  # Range: 1000-100999

class IBDataProvider:
    """
    Data provider using Interactive Brokers Gateway

    Connects to IB Gateway (hosted on Railway or local) to fetch:
    - Historical daily bars for ML training
    - Real-time NBBO quotes for trading

    Configuration via environment variables:
    - IB_GATEWAY_HOST: IB Gateway host (default: ib-gateway.railway.internal for Railway)
    - IB_GATEWAY_PORT: IB Gateway port (default: 4001)
    """

    # Common port configurations
    PORTS = {
        'railway_private': 4001,    # Railway private networking
        'railway_socat': 4003,      # Railway exposes via socat
        'local_live': 4001,         # Local live trading
        'local_paper': 4002,        # Local paper trading
    }

    def __init__(self, host: str = None, port: int = None):
        # Default to Railway private networking if not specified
        self.host = host or os.getenv('IB_GATEWAY_HOST', 'ib-gateway.railway.internal')
        # Default to 4001 (direct API port)
        self.port = port or int(os.getenv('IB_GATEWAY_PORT', '4001'))
        # Generate unique client ID for this instance
        self.client_id = _get_unique_client_id()
        self.ib = None
        self._connected = False
        self._event_loop = None
        logger.debug(f"IBDataProvider created with clientId={self.client_id}")

    def _ensure_event_loop(self):
        """Ensure an asyncio event loop exists for ib_insync"""
        import asyncio
        try:
            # Try to get running loop first
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop, create and set one for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # Apply nest_asyncio to allow nested event loops (required for ib_insync in threads)
        try:
            import nest_asyncio
            nest_asyncio.apply()
        except ImportError:
            # If nest_asyncio not available, try to proceed anyway
            logger.warning("nest_asyncio not installed. Run: pip install nest_asyncio")

        self._event_loop = loop
        return loop

    def connect(self) -> bool:
        """Connect to IB Gateway"""
        try:
            from ib_insync import IB, util
            import asyncio

            # Ensure event loop exists (required for ib_insync in threads)
            self._ensure_event_loop()

            # Use util.startLoop() for proper event loop handling in threads
            try:
                util.startLoop()
            except Exception as e:
                logger.debug(f"startLoop() note: {e}")

            logger.info(f"Connecting to IB Gateway at {self.host}:{self.port} with clientId={self.client_id}...")

            self.ib = IB()

            # Set up disconnect handler for debugging
            def on_disconnect():
                logger.warning(f"IB disconnected! (clientId={self.client_id})")

            self.ib.disconnectedEvent += on_disconnect

            # Try connecting with increasing timeout
            for timeout in [15, 30, 60]:
                try:
                    self.ib.connect(
                        self.host,
                        self.port,
                        clientId=self.client_id,
                        timeout=timeout
                    )
                    logger.info(f"connect() returned, sleeping to stabilize...")
                    # Give the event loop time to process the connection
                    self.ib.sleep(0.5)
                    logger.info(f"sleep() completed, checking connection...")
                    if self.ib.isConnected():
                        self._connected = True
                        logger.info(f"Connected to IB Gateway successfully (clientId={self.client_id}, timeout={timeout}s)")
                        return True
                    else:
                        logger.warning(f"Connection lost after sleep (clientId={self.client_id})")
                except Exception as e:
                    logger.warning(f"Connection attempt with timeout={timeout}s failed: {e}")
                    if timeout == 60:
                        raise

        except ImportError:
            logger.error("ib_insync not installed. Run: pip install ib_insync")
            return False
        except Exception as e:
            logger.error(f"Failed to connect to IB Gateway: {e}")

            # Try alternative ports
            alt_ports = [4003, 4001, 4002] if self.port not in [4003, 4001, 4002] else []
            for alt_port in alt_ports:
                if alt_port == self.port:
                    continue
                logger.info(f"Trying alternative port {alt_port}...")
                try:
                    self.ib = IB()
                    self.ib.connect(
                        self.host,
                        alt_port,
                        clientId=self.client_id,
                        timeout=30
                    )
                    # Give the event loop time to process the connection
                    self.ib.sleep(0.5)
                    self.port = alt_port
                    self._connected = True
                    logger.info(f"Connected to IB Gateway on alternative port {alt_port} (clientId={self.client_id})")
                    return True
                except Exception as e2:
                    logger.warning(f"Port {alt_port} failed: {e2}")

            return False

    def disconnect(self):
        """Disconnect from IB Gateway"""
        if self.ib and self._connected:
            try:
                self.ib.disconnect()
                logger.info("Disconnected from IB Gateway")
            except Exception as e:
                logger.error(f"Error disconnecting: {e}")
            finally:
                self._connected = False

    def ensure_connection(self) -> bool:
        """Ensure connection to IB Gateway"""
        if self._connected and self.ib and self.ib.isConnected():
            return True
        return self.connect()

    def get_historical_bars(
        self,
        symbol: str,
        days: int = 365,
        bar_size: str = '1 day'
    ) -> Optional[pd.DataFrame]:
        """
        Fetch historical daily bars for a symbol

        Args:
            symbol: Stock symbol (e.g., 'SOXL', 'SPY')
            days: Number of days of history
            bar_size: Bar size ('1 day', '1 hour', '5 mins', etc.)

        Returns:
            DataFrame with columns: Date, Open, High, Low, Close, Volume
        """
        if not self.ensure_connection():
            logger.error("Not connected to IB Gateway")
            return None

        try:
            from ib_insync import Stock

            logger.info(f"Fetching {days} days of {bar_size} bars for {symbol}...")

            # Create stock contract
            contract = Stock(symbol, 'SMART', 'USD')
            self.ib.qualifyContracts(contract)

            if not contract.conId:
                logger.error(f"Could not find contract for {symbol}")
                return None

            # Calculate duration string
            if bar_size == '1 day':
                duration_str = f'{days} D'
            elif bar_size in ['1 hour', '30 mins', '15 mins', '5 mins']:
                duration_str = f'{days} D'
            else:
                duration_str = f'{days} D'

            # Request historical data
            bars = self.ib.reqHistoricalData(
                contract,
                endDateTime='',
                durationStr=duration_str,
                barSizeSetting=bar_size,
                whatToShow='TRADES',
                useRTH=True,
                formatDate=1  # Return as YYYYMMDD format
            )

            if not bars or len(bars) == 0:
                logger.error(f"No historical data returned for {symbol}")
                return None

            # Convert to DataFrame
            df = pd.DataFrame([
                {
                    'Date': bar.date,
                    'Open': bar.open,
                    'High': bar.high,
                    'Low': bar.low,
                    'Close': bar.close,
                    'Volume': bar.volume
                }
                for bar in bars
            ])

            # Convert date string to datetime
            if isinstance(df['Date'].iloc[0], str):
                df['Date'] = pd.to_datetime(df['Date'], format='%Y%m%d')
            else:
                df['Date'] = pd.to_datetime(df['Date'])

            logger.info(f"Retrieved {len(df)} bars for {symbol}")
            return df

        except Exception as e:
            logger.error(f"Error fetching historical data for {symbol}: {e}")
            return None

    def get_realtime_quote(self, symbol: str) -> Optional[Dict]:
        """
        Fetch real-time NBBO quote for a symbol

        Args:
            symbol: Stock symbol

        Returns:
            Dict with bid, ask, last, bid_size, ask_size, etc.
        """
        if not self.ensure_connection():
            logger.error("Not connected to IB Gateway")
            return None

        try:
            from ib_insync import Stock

            # Create stock contract
            contract = Stock(symbol, 'SMART', 'USD')
            self.ib.qualifyContracts(contract)

            if not contract.conId:
                logger.error(f"Could not find contract for {symbol}")
                return None

            # Request market data
            ticker = self.ib.reqMktData(contract, '', False, False)

            # Wait for data (max 3 seconds)
            for _ in range(30):
                self.ib.sleep(0.1)
                if ticker.last and ticker.last > 0:
                    break
                if ticker.bid and ticker.ask and ticker.bid > 0 and ticker.ask > 0:
                    break

            # Build quote dict
            quote = {
                'symbol': symbol,
                'bid': float(ticker.bid) if ticker.bid and ticker.bid > 0 else None,
                'ask': float(ticker.ask) if ticker.ask and ticker.ask > 0 else None,
                'last': float(ticker.last) if ticker.last and ticker.last > 0 else None,
                'bid_size': int(ticker.bidSize) if ticker.bidSize else None,
                'ask_size': int(ticker.askSize) if ticker.askSize else None,
                'last_size': int(ticker.lastSize) if ticker.lastSize else None,
                'volume': int(ticker.volume) if ticker.volume else None,
                'high': float(ticker.high) if ticker.high else None,
                'low': float(ticker.low) if ticker.low else None,
                'timestamp': datetime.now().isoformat()
            }

            # Cancel market data subscription
            self.ib.cancelMktData(contract)

            # Calculate mid and spread if we have both bid and ask
            if quote['bid'] and quote['ask']:
                quote['mid'] = (quote['bid'] + quote['ask']) / 2
                quote['spread'] = quote['ask'] - quote['bid']
                quote['spread_pct'] = (quote['spread'] / quote['mid']) * 100

            logger.info(f"Got quote for {symbol}: bid={quote.get('bid')}, ask={quote.get('ask')}")
            return quote

        except Exception as e:
            logger.error(f"Error fetching quote for {symbol}: {e}")
            return None

    def get_multiple_quotes(self, symbols: List[str]) -> Dict[str, Dict]:
        """
        Fetch real-time quotes for multiple symbols

        Args:
            symbols: List of stock symbols

        Returns:
            Dict mapping symbol to quote dict
        """
        quotes = {}
        for symbol in symbols:
            quote = self.get_realtime_quote(symbol)
            if quote:
                quotes[symbol] = quote
            time.sleep(0.1)  # Small delay to avoid rate limiting
        return quotes

    def __enter__(self):
        """Context manager entry"""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.disconnect()


class IBDataProviderFallback:
    """
    IB Data Provider with automatic fallback to yfinance

    Tries IB Gateway first, falls back to yfinance if unavailable
    """

    def __init__(self, ib_host: str = None, ib_port: int = None):
        self.ib_provider = IBDataProvider(ib_host, ib_port)

    def get_historical_bars(self, symbol: str, days: int = 365) -> Optional[pd.DataFrame]:
        """Get historical bars with fallback"""
        # Try IB first
        df = self.ib_provider.get_historical_bars(symbol, days)
        if df is not None and len(df) > 0:
            return df

        # Fallback to yfinance
        logger.info(f"IB Gateway unavailable, falling back to yfinance for {symbol}")
        try:
            import yfinance as yf

            ticker = yf.Ticker(symbol)
            df = ticker.history(period=f"{days}d")

            if df.empty:
                logger.error(f"No data from yfinance for {symbol}")
                return None

            df = df.reset_index()
            df.columns = [c.capitalize() for c in df.columns]

            logger.info(f"Retrieved {len(df)} bars via yfinance for {symbol}")
            return df

        except ImportError:
            logger.error("yfinance not available as fallback")
            return None
        except Exception as e:
            logger.error(f"yfinance fallback failed: {e}")
            return None

    def get_realtime_quote(self, symbol: str) -> Optional[Dict]:
        """Get real-time quote with fallback"""
        # Try IB first
        quote = self.ib_provider.get_realtime_quote(symbol)
        if quote and (quote.get('bid') or quote.get('ask')):
            return quote

        # Fallback to yfinance (no real-time quotes, but we can get delayed)
        logger.info(f"IB Gateway unavailable for quote, using yfinance for {symbol}")
        try:
            import yfinance as yf

            ticker = yf.Ticker(symbol)
            info = ticker.info

            return {
                'symbol': symbol,
                'bid': info.get('bid'),
                'ask': info.get('ask'),
                'last': info.get('currentPrice') or info.get('regularMarketPrice'),
                'volume': info.get('volume'),
                'timestamp': datetime.now().isoformat(),
                'source': 'yfinance'
            }

        except Exception as e:
            logger.error(f"yfinance quote fallback failed: {e}")
            return None


# Convenience function for quick data fetching
def fetch_bars(symbol: str, days: int = 365, use_ib: bool = True) -> Optional[pd.DataFrame]:
    """
    Fetch historical bars for a symbol

    Args:
        symbol: Stock symbol
        days: Number of days
        use_ib: Whether to use IB Gateway (falls back to yfinance)

    Returns:
        DataFrame with OHLCV data
    """
    if use_ib:
        provider = IBDataProviderFallback()
        return provider.get_historical_bars(symbol, days)
    else:
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=f"{days}d")
            if df.empty:
                return None
            df = df.reset_index()
            df.columns = [c.capitalize() for c in df.columns]
            return df
        except Exception as e:
            logger.error(f"Failed to fetch data: {e}")
            return None


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("Usage: python ib_data_provider.py SYMBOL [DAYS]")
        print("Example: python ib_data_provider.py SOXL 365")
        sys.exit(1)

    symbol = sys.argv[1].upper()
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 365

    print(f"\n{'='*60}")
    print(f"IB Data Provider Test: {symbol}")
    print(f"{'='*60}")

    # Test with fallback
    provider = IBDataProviderFallback()

    # Test historical bars
    print(f"\nFetching {days} days of historical data...")
    df = provider.get_historical_bars(symbol, days)

    if df is not None:
        print(f"\nRetrieved {len(df)} bars")
        print(f"\nFirst 5 rows:")
        print(df.head())
        print(f"\nLast 5 rows:")
        print(df.tail())
    else:
        print("Failed to fetch historical data")

    # Test real-time quote
    print(f"\n{'='*60}")
    print("Fetching real-time quote...")
    quote = provider.get_realtime_quote(symbol)

    if quote:
        print(f"\nQuote for {symbol}:")
        for key, value in quote.items():
            print(f"  {key}: {value}")
    else:
        print("Failed to fetch quote")

    print(f"\n{'='*60}")
