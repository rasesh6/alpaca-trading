#!/usr/bin/env python3
"""
ML Trading System - Main Entry Point

Usage:
    python run.py train SYMBOL [DAYS]     # Train new model
    python run.py signal SYMBOL           # Get current signal
    python run.py backtest SYMBOL [DAYS]  # Backtest strategy
    python run.py full SYMBOL [DAYS]      # Train + backtest

Examples:
    python run.py train SOXL 500
    python run.py signal SOXL
    python run.py backtest SOXL 500
    python run.py full SOXL 500
"""
import sys
import os

# Add parent directory for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def print_usage():
    print(__doc__)


def train_model(symbol, days=None):
    """Train a new model"""
    from trainer import Trainer
    trainer = Trainer(symbol)
    trainer.run_full_training(days)
    return trainer.model


def get_signal(symbol):
    """Get current trading signal"""
    from signal_generator import SignalGenerator
    generator = SignalGenerator(symbol)
    signal = generator.get_latest_signal()

    print(f"\n{'='*50}")
    print(f"ML SIGNAL: {symbol}")
    print(f"{'='*50}")
    print(f"Signal:     {signal['signal']}")
    print(f"Confidence: {signal['confidence']:.2%}")
    print(f"Probabilities:")
    print(f"  UP:   {signal['probabilities'].get(1, 0):.2%}")
    print(f"  DOWN: {signal['probabilities'].get(-1, 0):.2%}")
    print(f"  FLAT: {signal['probabilities'].get(0, 0):.2%}")
    print(f"{'='*50}\n")

    return signal


def run_backtest(symbol, days=500):
    """Run backtest"""
    from backtester import Backtester
    backtester = Backtester(symbol)
    backtester.load_data(days)
    backtester.run_backtest()
    backtester.print_results()
    return backtester.results


def full_pipeline(symbol, days=None):
    """Train + backtest"""
    print(f"\n{'#'*60}")
    print(f"# FULL ML TRADING PIPELINE: {symbol}")
    print(f"{'#'*60}\n")

    # Train
    print("STEP 1: Training Model")
    print("-" * 40)
    train_model(symbol, days)

    # Signal
    print("\nSTEP 2: Current Signal")
    print("-" * 40)
    get_signal(symbol)

    # Backtest
    print("\nSTEP 3: Backtesting")
    print("-" * 40)
    run_backtest(symbol, days or 500)


def main():
    if len(sys.argv) < 3:
        print_usage()
        sys.exit(1)

    command = sys.argv[1].lower()
    symbol = sys.argv[2].upper()
    days = int(sys.argv[3]) if len(sys.argv) > 3 else None

    if command == 'train':
        train_model(symbol, days)
    elif command == 'signal':
        get_signal(symbol)
    elif command == 'backtest':
        run_backtest(symbol, days or 500)
    elif command == 'full':
        full_pipeline(symbol, days)
    else:
        print(f"Unknown command: {command}")
        print_usage()
        sys.exit(1)


if __name__ == '__main__':
    main()
