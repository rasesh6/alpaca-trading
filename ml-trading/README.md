# ML Trading System

Ensemble machine learning trading system using Random Forest, XGBoost, and LightGBM.

## Data Sources

The system uses multiple data sources with automatic fallback:

| Priority | Source | Features |
|----------|--------|----------|
| 1 | **IB Gateway** | Real NBBO quotes, unlimited historical data |
| 2 | Alpaca | Good data, but limited on basic plan (IEX only) |
| 3 | yfinance | Free fallback, delayed quotes |

### IB Gateway Integration

Connect to your IB Gateway hosted on Railway for premium data:

```bash
# Set environment variables
export IB_GATEWAY_HOST=ib-gateway-production.up.railway.app
export IB_GATEWAY_PORT=4001
```

Or use the IB data provider directly:

```python
from ib_data_provider import IBDataProviderFallback

provider = IBDataProviderFallback()
df = provider.get_historical_bars('SOXL', days=365)
quote = provider.get_realtime_quote('SOXL')

print(f"Bid: {quote['bid']}, Ask: {quote['ask']}")
```

## Quick Start

### 1. Install Dependencies
```bash
cd ~/Projects/Alpaca/ml-trading
pip install -r requirements.txt
```

### 2. Train a Model
```bash
python run.py train SOXL 500    # Train on 500 days of SOXL data
python run.py train NVDA 365    # Train on 1 year of NVDA data
```

### 3. Get Trading Signal
```bash
python run.py signal SOXL
```

Output:
```
ML SIGNAL: SOXL
==================================================
Signal:     BUY
Confidence: 72.5%
Probabilities:
  UP:   72.5%
  DOWN: 15.3%
  FLAT: 12.2%
==================================================
```

### 4. Backtest Strategy
```bash
python run.py backtest SOXL 500
```

### 5. Full Pipeline (Train + Signal + Backtest)
```bash
python run.py full SOXL 500
```

## Commands Reference

| Command | Description |
|---------|-------------|
| `python run.py train SYMBOL [DAYS]` | Train new model |
| `python run.py signal SYMBOL` | Get current signal |
| `python run.py backtest SYMBOL [DAYS]` | Backtest strategy |
| `python run.py full SYMBOL [DAYS]` | Complete pipeline |

## How It Works

### 1. Feature Engineering
Generates 30+ technical indicators:
- Moving Averages (SMA, EMA)
- Momentum (RSI, MACD, Stochastic)
- Volatility (Bollinger Bands, ATR)
- Volume indicators
- Price returns

### 2. Ensemble Model
Combines three models with weighted voting:
| Model | Weight | Strength |
|-------|--------|----------|
| Random Forest | 40% | Robust, less overfitting |
| XGBoost | 35% | Fast, good pattern detection |
| LightGBM | 25% | Efficient with large data |

### 3. Target Prediction
Predicts price direction over next 5 bars:
- **UP (+1)**: Price will rise > 0.5%
- **DOWN (-1)**: Price will fall > 0.5%
- **FLAT (0)**: Price change < 0.5%

### 4. Signal Generation
- Confidence threshold: 60% (configurable)
- Only generates BUY/SELL when confidence > threshold
- Otherwise returns HOLD

## File Structure

```
ml-trading/
├── config.py              # Configuration settings
├── feature_engineering.py # Technical indicators
├── ensemble_model.py      # RF + XGB + LGB ensemble
├── trainer.py             # Training pipeline
├── signal_generator.py    # Generate trading signals
├── backtester.py          # Strategy backtesting
├── ib_data_provider.py    # IB Gateway data connector
├── run.py                 # Main entry point
├── requirements.txt       # Dependencies
├── README.md              # This file
├── data/                  # Cached price data
└── models/                # Saved models
```

## Configuration

Edit `config.py` to customize:

### Model Parameters
```python
ENSEMBLE_CONFIG = {
    'rf_n_estimators': 200,
    'rf_max_depth': 10,
    'xgb_n_estimators': 200,
    'xgb_max_depth': 6,
    ...
}
```

### Feature Parameters
```python
FEATURE_CONFIG = {
    'sma_periods': [5, 10, 20, 50],
    'rsi_period': 14,
    'target_period': 5,        # Predict 5 bars ahead
    'target_threshold': 0.005, # 0.5% move = signal
    ...
}
```

### Signal Parameters
```python
SIGNAL_CONFIG = {
    'confidence_threshold': 0.6,  # Min confidence to trade
}
```

## Integration with Alpaca

This system integrates with your existing Alpaca setup:

```python
# Use signals in your trading scripts
from ml_trading.signal_generator import SignalGenerator

gen = SignalGenerator('SOXL')
signal = gen.get_latest_signal()

if signal['signal'] == 'BUY' and signal['confidence'] > 0.7:
    # Execute trade via Alpaca
    place_order('SOXL', 'buy', 100)
```

## Performance Expectations

Based on research, realistic expectations:

| Metric | Expected Range |
|--------|---------------|
| Win Rate | 55-60% |
| Annual Return | 15-25% |
| Sharpe Ratio | 0.8-1.5 |
| Max Drawdown | 15-25% |

**Important:** Always paper trade first before using live capital!

## Best Practices

1. **Retrain Weekly**: Markets change, models should adapt
2. **Use Walk-Forward**: Test on out-of-sample data
3. **Combine with Other Signals**: Don't rely solely on ML
4. **Manage Risk**: Use stop-losses and position sizing
5. **Start Small**: Test with small positions first

## Troubleshooting

### "No data returned"
- Check market is open or use historical data
- Verify symbol is valid

### "Model not fitted"
- Run `python run.py train SYMBOL` first

### Low accuracy
- Try more training data (500+ days)
- Adjust feature configuration
- Consider different symbols

## Future Enhancements

- [x] IB Gateway integration for premium data
- [ ] Intraday signals (5-minute bars)
- [ ] Sentiment analysis integration
- [ ] Multi-symbol portfolio optimization
- [ ] Real-time signal streaming
- [ ] Auto-retraining scheduler
