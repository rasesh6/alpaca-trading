#!/usr/bin/env python3
"""
Scalp Trading Script - Quick scalp with auto-profit target

Usage:
    python scalp.py SYMBOL QUANTITY PROFIT_TARGET [OPTIONS]

Examples:
    python scalp.py SOXL 100 0.10          # Buy 100 SOXL, sell at +$0.10
    python scalp.py AAPL 10 0.05           # Buy 10 AAPL, sell at +$0.05
    python scalp.py SPY 5 0.25 --timeout 30  # 30 second fill timeout

Arguments:
    SYMBOL        Stock symbol to trade
    QUANTITY      Number of shares
    PROFIT_TARGET Profit amount per share (e.g., 0.10 = 10 cents)

Options:
    --timeout SECONDS   Fill timeout in seconds (default: 15)
    --sell-timeout SECONDS   Sell order timeout in seconds (default: 300)
    --limit-offset AMOUNT   Buy at bid + offset (default: 0 = at bid)
    --live              Use live trading (default: paper)
    --no-sell           Don't auto-sell, just buy
    --verbose           Show detailed output
"""

import sys
import os
import time
import argparse
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import alpaca_trade_api as alpaca
except ImportError:
    print("Error: alpaca-trade-api not installed. Run: pip install alpaca-trade-api")
    sys.exit(1)

# Import config
from config import PAPER_API_KEY, PAPER_SECRET_KEY, PAPER_BASE_URL
from config import LIVE_API_KEY, LIVE_SECRET_KEY, LIVE_BASE_URL


class ScalpTrader:
    """Quick scalp trading with auto-profit"""

    def __init__(self, use_live=False, verbose=False):
        # Select credentials based on mode
        if use_live:
            self.api = alpaca.REST(
                key_id=LIVE_API_KEY,
                secret_key=LIVE_SECRET_KEY,
                base_url=LIVE_BASE_URL
            )
            self.mode = "LIVE"
        else:
            self.api = alpaca.REST(
                key_id=PAPER_API_KEY,
                secret_key=PAPER_SECRET_KEY,
                base_url=PAPER_BASE_URL
            )
            self.mode = "PAPER"

        self.verbose = verbose

    def log(self, msg, level="INFO"):
        """Print log message with timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        prefix = "  " if level == "DEBUG" else ""
        print(f"[{timestamp}] {prefix}{msg}")

    def get_quote(self, symbol):
        """Get current bid/ask quote"""
        try:
            quote = self.api.get_latest_quote(symbol)
            return {
                'bid': float(quote.bid_price),
                'ask': float(quote.ask_price),
                'bid_size': int(quote.bid_size),
                'ask_size': int(quote.ask_size),
                'mid': (float(quote.bid_price) + float(quote.ask_price)) / 2
            }
        except Exception as e:
            self.log(f"Error getting quote: {e}", "ERROR")
            return None

    def get_account(self):
        """Get account info"""
        try:
            account = self.api.get_account()
            return {
                'cash': float(account.cash),
                'buying_power': float(account.buying_power),
                'equity': float(account.equity)
            }
        except Exception as e:
            self.log(f"Error getting account: {e}", "ERROR")
            return None

    def place_buy_order(self, symbol, qty, limit_price):
        """Place limit buy order"""
        try:
            order = self.api.submit_order(
                symbol=symbol,
                qty=qty,
                side='buy',
                type='limit',
                time_in_force='day',
                limit_price=str(limit_price)
            )
            self.log(f"BUY order placed: {qty} {symbol} @ ${limit_price:.2f}")
            self.log(f"Order ID: {order.id}", "DEBUG")
            return order
        except Exception as e:
            self.log(f"Error placing buy order: {e}", "ERROR")
            return None

    def place_sell_order(self, symbol, qty, limit_price):
        """Place limit sell order"""
        try:
            order = self.api.submit_order(
                symbol=symbol,
                qty=qty,
                side='sell',
                type='limit',
                time_in_force='day',
                limit_price=str(limit_price)
            )
            self.log(f"SELL order placed: {qty} {symbol} @ ${limit_price:.2f}")
            self.log(f"Order ID: {order.id}", "DEBUG")
            return order
        except Exception as e:
            self.log(f"Error placing sell order: {e}", "ERROR")
            return None

    def cancel_order(self, order_id):
        """Cancel an order"""
        try:
            self.api.cancel_order(order_id)
            self.log(f"Order {order_id} cancelled")
            return True
        except Exception as e:
            self.log(f"Error cancelling order: {e}", "ERROR")
            return False

    def get_order_status(self, order_id):
        """Get order status and fill info"""
        try:
            order = self.api.get_order(order_id)
            return {
                'status': order.status,
                'filled_qty': float(order.filled_qty) if order.filled_qty else 0,
                'filled_price': float(order.filled_avg_price) if order.filled_avg_price else None
            }
        except Exception as e:
            self.log(f"Error getting order status: {e}", "ERROR")
            return None

    def wait_for_fill(self, order_id, timeout_seconds=15):
        """Wait for order to fill, return fill price or None"""
        self.log(f"Waiting for fill (timeout: {timeout_seconds}s)...")
        start_time = time.time()

        while time.time() - start_time < timeout_seconds:
            status = self.get_order_status(order_id)
            if not status:
                time.sleep(0.5)
                continue

            if status['status'] == 'filled':
                return status['filled_price']

            if status['status'] in ['canceled', 'rejected', 'expired']:
                self.log(f"Order {status['status']}")
                return None

            elapsed = int(time.time() - start_time)
            if self.verbose:
                self.log(f"Checking fill... {elapsed}/{timeout_seconds}s (status: {status['status']})", "DEBUG")

            time.sleep(0.5)

        return None

    def scalp(self, symbol, quantity, profit_target, fill_timeout=15,
              sell_timeout=300, limit_offset=0, auto_sell=True):
        """
        Execute scalp trade:
        1. Buy at bid (or bid + offset)
        2. Wait for fill
        3. Sell at fill price + profit target
        """

        print("\n" + "="*60)
        print(f"SCALP TRADE: {symbol}")
        print("="*60)
        self.log(f"Mode: {self.mode}")
        self.log(f"Quantity: {quantity} shares")
        self.log(f"Profit Target: +${profit_target:.2f} per share")

        # Get account info
        account = self.get_account()
        if account:
            self.log(f"Buying Power: ${account['buying_power']:,.2f}")

        # Get current quote
        quote = self.get_quote(symbol)
        if not quote:
            self.log("Failed to get quote", "ERROR")
            return None

        buy_price = quote['bid'] + limit_offset
        self.log(f"Current Quote: Bid ${quote['bid']:.2f} / Ask ${quote['ask']:.2f}")
        self.log(f"Buy Price: ${buy_price:.2f}")

        # Calculate estimated cost
        estimated_cost = buy_price * quantity
        self.log(f"Estimated Cost: ${estimated_cost:,.2f}")

        # Place buy order
        buy_order = self.place_buy_order(symbol, quantity, buy_price)
        if not buy_order:
            return None

        # Wait for fill
        fill_price = self.wait_for_fill(buy_order.id, fill_timeout)

        if not fill_price:
            self.log(f"Fill timeout ({fill_timeout}s), cancelling order...")
            self.cancel_order(buy_order.id)
            return None

        self.log(f"FILLED at ${fill_price:.2f}")

        # Calculate profit target price
        sell_price = round(fill_price + profit_target, 2)
        potential_profit = profit_target * quantity

        self.log(f"Profit Target Price: ${sell_price:.2f}")
        self.log(f"Potential Profit: +${potential_profit:.2f}")

        if not auto_sell:
            self.log("Auto-sell disabled, position remains open")
            return {
                'buy_order_id': buy_order.id,
                'fill_price': fill_price,
                'quantity': quantity,
                'sell_price_target': sell_price
            }

        # Place sell order
        sell_order = self.place_sell_order(symbol, quantity, sell_price)
        if not sell_order:
            self.log("Failed to place sell order!", "ERROR")
            return None

        # Wait for sell fill
        self.log(f"Waiting for sell to fill (timeout: {sell_timeout}s)...")
        sell_fill_price = self.wait_for_fill(sell_order.id, sell_timeout)

        if sell_fill_price:
            actual_profit = (sell_fill_price - fill_price) * quantity
            self.log(f"SELL FILLED at ${sell_fill_price:.2f}")
            self.log(f"ACTUAL PROFIT: +${actual_profit:.2f}")
        else:
            self.log(f"Sell not filled within {sell_timeout}s")
            self.log(f"Sell order {sell_order.id} remains open")

        print("="*60 + "\n")

        return {
            'buy_order_id': buy_order.id,
            'sell_order_id': sell_order.id,
            'fill_price': fill_price,
            'sell_price': sell_fill_price,
            'quantity': quantity,
            'profit': (sell_fill_price - fill_price) * quantity if sell_fill_price else None
        }


def main():
    parser = argparse.ArgumentParser(
        description='Scalp Trading Script - Quick scalp with auto-profit',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python scalp.py SOXL 100 0.10          # Buy 100 SOXL, sell at +$0.10
    python scalp.py AAPL 10 0.05           # Buy 10 AAPL, sell at +$0.05
    python scalp.py SPY 5 0.25 --timeout 30  # 30 second fill timeout
        """
    )

    parser.add_argument('symbol', help='Stock symbol to trade')
    parser.add_argument('quantity', type=int, help='Number of shares')
    parser.add_argument('profit_target', type=float, help='Profit amount per share (e.g., 0.10 = 10 cents)')
    parser.add_argument('--timeout', type=int, default=15, help='Fill timeout in seconds (default: 15)')
    parser.add_argument('--sell-timeout', type=int, default=300, help='Sell order timeout in seconds (default: 300)')
    parser.add_argument('--limit-offset', type=float, default=0, help='Buy at bid + offset (default: 0)')
    parser.add_argument('--live', action='store_true', help='Use live trading (default: paper)')
    parser.add_argument('--no-sell', action='store_true', help="Don't auto-sell, just buy")
    parser.add_argument('--verbose', '-v', action='store_true', help='Show detailed output')

    args = parser.parse_args()

    # Create trader
    trader = ScalpTrader(use_live=args.live, verbose=args.verbose)

    # Execute scalp
    result = trader.scalp(
        symbol=args.symbol.upper(),
        quantity=args.quantity,
        profit_target=args.profit_target,
        fill_timeout=args.timeout,
        sell_timeout=args.sell_timeout,
        limit_offset=args.limit_offset,
        auto_sell=not args.no_sell
    )

    if result:
        print("\nRESULT:")
        for key, value in result.items():
            if value is not None:
                print(f"  {key}: {value}")
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == '__main__':
    main()
