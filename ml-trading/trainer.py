"""
Training Pipeline for ML Trading
Handles data loading, training, and evaluation

Data sources (in order of preference):
1. Interactive Brokers Gateway (best data, real NBBO)
2. Alpaca (good data, but limited on basic plan)
3. yfinance (free fallback)
"""
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import alpaca_trade_api as alpaca
from ml_config import PAPER_API_KEY, PAPER_SECRET_KEY, PAPER_BASE_URL, TRAINING_CONFIG
from ml_config import MODELS_DIR, DATA_DIR
from feature_engineering import FeatureEngineer
from ensemble_model import EnsembleModel

# Try to import IB data provider
try:
    from ib_data_provider import IBDataProviderFallback
    IB_AVAILABLE = True
except ImportError:
    IB_AVAILABLE = False
    print("Warning: ib_data_provider not available. Install ib_insync for IB data.")


class Trainer:
    """Training pipeline for ML trading model"""

    def __init__(self, symbol, use_live=False):
        self.symbol = symbol
        # Only initialize Alpaca API if credentials are available
        if PAPER_API_KEY and PAPER_SECRET_KEY:
            self.api = alpaca.REST(
                key_id=PAPER_API_KEY,
                secret_key=PAPER_SECRET_KEY,
                base_url=PAPER_BASE_URL
            )
        else:
            self.api = None
        self.feature_engineer = FeatureEngineer()
        self.model = EnsembleModel()
        self.df = None
        self.X_train = None
        self.X_test = None
        self.y_train = None
        self.y_test = None

    def fetch_data(self, days=None):
        """Fetch historical data - tries IB first, then Alpaca, then yfinance"""
        days = days or TRAINING_CONFIG['lookback_days']

        print(f"Fetching {days} days of data for {self.symbol}...")

        # 1. Try IB Gateway first (best data source)
        if IB_AVAILABLE:
            try:
                print("  Trying IB Gateway...")
                ib_provider = IBDataProviderFallback()
                df = ib_provider.get_historical_bars(self.symbol, days)

                if df is not None and len(df) > 0:
                    self.df = df
                    print(f"  Loaded {len(self.df)} bars via IB Gateway")

                    # Save to cache
                    cache_path = f"{DATA_DIR}/{self.symbol}_daily.csv"
                    self.df.to_csv(cache_path, index=False)
                    print(f"  Cached to {cache_path}")

                    return self.df
            except Exception as e:
                print(f"  IB Gateway error: {e}")

        # 2. Try Alpaca (good but limited on basic plan)
        try:
            # Use get_bars with proper timeframe
            from alpaca.data.timeframe import TimeFrame
            from alpaca.data.historical.stock import StockHistoricalDataClient

            # Create data client
            data_client = StockHistoricalDataClient(
                api_key=PAPER_API_KEY,
                secret_key=PAPER_SECRET_KEY
            )

            # Fetch bars
            from alpaca.data.requests import StockBarsRequest
            request = StockBarsRequest(
                symbol_or_symbols=self.symbol,
                timeframe=TimeFrame.Day,
                start=start,
                end=end
            )

            bars_df = data_client.get_stock_bars(request)

            if bars_df is None or bars_df.df.empty:
                raise ValueError(f"No data returned for {self.symbol}")

            # Get the dataframe for our symbol
            df = bars_df.df

            # Reset index if multi-index
            if isinstance(df.index, pd.MultiIndex):
                df = df.loc[self.symbol]
                df = df.reset_index()

            # Rename columns to expected format
            df = df.rename(columns={
                'timestamp': 'Date',
                'open': 'Open',
                'high': 'High',
                'low': 'Low',
                'close': 'Close',
                'volume': 'Volume'
            })

            # Ensure Date column exists
            if 'Date' not in df.columns and df.index.name == 'timestamp':
                df = df.reset_index()
                df = df.rename(columns={'timestamp': 'Date'})

            self.df = df
            print(f"  Loaded {len(self.df)} bars")

            # Save to cache
            cache_path = f"{DATA_DIR}/{self.symbol}_daily.csv"
            self.df.to_csv(cache_path, index=False)
            print(f"  Cached to {cache_path}")

            return self.df

        except Exception as e:
            print(f"Error fetching data: {e}")

            # Try fallback: use yfinance if available
            try:
                import yfinance as yf
                print(f"  Trying yfinance as fallback...")
                ticker = yf.Ticker(self.symbol)
                df = ticker.history(period=f"{days}d")

                if df.empty:
                    raise ValueError(f"No data from yfinance for {self.symbol}")

                df = df.reset_index()
                df = df.rename(columns={'Date': 'Date', 'Datetime': 'Date'})
                df.columns = [c.capitalize() for c in df.columns]

                self.df = df
                print(f"  Loaded {len(self.df)} bars via yfinance")

                cache_path = f"{DATA_DIR}/{self.symbol}_daily.csv"
                self.df.to_csv(cache_path, index=False)
                print(f"  Cached to {cache_path}")

                return self.df

            except ImportError:
                print("  yfinance not available. Install with: pip install yfinance")
                return None
            except Exception as e2:
                print(f"  yfinance also failed: {e2}")
                return None

    def load_cached_data(self):
        """Load data from cache"""
        cache_path = f"{DATA_DIR}/{self.symbol}_daily.csv"
        try:
            self.df = pd.read_csv(cache_path)
            print(f"Loaded {len(self.df)} bars from cache")
            return self.df
        except FileNotFoundError:
            print("No cached data found. Run fetch_data() first.")
            return None

    def prepare_features(self):
        """Prepare features for training"""
        if self.df is None:
            raise ValueError("No data loaded. Run fetch_data() or load_cached_data() first.")

        print("Preparing features...")
        self.df = self.feature_engineer.add_all_features(self.df)

        # Get feature columns
        feature_cols = self.feature_engineer.get_feature_columns()

        # Drop NaN rows
        valid_df = self.df.dropna(subset=feature_cols + ['target'])
        print(f"  Valid samples: {len(valid_df)} / {len(self.df)}")

        # Split into train/test
        split_idx = int(len(valid_df) * TRAINING_CONFIG['train_test_split'])

        train_df = valid_df.iloc[:split_idx]
        test_df = valid_df.iloc[split_idx:]

        self.X_train = train_df[feature_cols].values
        self.y_train = train_df['target'].values
        self.X_test = test_df[feature_cols].values
        self.y_test = test_df['target'].values

        print(f"  Train: {len(self.X_train)} samples")
        print(f"  Test: {len(self.X_test)} samples")
        print(f"  Features: {len(feature_cols)}")

        return feature_cols

    def train(self):
        """Train the ensemble model"""
        if self.X_train is None:
            raise ValueError("Features not prepared. Run prepare_features() first.")

        print("\nTraining ensemble model...")
        self.model.fit(self.X_train, self.y_train)

        # Evaluate on test set
        from sklearn.metrics import accuracy_score, classification_report
        y_pred = self.model.predict(self.X_test)

        print("\nTest Set Results:")
        print(f"  Accuracy: {accuracy_score(self.y_test, y_pred):.4f}")
        print("\nClassification Report:")
        print(classification_report(self.y_test, y_pred, target_names=['DOWN', 'FLAT', 'UP']))

        return self.model

    def save_model(self, name=None):
        """Save trained model"""
        name = name or f"{self.symbol}_ensemble"
        self.model.save(name)
        print(f"Model saved as '{name}'")

    def run_full_training(self, days=None):
        """Run complete training pipeline"""
        print(f"\n{'='*60}")
        print(f"FULL TRAINING PIPELINE: {self.symbol}")
        print(f"{'='*60}")

        # 1. Fetch data
        self.fetch_data(days)

        # 2. Prepare features
        feature_cols = self.prepare_features()

        # 3. Train model
        self.train()

        # 4. Show feature importance
        importance = self.model.get_feature_importance(feature_cols)
        print("\nTop 10 Features:")
        for name, imp in list(importance.items())[:10]:
            print(f"  {name}: {imp:.4f}")

        # 5. Save model
        self.save_model()

        print(f"\n{'='*60}")
        print("TRAINING COMPLETE")
        print(f"{'='*60}")

        return self.model


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("Usage: python trainer.py SYMBOL [DAYS]")
        print("Example: python trainer.py SOXL 500")
        sys.exit(1)

    symbol = sys.argv[1].upper()
    days = int(sys.argv[2]) if len(sys.argv) > 2 else None

    trainer = Trainer(symbol)
    trainer.run_full_training(days)
# Build fix Fri Feb 27 14:25:55 CST 2026
