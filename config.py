"""
Alpaca Trading System Configuration
Uses environment variables for secrets (safe for git)
"""
import os

# Mode file for persisting trading mode across reloads
MODE_FILE = '/tmp/alpaca_trading_mode.txt'

def _load_mode():
    """Load trading mode from file, default to paper"""
    try:
        if os.path.exists(MODE_FILE):
            with open(MODE_FILE, 'r') as f:
                return f.read().strip().lower() == 'paper'
    except:
        pass
    return True  # Default to paper

def _save_mode(paper: bool):
    """Save trading mode to file"""
    try:
        with open(MODE_FILE, 'w') as f:
            f.write('paper' if paper else 'live')
    except:
        pass

# Use paper trading by default (set to False for live)
USE_PAPER = _load_mode()

# Paper Trading Credentials (from environment variables)
PAPER_API_KEY = os.getenv('PAPER_API_KEY', '')
PAPER_SECRET_KEY = os.getenv('PAPER_SECRET_KEY', '')
PAPER_BASE_URL = os.getenv('PAPER_BASE_URL', 'https://paper-api.alpaca.markets')

# Live Trading Credentials (from environment variables)
LIVE_API_KEY = os.getenv('LIVE_API_KEY', '')
LIVE_SECRET_KEY = os.getenv('LIVE_SECRET_KEY', '')
LIVE_BASE_URL = os.getenv('LIVE_BASE_URL', 'https://api.alpaca.markets')

# Flask secret key for sessions
import secrets
SECRET_KEY = os.getenv('FLASK_SECRET_KEY', secrets.token_hex(32))

# Active credentials (based on USE_PAPER)
if USE_PAPER:
    API_KEY = PAPER_API_KEY
    SECRET_KEY = PAPER_SECRET_KEY
    BASE_URL = PAPER_BASE_URL
else:
    API_KEY = LIVE_API_KEY
    SECRET_KEY = LIVE_SECRET_KEY
    BASE_URL = LIVE_BASE_URL


def set_trading_mode(paper: bool):
    """Switch between paper and live trading mode"""
    global USE_PAPER, API_KEY, SECRET_KEY, BASE_URL
    USE_PAPER = paper
    _save_mode(paper)
    if USE_PAPER:
        API_KEY = PAPER_API_KEY
        SECRET_KEY = PAPER_SECRET_KEY
        BASE_URL = PAPER_BASE_URL
    else:
        API_KEY = LIVE_API_KEY
        SECRET_KEY = LIVE_SECRET_KEY
        BASE_URL = LIVE_BASE_URL
    return USE_PAPER


def get_trading_mode():
    """Get current trading mode"""
    return USE_PAPER
