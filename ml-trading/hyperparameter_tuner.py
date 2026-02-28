"""
Hyperparameter Tuner for ML Trading Models
Uses Optuna for automated hyperparameter optimization

Usage:
    python hyperparameter_tuner.py SOXL    # Tune specific symbol
    python hyperparameter_tuner.py --all   # Tune all symbols
"""
import os
import sys
import json
import logging
import numpy as np
import pandas as pd
from datetime import datetime
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import accuracy_score

# Add paths
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# Directories
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BEST_PARAMS_DIR = os.path.join(BASE_DIR, 'best_params')
os.makedirs(BEST_PARAMS_DIR, exist_ok=True)

# Default symbols
DEFAULT_SYMBOLS = ['SOXL', 'NVDA', 'SPY', 'QQQ', 'AAPL', 'GOOGL', 'MSFT', 'JPM', 'GS', 'META', 'SMCI', 'TSM', 'SNOW']

# Sector groupings for shared parameters
SECTOR_GROUPS = {
    'finance': ['JPM', 'GS'],
    'tech': ['NVDA', 'AAPL', 'GOOGL', 'MSFT', 'META', 'SMCI', 'TSM', 'SNOW'],
    'etf': ['SPY', 'QQQ', 'SOXL']
}


def get_sector(symbol):
    """Get sector for a symbol"""
    for sector, symbols in SECTOR_GROUPS.items():
        if symbol in symbols:
            return sector
    return 'default'


def load_data(symbol, days=500):
    """Load historical data for a symbol"""
    from ib_data_provider import IBDataProvider
    import yfinance as yf

    # Try IB Gateway first
    try:
        provider = IBDataProvider()
        df = provider.get_historical_bars(symbol, duration=f'{days} days', bar_size='1 day')
        if df is not None and len(df) > 100:
            logger.info(f"Loaded {len(df)} bars from IB Gateway for {symbol}")
            return df
    except Exception as e:
        logger.warning(f"IB Gateway unavailable for {symbol}: {e}")

    # Fallback to yfinance
    logger.info(f"Loading data via yfinance for {symbol}...")
    ticker = yf.Ticker(symbol)
    df = ticker.history(period=f'{days}d')

    if df.empty:
        raise ValueError(f"No data available for {symbol}")

    # Standardize column names (capitalize first letter)
    df = df.reset_index()
    df.columns = [col.capitalize() for col in df.columns]
    if 'Date' in df.columns:
        df['Date'] = pd.to_datetime(df['Date'])

    logger.info(f"Loaded {len(df)} bars via yfinance for {symbol}")
    return df


def prepare_features(df, symbol):
    """Prepare features for training"""
    from feature_engineering import FeatureEngineer

    engineer = FeatureEngineer()
    features_df = engineer.add_all_features(df)

    # Get feature columns
    feature_cols = engineer.get_feature_columns()

    # Drop NaN rows
    features_df = features_df.dropna()

    X = features_df[feature_cols].values
    y = features_df['target'].values

    return X, y, feature_cols


def objective(trial, X, y, symbol):
    """Optuna objective function for hyperparameter optimization"""

    # Random Forest parameters
    rf_params = {
        'n_estimators': trial.suggest_int('rf_n_estimators', 100, 500),
        'max_depth': trial.suggest_int('rf_max_depth', 4, 20),
        'min_samples_split': trial.suggest_int('rf_min_samples_split', 2, 20),
        'min_samples_leaf': trial.suggest_int('rf_min_samples_leaf', 1, 10),
    }

    # XGBoost parameters
    xgb_params = {
        'n_estimators': trial.suggest_int('xgb_n_estimators', 100, 500),
        'max_depth': trial.suggest_int('xgb_max_depth', 3, 12),
        'learning_rate': trial.suggest_float('xgb_learning_rate', 0.01, 0.3, log=True),
        'subsample': trial.suggest_float('xgb_subsample', 0.6, 1.0),
        'colsample_bytree': trial.suggest_float('xgb_colsample_bytree', 0.6, 1.0),
    }

    # LightGBM parameters
    lgb_params = {
        'n_estimators': trial.suggest_int('lgb_n_estimators', 100, 500),
        'max_depth': trial.suggest_int('lgb_max_depth', 3, 15),
        'learning_rate': trial.suggest_float('lgb_learning_rate', 0.01, 0.3, log=True),
        'num_leaves': trial.suggest_int('lgb_num_leaves', 15, 63),
    }

    # Ensemble weights
    rf_weight = trial.suggest_float('weight_rf', 0.2, 0.5)
    xgb_weight = trial.suggest_float('weight_xgb', 0.2, 0.5)
    lgb_weight = 1.0 - rf_weight - xgb_weight

    if lgb_weight < 0.1:
        raise optuna.TrialPruned()

    # Time series cross-validation
    tscv = TimeSeriesSplit(n_splits=3)
    scores = []

    for train_idx, test_idx in tscv.split(X):
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]

        try:
            # Train RF
            from sklearn.ensemble import RandomForestClassifier
            rf = RandomForestClassifier(**rf_params, n_jobs=-1, random_state=42)
            rf.fit(X_train, y_train)

            # Train XGBoost
            import xgboost as xgb
            xgb_model = xgb.XGBClassifier(
                **xgb_params,
                n_jobs=-1,
                random_state=42,
                use_label_encoder=False,
                eval_metric='mlogloss'
            )
            xgb_model.fit(X_train, y_train)

            # Train LightGBM
            import lightgbm as lgb
            lgb_model = lgb.LGBMClassifier(
                **lgb_params,
                n_jobs=-1,
                random_state=42,
                verbose=-1
            )
            lgb_model.fit(X_train, y_train)

            # Get predictions with weighted ensemble
            rf_proba = rf.predict_proba(X_test)
            xgb_proba = xgb_model.predict_proba(X_test)
            lgb_proba = lgb_model.predict_proba(X_test)

            ensemble_proba = (rf_weight * rf_proba +
                            xgb_weight * xgb_proba +
                            lgb_weight * lgb_proba)

            y_pred = np.argmax(ensemble_proba, axis=1)
            acc = accuracy_score(y_test, y_pred)
            scores.append(acc)

        except Exception as e:
            logger.warning(f"Trial failed: {e}")
            raise optuna.TrialPruned()

    return np.mean(scores)


def tune_symbol(symbol, n_trials=50, timeout=600):
    """
    Tune hyperparameters for a single symbol

    Args:
        symbol: Stock symbol
        n_trials: Number of optimization trials
        timeout: Maximum time in seconds

    Returns:
        dict: Best parameters found
    """
    import optuna

    logger.info(f"Starting hyperparameter tuning for {symbol}")

    # Load and prepare data
    df = load_data(symbol, days=500)
    X, y, feature_cols = prepare_features(df, symbol)

    logger.info(f"Data shape: X={X.shape}, y={y.shape}")

    # Create study
    study = optuna.create_study(
        direction='maximize',
        study_name=f'{symbol}_tuning',
        sampler=optuna.samplers.TPESampler(seed=42)
    )

    # Run optimization
    study.optimize(
        lambda trial: objective(trial, X, y, symbol),
        n_trials=n_trials,
        timeout=timeout,
        show_progress_bar=True
    )

    # Get best parameters
    best_params = study.best_params
    best_score = study.best_value

    logger.info(f"Best accuracy for {symbol}: {best_score:.4f}")
    logger.info(f"Best params: {best_params}")

    # Save best parameters
    params_file = os.path.join(BEST_PARAMS_DIR, f'{symbol}_params.json')
    result = {
        'symbol': symbol,
        'best_accuracy': best_score,
        'best_params': best_params,
        'n_trials': len(study.trials),
        'timestamp': datetime.now().isoformat()
    }

    with open(params_file, 'w') as f:
        json.dump(result, f, indent=2)

    logger.info(f"Saved best params to {params_file}")

    return result


def tune_all_symbols(symbols=None, n_trials=30, timeout=300):
    """Tune hyperparameters for all symbols"""
    symbols = symbols or DEFAULT_SYMBOLS

    results = {}
    for symbol in symbols:
        try:
            result = tune_symbol(symbol, n_trials=n_trials, timeout=timeout)
            results[symbol] = result
        except Exception as e:
            logger.error(f"Failed to tune {symbol}: {e}")
            results[symbol] = {'error': str(e)}

    # Summary
    print("\n" + "="*60)
    print("TUNING SUMMARY")
    print("="*60)
    for symbol, result in results.items():
        if 'error' in result:
            print(f"{symbol}: FAILED - {result['error']}")
        else:
            print(f"{symbol}: {result['best_accuracy']:.4f}")

    return results


def get_best_params(symbol):
    """Load best parameters for a symbol"""
    params_file = os.path.join(BEST_PARAMS_DIR, f'{symbol}_params.json')
    if os.path.exists(params_file):
        with open(params_file, 'r') as f:
            return json.load(f)
    return None


if __name__ == '__main__':
    import argparse
    import optuna

    parser = argparse.ArgumentParser(description='Hyperparameter Tuner for ML Trading')
    parser.add_argument('symbol', nargs='?', help='Symbol to tune (or --all for all)')
    parser.add_argument('--all', action='store_true', help='Tune all symbols')
    parser.add_argument('--trials', type=int, default=50, help='Number of trials per symbol')
    parser.add_argument('--timeout', type=int, default=600, help='Timeout per symbol (seconds)')

    args = parser.parse_args()

    if args.all:
        tune_all_symbols(n_trials=args.trials, timeout=args.timeout)
    elif args.symbol:
        tune_symbol(args.symbol.upper(), n_trials=args.trials, timeout=args.timeout)
    else:
        print("Usage:")
        print("  python hyperparameter_tuner.py SOXL       # Tune specific symbol")
        print("  python hyperparameter_tuner.py --all      # Tune all symbols")
        print("  python hyperparameter_tuner.py SOXL --trials 100  # More trials")
