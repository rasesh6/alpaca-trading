"""
ML Trading System Configuration
"""
import os
import sys

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
MODELS_DIR = os.path.join(BASE_DIR, 'models')

# Ensure directories exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(MODELS_DIR, exist_ok=True)

# Alpaca API credentials
# Try to load from parent config, otherwise use environment variables
PARENT_DIR = os.path.dirname(BASE_DIR)
parent_config_path = os.path.join(PARENT_DIR, "config.py")

if os.path.exists(parent_config_path):
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("parent_config", parent_config_path)
        parent_config = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(parent_config)

        PAPER_API_KEY = parent_config.PAPER_API_KEY or os.getenv('PAPER_API_KEY', '')
        PAPER_SECRET_KEY = parent_config.PAPER_SECRET_KEY or os.getenv('PAPER_SECRET_KEY', '')
        PAPER_BASE_URL = parent_config.PAPER_BASE_URL or os.getenv('PAPER_BASE_URL', 'https://paper-api.alpaca.markets')
        LIVE_API_KEY = getattr(parent_config, 'LIVE_API_KEY', None) or os.getenv('LIVE_API_KEY', '')
        LIVE_SECRET_KEY = getattr(parent_config, 'LIVE_SECRET_KEY', None) or os.getenv('LIVE_SECRET_KEY', '')
        LIVE_BASE_URL = getattr(parent_config, 'LIVE_BASE_URL', None) or os.getenv('LIVE_BASE_URL', 'https://api.alpaca.markets')
    except Exception as e:
        print(f"Warning: Could not load parent config: {e}")
        PAPER_API_KEY = os.getenv('PAPER_API_KEY', '')
        PAPER_SECRET_KEY = os.getenv('PAPER_SECRET_KEY', '')
        PAPER_BASE_URL = os.getenv('PAPER_BASE_URL', 'https://paper-api.alpaca.markets')
        LIVE_API_KEY = os.getenv('LIVE_API_KEY', '')
        LIVE_SECRET_KEY = os.getenv('LIVE_SECRET_KEY', '')
        LIVE_BASE_URL = os.getenv('LIVE_BASE_URL', 'https://api.alpaca.markets')
else:
    # Use environment variables directly
    PAPER_API_KEY = os.getenv('PAPER_API_KEY', '')
    PAPER_SECRET_KEY = os.getenv('PAPER_SECRET_KEY', '')
    PAPER_BASE_URL = os.getenv('PAPER_BASE_URL', 'https://paper-api.alpaca.markets')
    LIVE_API_KEY = os.getenv('LIVE_API_KEY', '')
    LIVE_SECRET_KEY = os.getenv('LIVE_SECRET_KEY', '')
    LIVE_BASE_URL = os.getenv('LIVE_BASE_URL', 'https://api.alpaca.markets')

# Model parameters
ENSEMBLE_CONFIG = {
    # Random Forest
    'rf_n_estimators': 200,
    'rf_max_depth': 10,
    'rf_min_samples_split': 5,
    'rf_min_samples_leaf': 2,

    # XGBoost
    'xgb_n_estimators': 200,
    'xgb_max_depth': 6,
    'xgb_learning_rate': 0.1,
    'xgb_subsample': 0.8,
    'xgb_colsample_bytree': 0.8,

    # LightGBM
    'lgb_n_estimators': 200,
    'lgb_max_depth': 6,
    'lgb_learning_rate': 0.1,
    'lgb_num_leaves': 31,

    # Ensemble weights
    'rf_weight': 0.4,
    'xgb_weight': 0.35,
    'lgb_weight': 0.25,
}

# Feature engineering
FEATURE_CONFIG = {
    # Moving averages
    'sma_periods': [5, 10, 20, 50],
    'ema_periods': [5, 10, 20],

    # Momentum
    'rsi_period': 14,
    'macd_fast': 12,
    'macd_slow': 26,
    'macd_signal': 9,
    'stoch_k': 14,
    'stoch_d': 3,

    # Volatility
    'bb_period': 20,
    'bb_std': 2,
    'atr_period': 14,

    # Volume
    'volume_sma_period': 20,

    # Returns
    'return_periods': [1, 5, 10, 20],

    # Target
    'target_period': 5,  # Predict 5 bars ahead
    'target_threshold': 0.005,  # 0.5% move = signal
}

# Training parameters
TRAINING_CONFIG = {
    'train_test_split': 0.8,
    'validation_split': 0.1,
    'lookback_days': 500,  # How much history to use
    'retrain_frequency': 7,  # Retrain every N days
    'min_samples': 1000,  # Minimum samples to train
}

# Signal generation
SIGNAL_CONFIG = {
    'confidence_threshold': 0.6,  # Minimum confidence to trade
    'signal_smoothing': 3,  # Smooth signals over N bars
    'min_holding_period': 5,  # Minimum bars to hold
}
