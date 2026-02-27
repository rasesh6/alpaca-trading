"""
Interactive Brokers Data Provider for ML Trading
Fetches historical bars and real-time NBBO quotes via IB Gateway
"""
import os
import time
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import pandas as pd

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

class IBDataProvider:
    """
    Data provider using Interactive Brokers Gateway

    Connects to IB Gateway (hosted on Railway or local) to fetch:
    - Historical daily bars for ML training
    - Real-time NBBO quotes for trading

    Configuration via environment variables:
    - IB_GATEWAY_HOST: IB Gateway host (default: ib-gateway-production.up.railway.app)
    - IB_GATEWAY_PORT: IB Gateway port (default: 4001)
    """

    def __init__(self, host: str = None, port: int = None):
        self.host = host or os.getenv('IB_GATEWAY_HOST', 'ib-gateway-production.up.railway.app')
        self.port = port or int(os.getenv('IB_GATEWAY_PORT', '4001'))
        self.ib = None
        self._connected = False

    def connect(self) -> bool:
        """Connect to IB Gateway"""
        try:
            from ib_insync import IB

            logger.info(f"Connecting to IB Gateway at {self.host}:{self.port}...")

            self.ib = IB()
            self.ib.connect(
                self.host,
                self.port,
                clientId=15,  # Unique client ID for ML trading
                timeout=30
            )

            self._connected = True
            logger.info("Connected to IB Gateway successfully")
            return True

        except ImportError:
            logger.error("ib_insync not installed. Run: pip install ib_insync")
            return False
        except Exception as e:
            logger.error(f"Failed to connect to IB Gateway: {e}")
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
