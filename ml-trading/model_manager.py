"""
Model Manager for ML Trading
Handles retraining, versioning, and performance monitoring
"""
import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, 'models')
DATA_DIR = os.path.join(BASE_DIR, 'data')
METRICS_FILE = os.path.join(BASE_DIR, 'model_metrics.json')

# Default symbols to train
DEFAULT_SYMBOLS = ['SOXL', 'NVDA', 'SPY', 'QQQ']


class ModelMetrics:
    """Track and store model performance metrics"""

    def __init__(self):
        self.metrics_file = METRICS_FILE
        self._ensure_metrics_file()

    def _ensure_metrics_file(self):
        """Ensure metrics file exists"""
        if not os.path.exists(self.metrics_file):
            self._save_metrics({})

    def _load_metrics(self) -> Dict:
        """Load metrics from file"""
        try:
            with open(self.metrics_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading metrics: {e}")
            return {}

    def _save_metrics(self, metrics: Dict):
        """Save metrics to file"""
        try:
            with open(self.metrics_file, 'w') as f:
                json.dump(metrics, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Error saving metrics: {e}")

    def record_training(self, symbol: str, metrics: Dict):
        """Record training results for a model"""
        all_metrics = self._load_metrics()

        if symbol not in all_metrics:
            all_metrics[symbol] = {
                'history': [],
                'current': None
            }

        # Add to history
        all_metrics[symbol]['history'].append({
            'timestamp': datetime.now().isoformat(),
            'accuracy': metrics.get('accuracy'),
            'train_samples': metrics.get('train_samples'),
            'test_samples': metrics.get('test_samples'),
            'features_count': metrics.get('features_count'),
            'data_days': metrics.get('data_days', 500)
        })

        # Keep only last 30 training records
        all_metrics[symbol]['history'] = all_metrics[symbol]['history'][-30:]

        # Update current
        all_metrics[symbol]['current'] = {
            'version': len(all_metrics[symbol]['history']),
            'last_trained': datetime.now().isoformat(),
            'accuracy': metrics.get('accuracy'),
            'train_samples': metrics.get('train_samples'),
            'test_samples': metrics.get('test_samples')
        }

        self._save_metrics(all_metrics)
        logger.info(f"Recorded training metrics for {symbol}")

    def record_prediction(self, symbol: str, predicted: str, actual: str = None, confidence: float = None):
        """Record a prediction for later accuracy tracking"""
        all_metrics = self._load_metrics()

        if symbol not in all_metrics:
            all_metrics[symbol] = {'history': [], 'current': None, 'predictions': []}

        if 'predictions' not in all_metrics[symbol]:
            all_metrics[symbol]['predictions'] = []

        all_metrics[symbol]['predictions'].append({
            'timestamp': datetime.now().isoformat(),
            'predicted': predicted,
            'actual': actual,  # Will be filled in later when we know the outcome
            'confidence': confidence
        })

        # Keep only last 100 predictions
        all_metrics[symbol]['predictions'] = all_metrics[symbol]['predictions'][-100:]

        self._save_metrics(all_metrics)

    def update_prediction_outcome(self, symbol: str, timestamp: str, actual: str):
        """Update a prediction with the actual outcome"""
        all_metrics = self._load_metrics()

        if symbol not in all_metrics or 'predictions' not in all_metrics[symbol]:
            return

        for pred in all_metrics[symbol]['predictions']:
            if pred['timestamp'] == timestamp:
                pred['actual'] = actual
                break

        self._save_metrics(all_metrics)

    def get_prediction_accuracy(self, symbol: str, days: int = 30) -> Optional[Dict]:
        """Calculate prediction accuracy over the last N days"""
        all_metrics = self._load_metrics()

        if symbol not in all_metrics or 'predictions' not in all_metrics[symbol]:
            return None

        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        predictions = [
            p for p in all_metrics[symbol]['predictions']
            if p['timestamp'] >= cutoff and p['actual'] is not None
        ]

        if not predictions:
            return None

        correct = sum(1 for p in predictions if p['predicted'] == p['actual'])
        total = len(predictions)

        return {
            'correct': correct,
            'total': total,
            'accuracy': correct / total if total > 0 else 0,
            'period_days': days
        }

    def get_model_info(self, symbol: str) -> Optional[Dict]:
        """Get current model info"""
        all_metrics = self._load_metrics()

        if symbol not in all_metrics:
            return None

        return all_metrics[symbol].get('current')

    def get_all_model_info(self) -> Dict:
        """Get info for all models"""
        all_metrics = self._load_metrics()
        result = {}

        for symbol in DEFAULT_SYMBOLS:
            if symbol in all_metrics:
                result[symbol] = all_metrics[symbol].get('current')
            else:
                result[symbol] = None

        return result

    def needs_retraining(self, symbol: str, days_threshold: int = 7) -> bool:
        """Check if a model needs retraining"""
        info = self.get_model_info(symbol)

        if not info:
            return True  # No model exists

        last_trained = datetime.fromisoformat(info['last_trained'])
        days_since = (datetime.now() - last_trained).days

        return days_since >= days_threshold


class ModelRetrainer:
    """Handle model retraining with new data"""

    def __init__(self):
        self.metrics = ModelMetrics()

    def retrain_model(self, symbol: str, days: int = 500) -> Dict:
        """
        Retrain a single model

        Returns:
            Dict with training results
        """
        from trainer import Trainer

        logger.info(f"Starting retraining for {symbol}...")

        try:
            trainer = Trainer(symbol)
            trainer.fetch_data(days)
            feature_cols = trainer.prepare_features()
            trainer.train()
            trainer.save_model()

            # Calculate metrics
            from sklearn.metrics import accuracy_score
            y_pred = trainer.model.predict(trainer.X_test)
            accuracy = accuracy_score(trainer.y_test, y_pred)

            metrics = {
                'accuracy': float(accuracy),
                'train_samples': len(trainer.X_train),
                'test_samples': len(trainer.X_test),
                'features_count': len(feature_cols),
                'data_days': days
            }

            # Record metrics
            self.metrics.record_training(symbol, metrics)

            logger.info(f"Retraining complete for {symbol}: accuracy={accuracy:.4f}")

            return {
                'symbol': symbol,
                'success': True,
                'accuracy': accuracy,
                'train_samples': len(trainer.X_train),
                'test_samples': len(trainer.X_test),
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Retraining failed for {symbol}: {e}")
            return {
                'symbol': symbol,
                'success': False,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }

    def retrain_all(self, symbols: List[str] = None, days: int = 500) -> Dict:
        """
        Retrain all models

        Returns:
            Dict with results for each symbol
        """
        symbols = symbols or DEFAULT_SYMBOLS

        results = {
            'started': datetime.now().isoformat(),
            'symbols': symbols,
            'results': {}
        }

        for symbol in symbols:
            logger.info(f"Retraining {symbol}...")
            result = self.retrain_model(symbol, days)
            results['results'][symbol] = result

        results['completed'] = datetime.now().isoformat()

        # Summary
        successful = sum(1 for r in results['results'].values() if r.get('success'))
        results['summary'] = {
            'total': len(symbols),
            'successful': successful,
            'failed': len(symbols) - successful
        }

        return results

    def retrain_if_needed(self, symbols: List[str] = None, days_threshold: int = 7) -> Dict:
        """
        Retrain models only if they need it (based on age)

        Returns:
            Dict with retraining results
        """
        symbols = symbols or DEFAULT_SYMBOLS

        to_retrain = []
        for symbol in symbols:
            if self.metrics.needs_retraining(symbol, days_threshold):
                to_retrain.append(symbol)

        if not to_retrain:
            return {
                'status': 'skipped',
                'message': 'All models are up to date',
                'checked': datetime.now().isoformat()
            }

        logger.info(f"Models needing retraining: {to_retrain}")
        return self.retrain_all(to_retrain)


def get_retraining_status() -> Dict:
    """Get current retraining status for all models"""
    metrics = ModelMetrics()

    status = {
        'timestamp': datetime.now().isoformat(),
        'models': {}
    }

    for symbol in DEFAULT_SYMBOLS:
        info = metrics.get_model_info(symbol)
        needs_retrain = metrics.needs_retraining(symbol)

        status['models'][symbol] = {
            'trained': info is not None,
            'last_trained': info.get('last_trained') if info else None,
            'accuracy': info.get('accuracy') if info else None,
            'needs_retraining': needs_retrain,
            'prediction_accuracy': metrics.get_prediction_accuracy(symbol)
        }

    return status


if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == 'status':
        # Show status
        status = get_retraining_status()
        print(json.dumps(status, indent=2, default=str))

    elif len(sys.argv) > 1 and sys.argv[1] == 'retrain':
        # Retrain specific symbol or all
        retrainer = ModelRetrainer()

        if len(sys.argv) > 2:
            symbol = sys.argv[2].upper()
            result = retrainer.retrain_model(symbol)
        else:
            result = retrainer.retrain_all()

        print(json.dumps(result, indent=2, default=str))

    else:
        print("Usage:")
        print("  python model_manager.py status           - Show model status")
        print("  python model_manager.py retrain          - Retrain all models")
        print("  python model_manager.py retrain SOXL     - Retrain specific model")
