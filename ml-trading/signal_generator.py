"""
Signal Generator for ML Trading
Generates trading signals from trained model

Data sources (in order of preference):
1. Interactive Brokers Gateway (real NBBO quotes)
2. Alpaca (IEX quotes, limited on basic plan)
3. yfinance (free fallback)
"""
import numpy as np
import pandas as pd
from feature_engineering import FeatureEngineer
from ensemble_model import EnsembleModel
from ml_config import SIGNAL_CONFIG, MODELS_DIR

# Try to import IB data provider
try:
    from ib_data_provider import IBDataProviderFallback
    IB_AVAILABLE = True
except ImportError:
    IB_AVAILABLE = False


class SignalGenerator:
    """Generate trading signals from ML model"""

    def __init__(self, symbol, model_name=None):
        self.symbol = symbol
        self.model_name = model_name or f"{symbol}_ensemble"
        self.feature_engineer = FeatureEngineer()
        self.model = EnsembleModel()

        # Load model
        try:
            self.model.load(self.model_name)
        except Exception as e:
            print(f"Warning: Could not load model: {e}")

    def prepare_features(self, df):
        """Prepare features from price data"""
        df = self.feature_engineer.add_all_features(df)
        feature_cols = self.feature_engineer.get_feature_columns()
        return df, feature_cols

    def generate_signal(self, df):
        """
        Generate trading signal from latest data

        Returns:
            dict with keys: signal, confidence, probabilities
        """
        df, feature_cols = self.prepare_features(df)

        # Get latest valid row
        valid_df = df.dropna(subset=feature_cols)
        if len(valid_df) == 0:
            return {'signal': 'HOLD', 'confidence': 0, 'probabilities': {}}

        latest = valid_df.iloc[[-1]]
        X = latest[feature_cols].values

        # Get prediction and probabilities
        prediction = self.model.predict(X)[0]
        probabilities = self.model.predict_proba(X)[0]

        # Class labels
        classes = self.model.rf_model.classes_
        prob_dict = {int(c): float(p) for c, p in zip(classes, probabilities)}

        # Determine signal (classes: 0=DOWN, 1=FLAT, 2=UP)
        confidence = max(probabilities)

        if confidence < SIGNAL_CONFIG['confidence_threshold']:
            signal = 'HOLD'
        elif prediction == 2:  # UP
            signal = 'BUY'
        elif prediction == 0:  # DOWN
            signal = 'SELL'
        else:
            signal = 'HOLD'

        return {
            'signal': signal,
            'confidence': confidence,
            'prediction': int(prediction),
            'probabilities': prob_dict
        }

    def generate_signals_series(self, df):
        """Generate signals for entire dataframe"""
        df, feature_cols = self.prepare_features(df)
        valid_df = df.dropna(subset=feature_cols).copy()

        if len(valid_df) == 0:
            return pd.DataFrame()

        X = valid_df[feature_cols].values
        predictions = self.model.predict(X)
        probabilities = self.model.predict_proba(X)

        # Get class labels
        classes = self.model.rf_model.classes_

        # Create results dataframe
        results = pd.DataFrame(index=valid_df.index)
        results['prediction'] = predictions
        results['confidence'] = probabilities.max(axis=1)

        # Map class probabilities
        for i, c in enumerate(classes):
            results[f'prob_{int(c)}'] = probabilities[:, i]

        # Generate signals (classes: 0=DOWN, 1=FLAT, 2=UP)
        results['signal'] = 'HOLD'
        results.loc[(results['prediction'] == 2) &
                   (results['confidence'] >= SIGNAL_CONFIG['confidence_threshold']), 'signal'] = 'BUY'
        results.loc[(results['prediction'] == 0) &
                   (results['confidence'] >= SIGNAL_CONFIG['confidence_threshold']), 'signal'] = 'SELL'

        return results

    def get_latest_signal(self):
        """Get signal for latest market data"""
        from datetime import datetime, timedelta

        # 1. Try IB Gateway first (best data source with real NBBO)
        if IB_AVAILABLE:
            try:
                print(f"Fetching latest data for {self.symbol} via IB Gateway...")
                ib_provider = IBDataProviderFallback()
                df = ib_provider.get_historical_bars(self.symbol, days=100)

                if df is not None and len(df) > 0:
                    return self.generate_signal(df)
            except Exception as e:
                print(f"IB Gateway error: {e}")

        # 2. Try yfinance (works with free data)
        try:
            import yfinance as yf
            print(f"Fetching latest data for {self.symbol} via yfinance...")
            ticker = yf.Ticker(self.symbol)
            df = ticker.history(period="100d")

            if df.empty:
                return {'signal': 'HOLD', 'confidence': 0, 'error': 'No data from yfinance'}

            df = df.reset_index()
            df.columns = [c.capitalize() for c in df.columns]

            return self.generate_signal(df)

        except Exception as e:
            print(f"yfinance error: {e}")

            # Fallback to Alpaca
            try:
                import alpaca_trade_api as alpaca
                from ml_config import PAPER_API_KEY, PAPER_SECRET_KEY, PAPER_BASE_URL

                api = alpaca.REST(
                    key_id=PAPER_API_KEY,
                    secret_key=PAPER_SECRET_KEY,
                    base_url=PAPER_BASE_URL
                )

                end = datetime.now()
                start = end - timedelta(days=100)

                bars = api.get_bars(
                    self.symbol,
                    '1Day',
                    start=start.strftime('%Y-%m-%d'),
                    end=end.strftime('%Y-%m-%d')
                ).df

                if bars.empty:
                    return {'signal': 'HOLD', 'confidence': 0, 'error': 'No data'}

                bars = bars.reset_index()
                bars = bars.rename(columns={'timestamp': 'Date'})
                if 'Close' not in bars.columns:
                    bars['Close'] = bars['close']
                    bars['Open'] = bars['open']
                    bars['High'] = bars['high']
                    bars['Low'] = bars['low']
                    bars['Volume'] = bars['volume']

                return self.generate_signal(bars)

            except Exception as e2:
                return {'signal': 'HOLD', 'confidence': 0, 'error': str(e2)}

    def get_realtime_quote(self):
        """Get real-time NBBO quote for the symbol"""
        if IB_AVAILABLE:
            try:
                ib_provider = IBDataProviderFallback()
                quote = ib_provider.get_realtime_quote(self.symbol)
                if quote:
                    return quote
            except Exception as e:
                print(f"IB quote error: {e}")

        # Fallback to yfinance
        try:
            import yfinance as yf
            ticker = yf.Ticker(self.symbol)
            info = ticker.info
            return {
                'symbol': self.symbol,
                'bid': info.get('bid'),
                'ask': info.get('ask'),
                'last': info.get('currentPrice') or info.get('regularMarketPrice'),
                'volume': info.get('volume'),
                'source': 'yfinance'
            }
        except Exception as e:
            return {'symbol': self.symbol, 'error': str(e)}


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("Usage: python signal_generator.py SYMBOL")
        print("Example: python signal_generator.py SOXL")
        sys.exit(1)

    symbol = sys.argv[1].upper()
    generator = SignalGenerator(symbol)

    signal = generator.get_latest_signal()
    print(f"\nSignal for {symbol}:")
    print(f"  Signal: {signal['signal']}")
    print(f"  Confidence: {signal['confidence']:.2%}")
    print(f"  Probabilities: UP={signal['probabilities'].get(2, 0):.2%}, "
          f"DOWN={signal['probabilities'].get(0, 0):.2%}, "
          f"FLAT={signal['probabilities'].get(1, 0):.2%}")
