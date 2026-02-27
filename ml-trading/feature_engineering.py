"""
Feature Engineering for ML Trading
Generates technical indicators and features from price data
"""
import numpy as np
import pandas as pd
from ml_config import FEATURE_CONFIG


class FeatureEngineer:
    """Generate technical indicators and features"""

    def __init__(self, config=None):
        self.config = config or FEATURE_CONFIG

    def add_all_features(self, df):
        """Add all features to dataframe"""
        df = df.copy()

        # Price features
        df = self._add_returns(df)
        df = self._add_moving_averages(df)
        df = self._add_momentum(df)
        df = self._add_volatility(df)
        df = self._add_volume_features(df)

        # Target variable
        df = self._add_target(df)

        return df

    def _add_returns(self, df):
        """Add return features"""
        for period in self.config['return_periods']:
            df[f'return_{period}'] = df['Close'].pct_change(period)
        df['log_return'] = np.log(df['Close'] / df['Close'].shift(1))
        return df

    def _add_moving_averages(self, df):
        """Add moving average features"""
        for period in self.config['sma_periods']:
            df[f'sma_{period}'] = df['Close'].rolling(period).mean()
            df[f'price_to_sma_{period}'] = df['Close'] / df[f'sma_{period}']

        for period in self.config['ema_periods']:
            df[f'ema_{period}'] = df['Close'].ewm(span=period).mean()

        # Crossovers
        df['sma_5_20_cross'] = (df['sma_5'] > df['sma_20']).astype(int)
        df['sma_10_50_cross'] = (df['sma_10'] > df['sma_50']).astype(int)

        return df

    def _add_momentum(self, df):
        """Add momentum indicators"""
        # RSI
        period = self.config['rsi_period']
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))

        # MACD
        fast = df['Close'].ewm(span=self.config['macd_fast']).mean()
        slow = df['Close'].ewm(span=self.config['macd_slow']).mean()
        df['macd'] = fast - slow
        df['macd_signal'] = df['macd'].ewm(span=self.config['macd_signal']).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']

        # Stochastic
        low_min = df['Low'].rolling(self.config['stoch_k']).min()
        high_max = df['High'].rolling(self.config['stoch_k']).max()
        df['stoch_k'] = 100 * (df['Close'] - low_min) / (high_max - low_min)
        df['stoch_d'] = df['stoch_k'].rolling(self.config['stoch_d']).mean()

        return df

    def _add_volatility(self, df):
        """Add volatility indicators"""
        # Bollinger Bands
        period = self.config['bb_period']
        std_dev = self.config['bb_std']
        df['bb_middle'] = df['Close'].rolling(period).mean()
        df['bb_std'] = df['Close'].rolling(period).std()
        df['bb_upper'] = df['bb_middle'] + std_dev * df['bb_std']
        df['bb_lower'] = df['bb_middle'] - std_dev * df['bb_std']
        df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle']
        df['bb_position'] = (df['Close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])

        # ATR
        period = self.config['atr_period']
        tr1 = df['High'] - df['Low']
        tr2 = abs(df['High'] - df['Close'].shift(1))
        tr3 = abs(df['Low'] - df['Close'].shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        df['atr'] = tr.rolling(period).mean()
        df['atr_ratio'] = df['atr'] / df['Close']

        return df

    def _add_volume_features(self, df):
        """Add volume-based features"""
        period = self.config['volume_sma_period']
        df['volume_sma'] = df['Volume'].rolling(period).mean()
        df['volume_ratio'] = df['Volume'] / df['volume_sma']
        df['volume_change'] = df['Volume'].pct_change()
        return df

    def _add_target(self, df):
        """Add target variable for prediction"""
        period = self.config['target_period']
        threshold = self.config['target_threshold']

        # Future return
        future_return = df['Close'].shift(-period) / df['Close'] - 1

        # Class labels: 2 = UP, 0 = DOWN, 1 = FLAT (XGBoost needs 0, 1, 2)
        df['target'] = 1  # FLAT
        df.loc[future_return > threshold, 'target'] = 2  # UP
        df.loc[future_return < -threshold, 'target'] = 0  # DOWN

        return df

    def get_feature_columns(self):
        """Get list of feature columns (excluding target)"""
        return [
            'return_1', 'return_5', 'return_10', 'return_20', 'log_return',
            'sma_5', 'sma_10', 'sma_20', 'sma_50',
            'price_to_sma_5', 'price_to_sma_10', 'price_to_sma_20', 'price_to_sma_50',
            'ema_5', 'ema_10', 'ema_20',
            'sma_5_20_cross', 'sma_10_50_cross',
            'rsi', 'macd', 'macd_signal', 'macd_hist',
            'stoch_k', 'stoch_d',
            'bb_width', 'bb_position',
            'atr', 'atr_ratio',
            'volume_ratio', 'volume_change'
        ]
