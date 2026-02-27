"""
Backtester for ML Trading
Evaluates strategy performance on historical data
"""
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import alpaca_trade_api as alpaca
from config import PAPER_API_KEY, PAPER_SECRET_KEY, PAPER_BASE_URL, DATA_DIR
from feature_engineering import FeatureEngineer
from ensemble_model import EnsembleModel
from signal_generator import SignalGenerator


class Backtester:
    """Backtest ML trading strategy"""

    def __init__(self, symbol, initial_capital=10000):
        self.symbol = symbol
        self.initial_capital = initial_capital
        self.api = alpaca.REST(
            key_id=PAPER_API_KEY,
            secret_key=PAPER_SECRET_KEY,
            base_url=PAPER_BASE_URL
        )
        self.df = None
        self.signals = None
        self.results = None

    def load_data(self, days=500):
        """Load historical data"""
        print(f"Loading {days} days of data for {self.symbol}...")

        # Try yfinance first
        try:
            import yfinance as yf
            ticker = yf.Ticker(self.symbol)
            self.df = ticker.history(period=f"{days}d")

            if self.df.empty:
                raise ValueError(f"No data from yfinance for {self.symbol}")

            self.df = self.df.reset_index()
            self.df.columns = [c.capitalize() for c in self.df.columns]

            print(f"  Loaded {len(self.df)} bars via yfinance")
            return self.df

        except Exception as e:
            print(f"yfinance error: {e}, trying Alpaca...")

        # Fallback to Alpaca
        end = datetime.now()
        start = end - timedelta(days=days)

        bars = self.api.get_bars(
            self.symbol,
            '1Day',
            start=start.strftime('%Y-%m-%d'),
            end=end.strftime('%Y-%m-%d')
        ).df

        if bars.empty:
            raise ValueError(f"No data returned for {self.symbol}")

        bars = bars.reset_index()
        bars = bars.rename(columns={'timestamp': 'Date'})

        if 'Close' not in bars.columns:
            bars['Close'] = bars['close']
            bars['Open'] = bars['open']
            bars['High'] = bars['high']
            bars['Low'] = bars['low']
            bars['Volume'] = bars['volume']

        self.df = bars
        print(f"  Loaded {len(self.df)} bars")
        return self.df

    def run_backtest(self, model_name=None, confidence_threshold=0.6):
        """Run backtest with trained model"""
        if self.df is None:
            self.load_data()

        # Generate signals
        signal_gen = SignalGenerator(self.symbol, model_name)
        self.signals = signal_gen.generate_signals_series(self.df)

        if self.signals.empty:
            raise ValueError("Could not generate signals")

        # Merge with price data
        backtest_df = self.df.copy()
        backtest_df = backtest_df.loc[self.signals.index]
        backtest_df['signal'] = self.signals['signal']
        backtest_df['confidence'] = self.signals['confidence']

        # Filter by confidence
        backtest_df['trade_signal'] = backtest_df.apply(
            lambda x: x['signal'] if x['confidence'] >= confidence_threshold else 'HOLD',
            axis=1
        )

        # Simulate trading
        capital = self.initial_capital
        position = 0
        shares = 0
        trades = []

        for i, row in backtest_df.iterrows():
            price = row['Close']
            signal = row['trade_signal']

            if signal == 'BUY' and position == 0:
                # Buy
                shares = int(capital / price)
                if shares > 0:
                    cost = shares * price
                    capital -= cost
                    position = 1
                    trades.append({
                        'date': row['Date'],
                        'type': 'BUY',
                        'price': price,
                        'shares': shares,
                        'capital': capital
                    })

            elif signal == 'SELL' and position == 1:
                # Sell
                revenue = shares * price
                capital += revenue
                position = 0
                trades.append({
                    'date': row['Date'],
                    'type': 'SELL',
                    'price': price,
                    'shares': shares,
                    'capital': capital
                })
                shares = 0

        # Close any remaining position
        if position == 1:
            final_price = backtest_df.iloc[-1]['Close']
            capital += shares * final_price
            position = 0

        # Calculate final value
        final_value = capital

        # Calculate metrics
        total_return = (final_value - self.initial_capital) / self.initial_capital

        # Buy and hold return
        first_price = backtest_df.iloc[0]['Close']
        last_price = backtest_df.iloc[-1]['Close']
        bh_return = (last_price - first_price) / first_price

        # Calculate Sharpe (simplified)
        daily_returns = backtest_df['Close'].pct_change().dropna()
        sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252) if daily_returns.std() > 0 else 0

        # Win rate
        winning_trades = 0
        total_trades = len(trades) // 2
        for i in range(0, len(trades) - 1, 2):
            if i + 1 < len(trades):
                buy_trade = trades[i]
                sell_trade = trades[i + 1]
                if sell_trade['price'] > buy_trade['price']:
                    winning_trades += 1

        win_rate = winning_trades / total_trades if total_trades > 0 else 0

        self.results = {
            'initial_capital': self.initial_capital,
            'final_value': final_value,
            'total_return': total_return,
            'buy_hold_return': bh_return,
            'sharpe_ratio': sharpe,
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'win_rate': win_rate,
            'trades': trades
        }

        return self.results

    def print_results(self):
        """Print backtest results"""
        if self.results is None:
            print("No results. Run run_backtest() first.")
            return

        r = self.results
        print(f"\n{'='*60}")
        print(f"BACKTEST RESULTS: {self.symbol}")
        print(f"{'='*60}")
        print(f"Initial Capital:    ${r['initial_capital']:,.2f}")
        print(f"Final Value:        ${r['final_value']:,.2f}")
        print(f"Total Return:       {r['total_return']:.2%}")
        print(f"Buy & Hold Return:  {r['buy_hold_return']:.2%}")
        print(f"Sharpe Ratio:       {r['sharpe_ratio']:.2f}")
        print(f"Total Trades:       {r['total_trades']}")
        print(f"Winning Trades:     {r['winning_trades']}")
        print(f"Win Rate:           {r['win_rate']:.2%}")
        print(f"{'='*60}\n")


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("Usage: python backtester.py SYMBOL [DAYS]")
        print("Example: python backtester.py SOXL 500")
        sys.exit(1)

    symbol = sys.argv[1].upper()
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 500

    backtester = Backtester(symbol)
    backtester.load_data(days)
    backtester.run_backtest()
    backtester.print_results()
