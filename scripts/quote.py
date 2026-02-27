#!/usr/bin/env python3
"""
Quick Quote Lookup Script

Usage:
    python quote.py SYMBOL [SYMBOL ...]

Examples:
    python quote.py SOXL
    python quote.py AAPL MSFT GOOGL
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import PAPER_API_KEY, PAPER_SECRET_KEY, PAPER_BASE_URL
import alpaca_trade_api as alpaca


def get_quotes(symbols):
    """Get quotes for multiple symbols"""
    api = alpaca.REST(
        key_id=PAPER_API_KEY,
        secret_key=PAPER_SECRET_KEY,
        base_url=PAPER_BASE_URL
    )

    print("\n" + "="*70)
    print(f"{'Symbol':<8} {'Bid':>10} {'Ask':>10} {'Mid':>10} {'Spread':>10} {'Time':>12}")
    print("="*70)

    for symbol in symbols:
        try:
            quote = api.get_latest_quote(symbol.upper())
            bid = float(quote.bid_price)
            ask = float(quote.ask_price)
            mid = (bid + ask) / 2
            spread = ask - bid
            timestamp = quote.timestamp.strftime("%H:%M:%S") if hasattr(quote, 'timestamp') else "N/A"

            print(f"{symbol.upper():<8} ${bid:>9.2f} ${ask:>9.2f} ${mid:>9.2f} ${spread:>9.3f} {timestamp:>12}")
        except Exception as e:
            print(f"{symbol.upper():<8} ERROR: {e}")

    print("="*70 + "\n")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python quote.py SYMBOL [SYMBOL ...]")
        print("Example: python quote.py SOXL AAPL MSFT")
        sys.exit(1)

    get_quotes(sys.argv[1:])
