"""
Walk-Forward Validation for ML Trading
Provides realistic backtest results by training on past data and testing on future
"""
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import logging

from ml_config import FEATURE_CONFIG, ENSEMBLE_CONFIG, SIGNAL_CONFIG
from feature_engineering import FeatureEngineer
from ensemble_model import EnsembleModel

logger = logging.getLogger(__name__)


class WalkForwardValidator:
    """
    Walk-forward validation for ML trading models

    Provides realistic backtest by:
    1. Training on historical data
    2. Testing on future (unseen) data
    3. Rolling forward and repeating

    This prevents look-ahead bias and gives accurate performance estimates
    """

    def __init__(self, symbol: str, df: pd.DataFrame,
                 train_window: int = 252,  # 1 year of trading days
                 test_window: int = 63,    # 3 months of trading days
                 step_size: int = 21):     # 1 month steps
        """
        Initialize walk-forward validator

        Args:
            symbol: Trading symbol
            df: DataFrame with OHLCV data
            train_window: Number of bars to train on
            test_window: Number of bars to test on
            step_size: Number of bars to roll forward each iteration
        """
        self.symbol = symbol
        self.df = df.copy()
        self.train_window = train_window
        self.test_window = test_window
        self.step_size = step_size

        self.feature_engineer = FeatureEngineer()
        self.results = []

    def prepare_data(self) -> pd.DataFrame:
        """Prepare features for the entire dataset"""
        logger.info(f"Preparing features for {len(self.df)} bars...")

        df = self.feature_engineer.add_all_features(self.df)
        feature_cols = self.feature_engineer.get_feature_columns()

        # Drop NaN rows
        valid_df = df.dropna(subset=feature_cols + ['target'])

        logger.info(f"Valid samples: {len(valid_df)} / {len(self.df)}")

        return valid_df, feature_cols

    def run_validation(self, min_confidence: float = 0.6) -> Dict:
        """
        Run walk-forward validation

        Args:
            min_confidence: Minimum confidence to generate a trade signal

        Returns:
            Dictionary with validation results
        """
        df, feature_cols = self.prepare_data()

        if len(df) < self.train_window + self.test_window:
            raise ValueError(f"Not enough data for walk-forward validation. Need at least {self.train_window + self.test_window} bars")

        logger.info(f"\n{'='*60}")
        logger.info(f"WALK-FORWARD VALIDATION: {self.symbol}")
        logger.info(f"{'='*60}")
        logger.info(f"Train window: {self.train_window} bars")
        logger.info(f"Test window: {self.test_window} bars")
        logger.info(f"Step size: {self.step_size} bars")
        logger.info(f"Total samples: {len(df)}")

        self.results = []
        all_predictions = []
        all_returns = []

        # Walk forward through the data
        start_idx = 0
        fold_num = 0

        while start_idx + self.train_window + self.test_window <= len(df):
            fold_num += 1

            # Define train and test indices
            train_end = start_idx + self.train_window
            test_end = train_end + self.test_window

            train_df = df.iloc[start_idx:train_end]
            test_df = df.iloc[train_end:test_end]

            logger.info(f"\n--- Fold {fold_num} ---")
            logger.info(f"Train: {train_df.index[0]} to {train_df.index[-1]} ({len(train_df)} bars)")
            logger.info(f"Test: {test_df.index[0]} to {test_df.index[-1]} ({len(test_df)} bars)")

            # Train model
            X_train = train_df[feature_cols].values
            y_train = train_df['target'].values

            model = EnsembleModel()
            model.fit(X_train, y_train)

            # Test model
            X_test = test_df[feature_cols].values
            y_test = test_df['target'].values

            predictions = model.predict(X_test)
            probabilities = model.predict_proba(X_test)

            # Calculate fold metrics
            accuracy = np.mean(predictions == y_test)

            # Generate trading signals
            test_df = test_df.copy()
            test_df['prediction'] = predictions
            test_df['confidence'] = probabilities.max(axis=1)
            test_df['signal'] = 'HOLD'

            # Apply confidence threshold
            test_df.loc[(test_df['prediction'] == 2) &
                       (test_df['confidence'] >= min_confidence), 'signal'] = 'BUY'
            test_df.loc[(test_df['prediction'] == 0) &
                       (test_df['confidence'] >= min_confidence), 'signal'] = 'SELL'

            # Simulate trading
            fold_returns = self._simulate_trading(test_df)

            fold_result = {
                'fold': fold_num,
                'train_start': str(train_df.index[0]),
                'train_end': str(train_df.index[-1]),
                'test_start': str(test_df.index[0]),
                'test_end': str(test_df.index[-1]),
                'accuracy': accuracy,
                'trades': len(fold_returns),
                'total_return': sum(fold_returns),
                'avg_return': np.mean(fold_returns) if fold_returns else 0,
                'win_rate': np.mean([r > 0 for r in fold_returns]) if fold_returns else 0
            }

            self.results.append(fold_result)
            all_returns.extend(fold_returns)

            logger.info(f"Accuracy: {accuracy:.2%}")
            logger.info(f"Trades: {fold_result['trades']}")
            logger.info(f"Return: {fold_result['total_return']:.2%}")
            logger.info(f"Win Rate: {fold_result['win_rate']:.2%}")

            # Move to next window
            start_idx += self.step_size

        # Calculate overall metrics
        overall_metrics = self._calculate_overall_metrics(all_returns)

        return {
            'symbol': self.symbol,
            'folds': len(self.results),
            'fold_results': self.results,
            'overall': overall_metrics
        }

    def _simulate_trading(self, df: pd.DataFrame) -> List[float]:
        """
        Simulate trading on test data

        Returns list of trade returns
        """
        returns = []
        position = 0
        entry_price = 0

        for i, row in df.iterrows():
            signal = row['signal']
            price = row['Close']

            if signal == 'BUY' and position == 0:
                # Open long position
                position = 1
                entry_price = price

            elif signal == 'SELL' and position == 1:
                # Close long position
                trade_return = (price - entry_price) / entry_price
                returns.append(trade_return)
                position = 0
                entry_price = 0

        # Close any remaining position at end
        if position == 1:
            final_price = df.iloc[-1]['Close']
            trade_return = (final_price - entry_price) / entry_price
            returns.append(trade_return)

        return returns

    def _calculate_overall_metrics(self, all_returns: List[float]) -> Dict:
        """Calculate overall performance metrics"""
        if not all_returns:
            return {
                'total_trades': 0,
                'total_return': 0,
                'avg_return': 0,
                'win_rate': 0,
                'sharpe_ratio': 0,
                'max_drawdown': 0
            }

        # Calculate cumulative returns
        cumulative = 1.0
        cumulative_series = []

        for r in all_returns:
            cumulative *= (1 + r)
            cumulative_series.append(cumulative)

        total_return = cumulative - 1
        avg_return = np.mean(all_returns)
        win_rate = np.mean([r > 0 for r in all_returns])

        # Calculate Sharpe ratio (annualized)
        if len(all_returns) > 1 and np.std(all_returns) > 0:
            sharpe = (np.mean(all_returns) / np.std(all_returns)) * np.sqrt(252 / 5)  # Assuming 5-day holding
        else:
            sharpe = 0

        # Calculate max drawdown
        peak = 1.0
        max_dd = 0

        for c in cumulative_series:
            if c > peak:
                peak = c
            dd = (peak - c) / peak
            if dd > max_dd:
                max_dd = dd

        return {
            'total_trades': len(all_returns),
            'total_return': float(total_return),
            'avg_return': float(avg_return),
            'win_rate': float(win_rate),
            'sharpe_ratio': float(sharpe),
            'max_drawdown': float(max_dd)
        }

    def print_summary(self, results: Dict):
        """Print validation summary"""
        print(f"\n{'='*70}")
        print(f"WALK-FORWARD VALIDATION RESULTS: {results['symbol']}")
        print(f"{'='*70}")

        print(f"\nFolds: {results['folds']}")

        print(f"\n{'Fold':<6} {'Accuracy':<12} {'Trades':<10} {'Return':<12} {'Win Rate':<12}")
        print("-" * 52)

        for fold in results['fold_results']:
            print(f"{fold['fold']:<6} {fold['accuracy']:>10.2%} {fold['trades']:>10} {fold['total_return']:>10.2%} {fold['win_rate']:>10.2%}")

        print("-" * 52)

        overall = results['overall']
        print(f"\nOVERALL PERFORMANCE:")
        print(f"  Total Trades:     {overall['total_trades']}")
        print(f"  Total Return:     {overall['total_return']:.2%}")
        print(f"  Avg Trade Return: {overall['avg_return']:.2%}")
        print(f"  Win Rate:         {overall['win_rate']:.2%}")
        print(f"  Sharpe Ratio:     {overall['sharpe_ratio']:.2f}")
        print(f"  Max Drawdown:     {overall['max_drawdown']:.2%}")

        print(f"\n{'='*70}\n")


def run_walk_forward_validation(symbol: str, days: int = 500) -> Dict:
    """
    Run walk-forward validation for a symbol

    Args:
        symbol: Trading symbol
        days: Number of days of historical data

    Returns:
        Validation results
    """
    # Fetch data
    try:
        from ib_data_provider import IBDataProviderFallback
        provider = IBDataProviderFallback()
        df = provider.get_historical_bars(symbol, days)
    except:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=f"{days}d")
        df = df.reset_index()
        df.columns = [c.capitalize() for c in df.columns]

    if df is None or len(df) == 0:
        raise ValueError(f"Could not fetch data for {symbol}")

    # Run validation
    validator = WalkForwardValidator(symbol, df)
    results = validator.run_validation()
    validator.print_summary(results)

    return results


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("Usage: python walk_forward.py SYMBOL [DAYS]")
        print("Example: python walk_forward.py SOXL 500")
        sys.exit(1)

    symbol = sys.argv[1].upper()
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 500

    run_walk_forward_validation(symbol, days)
