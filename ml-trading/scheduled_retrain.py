#!/usr/bin/env python3
"""
Scheduled Model Retraining
Runs via Railway cron to retrain models every 7 days

Usage:
    python scheduled_retrain.py

Set in Railway as a cron job:
    0 6 * * 0  # Every Sunday at 6 AM UTC
"""
import os
import sys
import logging
from datetime import datetime

# Add paths
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'ml-trading'))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Run scheduled retraining"""
    logger.info("=" * 60)
    logger.info("SCHEDULED MODEL RETRAINING")
    logger.info(f"Started: {datetime.now().isoformat()}")
    logger.info("=" * 60)

    try:
        from model_manager import ModelRetrainer, ModelMetrics, DEFAULT_SYMBOLS

        retrainer = ModelRetrainer()
        metrics = ModelMetrics()

        # Check which models need retraining (7 day threshold)
        symbols = DEFAULT_SYMBOLS
        to_retrain = []

        for symbol in symbols:
            if metrics.needs_retraining(symbol, days_threshold=7):
                to_retrain.append(symbol)
                logger.info(f"{symbol}: Needs retraining")
            else:
                info = metrics.get_model_info(symbol)
                if info:
                    logger.info(f"{symbol}: Up to date (trained {info.get('last_trained', 'unknown')})")
                else:
                    to_retrain.append(symbol)
                    logger.info(f"{symbol}: No model found, needs training")

        if not to_retrain:
            logger.info("All models are up to date. No retraining needed.")
            return

        logger.info(f"Models to retrain: {to_retrain}")

        # Retrain
        result = retrainer.retrain_all(to_retrain)

        # Log results
        logger.info("-" * 60)
        logger.info("RETRAINING RESULTS")
        logger.info("-" * 60)

        for symbol, res in result.get('results', {}).items():
            if res.get('success'):
                logger.info(f"✅ {symbol}: accuracy={res.get('accuracy', 'N/A'):.4f}")
            else:
                logger.error(f"❌ {symbol}: {res.get('error', 'Unknown error')}")

        logger.info("-" * 60)
        logger.info(f"Summary: {result.get('summary', {})}")
        logger.info(f"Completed: {datetime.now().isoformat()}")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Scheduled retraining failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
