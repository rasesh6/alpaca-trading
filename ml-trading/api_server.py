"""
ML Trading API Server
REST API for training, signals, and backtesting
"""
import os
import logging
from datetime import datetime
from flask import Flask, jsonify, request
from flask_cors import CORS

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Import ML trading components
from trainer import Trainer
from signal_generator import SignalGenerator
from backtester import Backtester

# Configuration
IB_HOST = os.getenv('IB_GATEWAY_HOST', 'ib-gateway.railway.internal')
IB_PORT = int(os.getenv('IB_GATEWAY_PORT', '4001'))

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'ml-trading',
        'ib_host': IB_HOST,
        'ib_port': IB_PORT,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/train/<symbol>', methods=['POST'])
def train_model(symbol):
    """
    Train model for a symbol

    Query params:
    - days: Number of days of history (default: 365)
    """
    symbol = symbol.upper()
    days = int(request.args.get('days', 365))

    logger.info(f"Training request: {symbol}, days={days}")

    try:
        trainer = Trainer(symbol)

        # Set IB Gateway host for Railway private networking
        if hasattr(trainer, 'ib_host'):
            trainer.ib_host = IB_HOST
            trainer.ib_port = IB_PORT

        trainer.fetch_data(days)
        trainer.prepare_features()
        model = trainer.train()
        trainer.save_model()

        # Get feature importance
        feature_cols = trainer.feature_engineer.get_feature_columns()
        importance = model.get_feature_importance(feature_cols)

        return jsonify({
            'success': True,
            'symbol': symbol,
            'days': days,
            'train_samples': len(trainer.X_train),
            'test_samples': len(trainer.X_test),
            'model_saved': f"{symbol}_ensemble",
            'top_features': dict(list(importance.items())[:10]),
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Training failed: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/signal/<symbol>', methods=['GET'])
def get_signal(symbol):
    """
    Get current trading signal for a symbol

    Query params:
    - model: Model name (default: {symbol}_ensemble)
    """
    symbol = symbol.upper()
    model_name = request.args.get('model', f"{symbol}_ensemble")

    logger.info(f"Signal request: {symbol}, model={model_name}")

    try:
        generator = SignalGenerator(symbol, model_name)

        # Set IB Gateway host for Railway private networking
        if hasattr(generator, 'ib_host'):
            generator.ib_host = IB_HOST
            generator.ib_port = IB_PORT

        signal = generator.get_latest_signal()

        return jsonify({
            'success': True,
            'symbol': symbol,
            'signal': signal.get('signal', 'HOLD'),
            'confidence': signal.get('confidence', 0),
            'prediction': signal.get('prediction', 1),
            'probabilities': signal.get('probabilities', {}),
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Signal generation failed: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/quote/<symbol>', methods=['GET'])
def get_quote(symbol):
    """
    Get real-time NBBO quote from IB Gateway
    """
    symbol = symbol.upper()

    logger.info(f"Quote request: {symbol}")

    try:
        from ib_data_provider import IBDataProvider

        provider = IBDataProvider(host=IB_HOST, port=IB_PORT)
        quote = provider.get_realtime_quote(symbol)

        if quote:
            return jsonify({
                'success': True,
                'symbol': symbol,
                'quote': quote,
                'timestamp': datetime.now().isoformat()
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Could not fetch quote',
                'timestamp': datetime.now().isoformat()
            }), 404

    except Exception as e:
        logger.error(f"Quote fetch failed: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/backtest/<symbol>', methods=['POST'])
def run_backtest(symbol):
    """
    Run backtest for a symbol

    Query params:
    - days: Number of days of history (default: 365)
    - capital: Initial capital (default: 10000)
    - confidence: Confidence threshold (default: 0.6)
    """
    symbol = symbol.upper()
    days = int(request.args.get('days', 365))
    capital = float(request.args.get('capital', 10000))
    confidence = float(request.args.get('confidence', 0.6))

    logger.info(f"Backtest request: {symbol}, days={days}, capital={capital}")

    try:
        backtester = Backtester(symbol, initial_capital=capital)
        backtester.load_data(days)
        results = backtester.run_backtest(confidence_threshold=confidence)

        return jsonify({
            'success': True,
            'symbol': symbol,
            'initial_capital': results.get('initial_capital'),
            'final_value': results.get('final_value'),
            'total_return': results.get('total_return'),
            'buy_hold_return': results.get('buy_hold_return'),
            'sharpe_ratio': results.get('sharpe_ratio'),
            'total_trades': results.get('total_trades'),
            'win_rate': results.get('win_rate'),
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Backtest failed: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/full/<symbol>', methods=['POST'])
def full_pipeline(symbol):
    """
    Run full pipeline: train, signal, backtest

    Query params:
    - days: Number of days of history (default: 365)
    """
    symbol = symbol.upper()
    days = int(request.args.get('days', 365))

    logger.info(f"Full pipeline request: {symbol}, days={days}")

    results = {
        'symbol': symbol,
        'days': days,
        'timestamp': datetime.now().isoformat()
    }

    # Train
    try:
        trainer = Trainer(symbol)
        trainer.fetch_data(days)
        trainer.prepare_features()
        model = trainer.train()
        trainer.save_model()

        feature_cols = trainer.feature_engineer.get_feature_columns()
        importance = model.get_feature_importance(feature_cols)

        results['training'] = {
            'success': True,
            'train_samples': len(trainer.X_train),
            'test_samples': len(trainer.X_test),
            'top_features': dict(list(importance.items())[:5])
        }
    except Exception as e:
        results['training'] = {'success': False, 'error': str(e)}

    # Signal
    try:
        generator = SignalGenerator(symbol)
        signal = generator.get_latest_signal()

        results['signal'] = {
            'success': True,
            'signal': signal.get('signal', 'HOLD'),
            'confidence': signal.get('confidence', 0),
            'probabilities': signal.get('probabilities', {})
        }
    except Exception as e:
        results['signal'] = {'success': False, 'error': str(e)}

    # Backtest
    try:
        backtester = Backtester(symbol)
        backtester.load_data(days)
        bt_results = backtester.run_backtest()

        results['backtest'] = {
            'success': True,
            'total_return': bt_results.get('total_return'),
            'win_rate': bt_results.get('win_rate'),
            'total_trades': bt_results.get('total_trades')
        }
    except Exception as e:
        results['backtest'] = {'success': False, 'error': str(e)}

    return jsonify(results)


if __name__ == '__main__':
    port = int(os.getenv('PORT', 3000))
    logger.info(f"Starting ML Trading API on port {port}")
    logger.info(f"IB Gateway: {IB_HOST}:{IB_PORT}")

    # Use production server
    from waitress import serve
    serve(app, host='0.0.0.0', port=port, threads=4)
