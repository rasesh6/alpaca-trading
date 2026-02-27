#!/usr/bin/env python3
"""
Position Management Script

Usage:
    python position.py                    # Show all positions
    python position.py close SYMBOL       # Close position (market)
    python position.py close SYMBOL 50    # Close 50% of position
    python position.py close-all          # Close all positions

Examples:
    python position.py
    python position.py close SOXL
    python position.py close SOXL 50
    python position.py close-all
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import PAPER_API_KEY, PAPER_SECRET_KEY, PAPER_BASE_URL
from config import LIVE_API_KEY, LIVE_SECRET_KEY, LIVE_BASE_URL
import alpaca_trade_api as alpaca


def get_api(use_live=False):
    """Get API instance"""
    if use_live:
        return alpaca.REST(
            key_id=LIVE_API_KEY,
            secret_key=LIVE_SECRET_KEY,
            base_url=LIVE_BASE_URL
        )
    return alpaca.REST(
        key_id=PAPER_API_KEY,
        secret_key=PAPER_SECRET_KEY,
        base_url=PAPER_BASE_URL
    )


def show_positions(api):
    """Display all open positions"""
    try:
        positions = api.list_positions()
        account = api.get_account()

        print("\n" + "="*90)
        print(f"Portfolio Value: ${float(account.equity):,.2f} | Cash: ${float(account.cash):,.2f} | Buying Power: ${float(account.buying_power):,.2f}")
        print("="*90)

        if not positions:
            print("No open positions")
            print("="*90 + "\n")
            return

        print(f"{'Symbol':<8} {'Qty':>8} {'Avg Cost':>10} {'Current':>10} {'Value':>12} {'P/L':>10} {'P/L %':>10}")
        print("-"*90)

        total_pl = 0
        for pos in positions:
            qty = float(pos.qty)
            avg_cost = float(pos.avg_entry_price)
            current = float(pos.current_price)
            value = float(pos.market_value)
            pl = float(pos.unrealized_pl)
            pl_pct = float(pos.unrealized_plpc) * 100
            total_pl += pl

            pl_str = f"+${pl:.2f}" if pl >= 0 else f"-${abs(pl):.2f}"
            pl_pct_str = f"+{pl_pct:.2f}%" if pl_pct >= 0 else f"{pl_pct:.2f}%"

            print(f"{pos.symbol:<8} {qty:>8.0f} ${avg_cost:>9.2f} ${current:>9.2f} ${value:>11.2f} {pl_str:>10} {pl_pct_str:>10}")

        print("-"*90)
        total_str = f"+${total_pl:.2f}" if total_pl >= 0 else f"-${abs(total_pl):.2f}"
        print(f"{'TOTAL':<8} {'':<8} {'':<10} {'':<10} {'':<12} {total_str:>10}")
        print("="*90 + "\n")

    except Exception as e:
        print(f"Error: {e}")


def close_position(api, symbol, percentage=None):
    """Close a position (full or partial)"""
    try:
        if percentage:
            result = api.close_position(symbol, percentage=percentage)
            print(f"Closing {percentage}% of {symbol} position...")
        else:
            result = api.close_position(symbol)
            print(f"Closing entire {symbol} position...")

        print(f"Order submitted: {result.id}")
        print(f"Status: {result.status}")
        return result
    except Exception as e:
        print(f"Error closing position: {e}")
        return None


def close_all_positions(api):
    """Close all positions"""
    try:
        print("Closing all positions...")
        results = api.close_all_positions()
        for result in results:
            print(f"  {result.symbol}: Order {result.id} - {result.status}")
        return results
    except Exception as e:
        print(f"Error closing positions: {e}")
        return None


def main():
    use_live = '--live' in sys.argv
    if use_live:
        sys.argv.remove('--live')

    api = get_api(use_live)

    if len(sys.argv) == 1:
        show_positions(api)
        return

    command = sys.argv[1].lower()

    if command == 'close' and len(sys.argv) >= 3:
        symbol = sys.argv[2].upper()
        percentage = float(sys.argv[3]) if len(sys.argv) > 3 else None
        close_position(api, symbol, percentage)
        show_positions(api)

    elif command == 'close-all':
        close_all_positions(api)
        show_positions(api)

    else:
        print("Usage:")
        print("  python position.py                    # Show all positions")
        print("  python position.py close SYMBOL       # Close position")
        print("  python position.py close SYMBOL 50    # Close 50% of position")
        print("  python position.py close-all          # Close all positions")


if __name__ == '__main__':
    main()
