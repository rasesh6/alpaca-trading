#!/usr/bin/env python3
"""
Bracket Order Script - Entry with TP and SL

Usage:
    python bracket.py SYMBOL QUANTITY [TP_OFFSET] [SL_OFFSET] [OPTIONS]

Examples:
    python bracket.py SOXL 100 0.50 0.25       # TP +$0.50, SL -$0.25
    python bracket.py AAPL 10 1.0 0.5          # TP +$1.00, SL -$0.50
    python bracket.py SPY 5 --tp-pct 1 --sl-pct 0.5  # TP +1%, SL -0.5%

Options:
    --market         Use market order for entry (default: limit at ask)
    --limit          Use limit order at specified price
    --tp-pct PCT     Take profit as percentage
    --sl-pct PCT     Stop loss as percentage
    --live           Use live trading
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import PAPER_API_KEY, PAPER_SECRET_KEY, PAPER_BASE_URL
from config import LIVE_API_KEY, LIVE_SECRET_KEY, LIVE_BASE_URL
import alpaca_trade_api as alpaca


def bracket_order(api, symbol, quantity, entry_type='limit', entry_price=None,
                  tp_offset=None, sl_offset=None, tp_pct=None, sl_pct=None,
                  verbose=False):
    """
    Place a bracket order with entry, take profit, and stop loss.

    For BUY orders:
        - TP is above entry (sell when price rises)
        - SL is below entry (sell when price falls)
    """

    # Get current price
    try:
        quote = api.get_latest_quote(symbol)
        bid = float(quote.bid_price)
        ask = float(quote.ask_price)
        mid = (bid + ask) / 2
    except Exception as e:
        print(f"Error getting quote: {e}")
        return None

    print(f"\n{'='*60}")
    print(f"BRACKET ORDER: {symbol}")
    print(f"{'='*60}")
    print(f"Current Quote: Bid ${bid:.2f} / Ask ${ask:.2f}")

    # Determine entry price
    if entry_price:
        pass  # Use specified price
    elif entry_type == 'market':
        entry_price = None  # Market order
    else:
        entry_price = ask  # Limit at ask for quick fill

    print(f"Quantity: {quantity}")
    print(f"Entry Type: {entry_type}")
    if entry_price:
        print(f"Entry Price: ${entry_price:.2f}")

    # Calculate TP and SL prices
    base_price = entry_price if entry_price else mid

    if tp_pct:
        tp_price = round(base_price * (1 + tp_pct/100), 2)
        print(f"Take Profit: ${tp_price:.2f} (+{tp_pct}%)")
    elif tp_offset:
        tp_price = round(base_price + tp_offset, 2)
        print(f"Take Profit: ${tp_price:.2f} (+${tp_offset:.2f})")
    else:
        tp_price = None
        print("Take Profit: None (manual exit)")

    if sl_pct:
        sl_price = round(base_price * (1 - sl_pct/100), 2)
        sl_limit = round(sl_price - 0.01, 2)
        print(f"Stop Loss: ${sl_price:.2f} (-{sl_pct}%)")
    elif sl_offset:
        sl_price = round(base_price - sl_offset, 2)
        sl_limit = round(sl_price - 0.01, 2)
        print(f"Stop Loss: ${sl_price:.2f} (-${sl_offset:.2f})")
    else:
        sl_price = None
        sl_limit = None
        print("Stop Loss: None (manual exit)")

    # Build order
    order_kwargs = {
        'symbol': symbol,
        'qty': quantity,
        'side': 'buy',
        'time_in_force': 'day',
        'order_class': 'bracket',
    }

    if entry_type == 'market':
        order_kwargs['type'] = 'market'
    else:
        order_kwargs['type'] = 'limit'
        order_kwargs['limit_price'] = str(entry_price)

    if tp_price:
        order_kwargs['take_profit'] = {'limit_price': str(tp_price)}

    if sl_price:
        order_kwargs['stop_loss'] = {
            'stop_price': str(sl_price),
            'limit_price': str(sl_limit)
        }

    # Place order
    try:
        order = api.submit_order(**order_kwargs)
        print(f"\nOrder Placed: {order.id}")
        print(f"Status: {order.status}")
        print(f"{'='*60}\n")
        return order
    except Exception as e:
        print(f"\nError placing order: {e}")
        print(f"{'='*60}\n")
        return None


def main():
    parser = argparse.ArgumentParser(description='Bracket Order Script')
    parser.add_argument('symbol', help='Stock symbol')
    parser.add_argument('quantity', type=int, help='Number of shares')
    parser.add_argument('tp_offset', type=float, nargs='?', help='Take profit offset ($)')
    parser.add_argument('sl_offset', type=float, nargs='?', help='Stop loss offset ($)')
    parser.add_argument('--market', action='store_true', help='Use market order for entry')
    parser.add_argument('--limit', type=float, help='Limit price for entry')
    parser.add_argument('--tp-pct', type=float, help='Take profit percentage')
    parser.add_argument('--sl-pct', type=float, help='Stop loss percentage')
    parser.add_argument('--live', action='store_true', help='Use live trading')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')

    args = parser.parse_args()

    # Get API
    if args.live:
        api = alpaca.REST(LIVE_API_KEY, LIVE_SECRET_KEY, LIVE_BASE_URL)
    else:
        api = alpaca.REST(PAPER_API_KEY, PAPER_SECRET_KEY, PAPER_BASE_URL)

    # Determine entry type
    if args.market:
        entry_type = 'market'
        entry_price = None
    elif args.limit:
        entry_type = 'limit'
        entry_price = args.limit
    else:
        entry_type = 'limit'
        entry_price = None

    bracket_order(
        api=api,
        symbol=args.symbol.upper(),
        quantity=args.quantity,
        entry_type=entry_type,
        entry_price=entry_price,
        tp_offset=args.tp_offset,
        sl_offset=args.sl_offset,
        tp_pct=args.tp_pct,
        sl_pct=args.sl_pct,
        verbose=args.verbose
    )


if __name__ == '__main__':
    main()
