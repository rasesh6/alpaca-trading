"""
ML Auto Trader - Paper Trading
Automatically trades based on ML signals with risk management
"""
import os
import sys
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

# Add paths
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'ml-trading'))

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest
from ib_data_provider import IBDataProviderFallback

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('ml_auto_trader.log')
    ]
)
logger = logging.getLogger(__name__)


class MLAutoTrader:
    """
    Automated trading using ML signals

    Features:
    - Fetches ML signals from trained models
    - Executes trades with risk management
    - Position sizing based on confidence
    - Stop-loss and take-profit orders
    - Paper trading mode (default)
    """

    def __init__(self, paper: bool = True):
        self.paper = paper

        # API credentials from environment
        if paper:
            self.api_key = os.getenv('PAPER_API_KEY')
            self.secret_key = os.getenv('PAPER_SECRET_KEY')
        else:
            self.api_key = os.getenv('LIVE_API_KEY')
            self.secret_key = os.getenv('LIVE_SECRET_KEY')

        if not self.api_key or not self.secret_key:
            raise ValueError("API credentials not found in environment variables")

        # Initialize clients
        self.trading_client = TradingClient(
            api_key=self.api_key,
            secret_key=self.secret_key,
            paper=paper
        )
        self.data_client = StockHistoricalDataClient(
            api_key=self.api_key,
            secret_key=self.secret_key
        )

        # Trading configuration
        self.config = {
            'min_confidence': 0.70,          # Minimum confidence to trade
            'position_size_pct': 0.02,       # 2% of portfolio per trade
            'stop_loss_pct': 0.05,           # 5% stop loss
            'take_profit_pct': 0.10,         # 10% take profit
            'max_positions': 5,              # Maximum concurrent positions
            'min_trade_value': 100,          # Minimum trade value in $
            'signals_url': os.getenv('ML_SIGNALS_URL', 'http://localhost:5000/api/ml/signal'),
        }

        logger.info(f"ML Auto Trader initialized (paper={paper})")

    def get_account_info(self) -> Dict:
        """Get account information"""
        account = self.trading_client.get_account()
        return {
            'buying_power': float(account.buying_power),
            'cash': float(account.cash),
            'portfolio_value': float(account.portfolio_value),
            'pattern_day_trader': account.pattern_day_trader,
            'trading_blocked': account.trading_blocked
        }

    def get_positions(self) -> Dict[str, Dict]:
        """Get current positions"""
        positions = self.trading_client.get_all_positions()
        return {p.symbol: {
            'qty': float(p.qty),
            'avg_price': float(p.avg_entry_price),
            'current_price': float(p.current_price),
            'market_value': float(p.market_value),
            'unrealized_pl': float(p.unrealized_pl),
            'unrealized_plpc': float(p.unrealized_plpc)
        } for p in positions}

    def get_latest_price(self, symbol: str) -> Optional[float]:
        """
        Get latest NBBO price for a symbol from IB

        Uses IB Gateway for real-time NBBO quotes (better than Alpaca free tier).
        Falls back to Alpaca if IB is unavailable.

        Returns mid-price for market orders, or ask/bid for specific sides.
        """
        # Try IB first for NBBO quote
        try:
            ib_provider = IBDataProviderFallback()
            quote = ib_provider.get_realtime_quote(symbol)

            if quote:
                # Use mid-price for fair execution estimate
                if quote.get('mid'):
                    logger.info(f"{symbol}: IB NBBO mid={quote['mid']:.2f} (bid={quote.get('bid')}, ask={quote.get('ask')})")
                    return quote['mid']
                elif quote.get('ask'):
                    return quote['ask']
                elif quote.get('last'):
                    return quote['last']
        except Exception as e:
            logger.warning(f"IB quote failed for {symbol}: {e}, falling back to Alpaca")

        # Fallback to Alpaca
        try:
            request = StockLatestQuoteRequest(symbol_or_symbols=symbol)
            quote = self.data_client.get_stock_latest_quote(request)
            if symbol in quote:
                price = float(quote[symbol].ask_price)
                logger.info(f"{symbol}: Alpaca quote ask={price:.2f}")
                return price
        except Exception as e:
            logger.error(f"Error getting price for {symbol}: {e}")

        return None

    def get_ml_signal(self, symbol: str) -> Optional[Dict]:
        """
        Get ML signal for a symbol

        Returns:
            Dict with signal, confidence, probabilities
        """
        try:
            from signal_generator import SignalGenerator

            generator = SignalGenerator(symbol)
            signal = generator.get_latest_signal()

            return {
                'symbol': symbol,
                'signal': signal.get('signal', 'HOLD'),
                'confidence': signal.get('confidence', 0),
                'probabilities': signal.get('probabilities', {}),
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Error getting ML signal for {symbol}: {e}")
            return None

    def calculate_position_size(self, symbol: str, price: float) -> int:
        """Calculate position size based on portfolio and confidence"""
        account = self.get_account_info()
        portfolio_value = account['portfolio_value']

        # Base position size (2% of portfolio)
        position_value = portfolio_value * self.config['position_size_pct']

        # Calculate shares
        shares = int(position_value / price)

        # Ensure minimum trade value
        if shares * price < self.config['min_trade_value']:
            shares = int(self.config['min_trade_value'] / price)

        logger.info(f"Position size for {symbol}: {shares} shares @ ${price:.2f} = ${shares * price:.2f}")
        return shares

    def place_market_order(self, symbol: str, side: str, qty: int, extended_hours: bool = True) -> Optional[Dict]:
        """
        Place a market order

        Args:
            symbol: Stock symbol
            side: 'BUY' or 'SELL'
            qty: Number of shares
            extended_hours: Enable pre-market/after-hours trading (default: True)
        """
        try:
            order_data = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.BUY if side.upper() == 'BUY' else OrderSide.SELL,
                time_in_force=TimeInForce.DAY,
                extended_hours=extended_hours  # Enable extended hours trading
            )

            order = self.trading_client.submit_order(order_data)

            logger.info(f"Placed {side} order for {qty} {symbol} (extended_hours={extended_hours}) - Order ID: {order.id}")

            return {
                'order_id': str(order.id),
                'symbol': symbol,
                'side': side,
                'qty': qty,
                'extended_hours': extended_hours,
                'status': order.status,
                'created_at': order.created_at.isoformat() if order.created_at else None
            }
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            return None

    def place_bracket_order(self, symbol: str, side: str, qty: int,
                            stop_loss_pct: float = None,
                            take_profit_pct: float = None,
                            entry_price: float = None) -> Optional[Dict]:
        """
        Place a bracket order with stop loss and take profit

        Args:
            symbol: Stock symbol
            side: 'BUY' or 'SELL'
            qty: Number of shares
            stop_loss_pct: Stop loss percentage (default from config)
            take_profit_pct: Take profit percentage (default from config)
            entry_price: Entry price (if already known, skips price fetch)
        """
        try:
            # Use provided price or fetch new one
            if entry_price:
                price = entry_price
                logger.info(f"{symbol}: Using provided entry price ${price:.2f}")
            else:
                price = self.get_latest_price(symbol)
                if not price:
                    raise ValueError(f"Could not get price for {symbol}")

            stop_loss_pct = stop_loss_pct or self.config['stop_loss_pct']
            take_profit_pct = take_profit_pct or self.config['take_profit_pct']

            # Calculate stop loss and take profit prices
            if side.upper() == 'BUY':
                stop_price = price * (1 - stop_loss_pct)
                take_profit_price = price * (1 + take_profit_pct)
            else:
                stop_price = price * (1 + stop_loss_pct)
                take_profit_price = price * (1 - take_profit_pct)

            logger.info(f"{symbol}: Placing {side} order for {qty} shares @ ${price:.2f}")
            logger.info(f"{symbol}: Bracket targets - SL=${stop_price:.2f}, TP=${take_profit_price:.2f}")

            # Place market order
            order = self.place_market_order(symbol, side, qty)

            if order:
                order['entry_price'] = price
                order['stop_loss_price'] = round(stop_price, 2)
                order['take_profit_price'] = round(take_profit_price, 2)
                logger.info(f"{symbol}: Order placed successfully - Order ID: {order['order_id']}")
            else:
                logger.error(f"{symbol}: Order placement returned None")

            return order
        except Exception as e:
            logger.error(f"Error placing bracket order for {symbol}: {e}")
            return None

    def execute_signal(self, symbol: str, signal: Dict) -> Optional[Dict]:
        """
        Execute a trade based on ML signal

        Supports both long and short positions:
        - BUY signal: Close short OR open long
        - SELL signal: Close long OR open short
        """
        trade_signal = signal.get('signal', 'HOLD')
        confidence = signal.get('confidence', 0)

        # Check confidence threshold
        if confidence < self.config['min_confidence']:
            logger.info(f"{symbol}: Confidence {confidence:.1%} below threshold {self.config['min_confidence']:.1%}")
            return None

        # Check current positions
        positions = self.get_positions()

        # Check for existing position (long or short)
        has_long = symbol in positions and float(positions[symbol]['qty']) > 0
        has_short = symbol in positions and float(positions[symbol]['qty']) < 0

        if trade_signal == 'BUY':
            if has_short:
                # Close short position (buy to cover)
                position = positions[symbol]
                qty = abs(int(float(position['qty'])))
                logger.info(f"{symbol}: Closing SHORT position with BUY (confidence: {confidence:.1%})")
                return self.place_market_order(symbol, 'BUY', qty)

            if has_long:
                logger.info(f"{symbol}: Already have LONG position, skipping BUY")
                return None

            # Check max positions
            if len(positions) >= self.config['max_positions']:
                logger.info(f"{symbol}: Max positions ({self.config['max_positions']}) reached")
                return None

            # Open new long position
            price = self.get_latest_price(symbol)
            if not price:
                return None

            qty = self.calculate_position_size(symbol, price)
            logger.info(f"{symbol}: Opening LONG position with BUY (confidence: {confidence:.1%})")
            return self.place_bracket_order(symbol, 'BUY', qty, entry_price=price)

        elif trade_signal == 'SELL':
            if has_long:
                # Close long position (sell to close)
                position = positions[symbol]
                qty = int(float(position['qty']))
                logger.info(f"{symbol}: Closing LONG position with SELL (confidence: {confidence:.1%})")
                return self.place_market_order(symbol, 'SELL', qty)

            if has_short:
                logger.info(f"{symbol}: Already have SHORT position, skipping SELL")
                return None

            # Check max positions
            if len(positions) >= self.config['max_positions']:
                logger.info(f"{symbol}: Max positions ({self.config['max_positions']}) reached")
                return None

            # Open new short position
            price = self.get_latest_price(symbol)
            if not price:
                return None

            qty = self.calculate_position_size(symbol, price)
            logger.info(f"{symbol}: Opening SHORT position with SELL (confidence: {confidence:.1%})")
            return self.place_bracket_order(symbol, 'SELL', qty, entry_price=price)

        else:
            logger.info(f"{symbol}: HOLD signal, no action")
            return None

    def run_trading_cycle(self, symbols: list) -> Dict:
        """
        Run a complete trading cycle for multiple symbols

        Args:
            symbols: List of symbols to trade

        Returns:
            Summary of actions taken
        """
        logger.info("=" * 60)
        logger.info(f"ML Auto Trading Cycle - {datetime.now().isoformat()}")
        logger.info("=" * 60)

        results = {
            'timestamp': datetime.now().isoformat(),
            'account': self.get_account_info(),
            'positions_before': self.get_positions(),
            'signals': {},
            'orders': [],
            'errors': []
        }

        for symbol in symbols:
            try:
                # Get ML signal
                signal = self.get_ml_signal(symbol)
                if not signal:
                    results['errors'].append(f"{symbol}: Could not get signal")
                    continue

                results['signals'][symbol] = signal

                # Execute signal
                order = self.execute_signal(symbol, signal)
                if order:
                    results['orders'].append(order)

            except Exception as e:
                logger.error(f"Error processing {symbol}: {e}")
                results['errors'].append(f"{symbol}: {str(e)}")

        results['positions_after'] = self.get_positions()

        # Summary
        logger.info("\n" + "=" * 60)
        logger.info("TRADING CYCLE SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Signals generated: {len(results['signals'])}")
        logger.info(f"Orders placed: {len(results['orders'])}")
        logger.info(f"Errors: {len(results['errors'])}")

        for symbol, signal in results['signals'].items():
            logger.info(f"  {symbol}: {signal['signal']} ({signal['confidence']:.1%})")

        for order in results['orders']:
            logger.info(f"  Order: {order['side']} {order['qty']} {order['symbol']}")

        return results

    def close_all_positions(self) -> list:
        """Close all open positions"""
        positions = self.get_positions()
        orders = []

        for symbol, position in positions.items():
            qty = int(position['qty'])
            logger.info(f"Closing position: {qty} {symbol}")
            order = self.place_market_order(symbol, 'SELL', qty)
            if order:
                orders.append(order)

        return orders


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='ML Auto Trader')
    parser.add_argument('--symbols', nargs='+', default=['SOXL', 'NVDA', 'SPY', 'QQQ'],
                        help='Symbols to trade')
    parser.add_argument('--live', action='store_true', help='Use live trading (default: paper)')
    parser.add_argument('--close-all', action='store_true', help='Close all positions and exit')
    parser.add_argument('--status', action='store_true', help='Show account status and exit')

    args = parser.parse_args()

    trader = MLAutoTrader(paper=not args.live)

    if args.status:
        # Show status
        account = trader.get_account_info()
        positions = trader.get_positions()

        print("\n" + "=" * 60)
        print("ACCOUNT STATUS")
        print("=" * 60)
        print(f"Portfolio Value: ${account['portfolio_value']:,.2f}")
        print(f"Cash: ${account['cash']:,.2f}")
        print(f"Buying Power: ${account['buying_power']:,.2f}")

        if positions:
            print("\nPOSITIONS:")
            for symbol, pos in positions.items():
                pl_str = f"+{pos['unrealized_plpc']:.2%}" if pos['unrealized_plpc'] >= 0 else f"{pos['unrealized_plpc']:.2%}"
                print(f"  {symbol}: {pos['qty']} shares @ ${pos['avg_price']:.2f} = ${pos['market_value']:.2f} ({pl_str})")
        else:
            print("\nNo open positions")

        return

    if args.close_all:
        # Close all positions
        print("Closing all positions...")
        orders = trader.close_all_positions()
        print(f"Closed {len(orders)} positions")
        return

    # Run trading cycle
    results = trader.run_trading_cycle(args.symbols)

    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Signals: {len(results['signals'])}")
    print(f"Orders: {len(results['orders'])}")
    print(f"Errors: {len(results['errors'])}")


if __name__ == '__main__':
    main()
