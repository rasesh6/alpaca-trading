"""
Alpaca Trading System - Flask Server

A modern web-based trading interface using Alpaca's API.
Features: Paper/Live trading, positions, orders, exit strategies, WebSocket streaming
"""
import os
import json
import logging
import queue
import threading
from datetime import datetime
from flask import Flask, render_template, request, jsonify, Response
from config import SECRET_KEY, USE_PAPER, set_trading_mode
from alpaca_client import get_client, reinitialize_client
import streaming
import market_data_streaming


def restart_all_connections():
    """Restart client and streaming with new credentials after mode switch"""
    reinitialize_client()
    streaming.restart_streaming()
    market_data_streaming.restart_market_streaming()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.secret_key = SECRET_KEY

# Store pending exit strategies (in memory - lost on restart)
# Format: {order_id: {symbol, quantity, side, strategy_type, params...}}
_pending_exit_strategies = {}

# File for persisting exit strategies across restarts
EXIT_STRATEGIES_FILE = '/tmp/alpaca_exit_strategies.json'

def _load_exit_strategies():
    """Load exit strategies from disk"""
    global _pending_exit_strategies
    try:
        if os.path.exists(EXIT_STRATEGIES_FILE):
            with open(EXIT_STRATEGIES_FILE, 'r') as f:
                _pending_exit_strategies = json.load(f)
                logger.info(f"Loaded {len(_pending_exit_strategies)} exit strategies from disk")
    except Exception as e:
        logger.warning(f"Failed to load exit strategies: {e}")
        _pending_exit_strategies = {}

def _save_exit_strategies():
    """Save exit strategies to disk"""
    try:
        with open(EXIT_STRATEGIES_FILE, 'w') as f:
            json.dump(_pending_exit_strategies, f, indent=2)
    except Exception as e:
        logger.warning(f"Failed to save exit strategies: {e}")

# Load exit strategies on module import (survives Flask debug reload)
_load_exit_strategies()

# SSE message queues for each connected client
_sse_clients = {}
_sse_client_id = 0
_sse_lock = threading.Lock()


# ==================== SSE HELPERS ====================

def broadcast_trade_update(update):
    """Broadcast trade update to all connected SSE clients"""
    message = json.dumps(update)
    with _sse_lock:
        for client_queue in _sse_clients.values():
            try:
                client_queue.put_nowait(message)
            except:
                pass  # Queue full, skip


def broadcast_quote_update(quote):
    """Broadcast quote update to all connected SSE clients"""
    message = json.dumps({
        'type': 'quote',
        'symbol': quote.get('symbol'),
        'bid': quote.get('bid'),
        'ask': quote.get('ask'),
        'bid_size': quote.get('bid_size'),
        'ask_size': quote.get('ask_size'),
        'last': quote.get('last'),
        'timestamp': quote.get('timestamp')
    })
    with _sse_lock:
        for client_queue in _sse_clients.values():
            try:
                client_queue.put_nowait(message)
            except:
                pass  # Queue full, skip

def _handle_websocket_trade_update(update):
    """Handle trade updates from WebSocket and process exit strategies"""
    event = update.get('event')
    order_id = update.get('order_id')
    symbol = update.get('symbol')
    status = update.get('status')

    logger.info(f"WebSocket trade update: {event} for {symbol} order {order_id}")

    # Check if this order has a pending exit strategy
    exit_strategy = _pending_exit_strategies.get(order_id)

    if event in ['fill', 'partial_fill', 'canceled', 'expired']:
        logger.debug(f"Looking for exit strategy for order {order_id}: {'FOUND' if exit_strategy else 'NOT FOUND'}")
        if not exit_strategy and event == 'fill':
            logger.warning(f"No exit strategy found for filled order {order_id}. "
                          f"Pending strategies: {list(_pending_exit_strategies.keys())}")

    if event == 'fill' or event == 'partial_fill':
        if exit_strategy and exit_strategy.get('status') == 'waiting_fill':
            fill_price = update.get('filled_avg_price')
            if fill_price:
                exit_strategy['fill_price'] = fill_price
                original_side = exit_strategy.get('side', 'BUY')

                # Handle profit target - place close order immediately
                if exit_strategy['strategy_type'] == 'profit-target':
                    profit_offset_type = exit_strategy.get('profit_offset_type', 'dollar')
                    profit_offset = exit_strategy.get('profit_offset', 0.5)

                    # For BUY: profit when price goes UP (fill + offset)
                    # For SELL (short): profit when price goes DOWN (fill - offset)
                    if profit_offset_type == 'percent':
                        if original_side == 'BUY':
                            profit_price = fill_price * (1 + profit_offset / 100)
                        else:
                            profit_price = fill_price * (1 - profit_offset / 100)
                    else:
                        if original_side == 'BUY':
                            profit_price = fill_price + profit_offset
                        else:
                            profit_price = fill_price - profit_offset

                    # Close order is opposite of entry
                    close_side = 'sell' if original_side == 'BUY' else 'buy'

                    client = get_client()
                    profit_result = client.place_limit_order(
                        symbol=exit_strategy['symbol'],
                        side=close_side,
                        qty=exit_strategy['quantity'],
                        limit_price=round(profit_price, 2)
                    )

                    if profit_result.get('success'):
                        logger.info(f"Placed profit target {close_side} for {symbol} @ ${profit_price}")
                        broadcast_trade_update({
                            'type': 'profit_placed',
                            'order_id': order_id,
                            'symbol': symbol,
                            'fill_price': fill_price,
                            'profit_price': round(profit_price, 2),
                            'profit_order_id': profit_result['order']['id'],
                            'profit_side': close_side
                        })
                    else:
                        logger.error(f"Failed to place profit target: {profit_result.get('error')}")
                        broadcast_trade_update({
                            'type': 'profit_failed',
                            'order_id': order_id,
                            'symbol': symbol,
                            'error': profit_result.get('error')
                        })

                    # Clean up
                    del _pending_exit_strategies[order_id]
                    _save_exit_strategies()

                elif exit_strategy['strategy_type'] == 'bracket':
                    # Bracket order - place TP and SL orders
                    # Note: Alpaca doesn't support OCO with stop-limit, so we place both
                    # and they compete. When one fills, we need to cancel the other.
                    tp_offset = exit_strategy.get('tp_offset', 0.5)
                    tp_type = exit_strategy.get('tp_type', 'dollar')
                    sl_offset = exit_strategy.get('sl_offset', 0.25)
                    sl_type = exit_strategy.get('sl_type', 'dollar')
                    close_side = 'sell' if original_side == 'BUY' else 'buy'

                    # Calculate TP price
                    if tp_type == 'percent':
                        if original_side == 'BUY':
                            tp_price = fill_price * (1 + tp_offset / 100)
                        else:
                            tp_price = fill_price * (1 - tp_offset / 100)
                    else:
                        if original_side == 'BUY':
                            tp_price = fill_price + tp_offset
                        else:
                            tp_price = fill_price - tp_offset

                    # Calculate SL price
                    if sl_type == 'percent':
                        if original_side == 'BUY':
                            sl_price = fill_price * (1 - sl_offset / 100)
                        else:
                            sl_price = fill_price * (1 + sl_offset / 100)
                    else:
                        if original_side == 'BUY':
                            sl_price = fill_price - sl_offset
                        else:
                            sl_price = fill_price + sl_offset

                    tp_price = round(tp_price, 2)
                    sl_price = round(sl_price, 2)

                    # SL limit price: slightly worse than stop to ensure fill
                    sl_limit_price = round(sl_price - 0.01, 2) if original_side == 'BUY' else round(sl_price + 0.01, 2)

                    logger.info(f"Bracket: fill={fill_price}, TP={tp_price}, SL={sl_price}")

                    client = get_client()

                    # Place SL stop-limit order FIRST (risk management)
                    sl_result = client.place_stop_limit_order(
                        symbol=exit_strategy['symbol'],
                        side=close_side,
                        qty=exit_strategy['quantity'],
                        stop_price=sl_price,
                        limit_price=sl_limit_price
                    )

                    # Place TP limit order
                    tp_result = client.place_limit_order(
                        symbol=exit_strategy['symbol'],
                        side=close_side,
                        qty=exit_strategy['quantity'],
                        limit_price=tp_price
                    )

                    if tp_result.get('success') and sl_result.get('success'):
                        logger.info(f"Placed bracket TP/SL for {symbol}: TP={tp_price}, SL={sl_price}")
                        broadcast_trade_update({
                            'type': 'bracket_placed',
                            'order_id': order_id,
                            'symbol': symbol,
                            'fill_price': fill_price,
                            'tp_price': tp_price,
                            'sl_price': sl_price,
                            'tp_order_id': tp_result['order']['id'],
                            'sl_order_id': sl_result['order']['id']
                        })
                    else:
                        errors = []
                        if not tp_result.get('success'):
                            errors.append(f"TP: {tp_result.get('error')}")
                        if not sl_result.get('success'):
                            errors.append(f"SL: {sl_result.get('error')}")
                        logger.error(f"Failed to place bracket orders: {'; '.join(errors)}")
                        broadcast_trade_update({
                            'type': 'bracket_failed',
                            'order_id': order_id,
                            'symbol': symbol,
                            'error': '; '.join(errors)
                        })

                    # Clean up
                    del _pending_exit_strategies[order_id]
                    _save_exit_strategies()

                else:
                    # Confirmation stop or trailing stop - calculate trigger price
                    trigger_type = exit_strategy.get('trigger_type', 'dollar')
                    trigger_offset = exit_strategy.get('trigger_offset', 0)

                    # For BUY: trigger when price goes UP (fill + offset)
                    # For SELL (short): trigger when price goes DOWN (fill - offset)
                    if trigger_type == 'percent':
                        if original_side == 'BUY':
                            trigger_price = fill_price * (1 + trigger_offset / 100)
                        else:
                            trigger_price = fill_price * (1 - trigger_offset / 100)
                    else:
                        if original_side == 'BUY':
                            trigger_price = fill_price + trigger_offset
                        else:
                            trigger_price = fill_price - trigger_offset

                    exit_strategy['trigger_price'] = trigger_price
                    exit_strategy['status'] = 'waiting_trigger'
                    _save_exit_strategies()  # Persist the status change

                    logger.info(f"Order {order_id} filled at ${fill_price}, trigger at ${trigger_price}")

                    # Notify frontend
                    broadcast_trade_update({
                        'type': 'fill',
                        'order_id': order_id,
                        'symbol': symbol,
                        'fill_price': fill_price,
                        'trigger_price': trigger_price,
                        'status': 'waiting_trigger'
                    })

    elif event == 'canceled' or event == 'expired':
        if order_id in _pending_exit_strategies:
            del _pending_exit_strategies[order_id]
            _save_exit_strategies()
            logger.info(f"Removed exit strategy for cancelled/expired order {order_id}")

    # Always broadcast to connected clients
    broadcast_trade_update({
        'type': 'trade_update',
        'event': event,
        'order_id': order_id,
        'symbol': symbol,
        'status': status,
        'filled_qty': update.get('filled_qty'),
        'filled_avg_price': update.get('filled_avg_price')
    })


# Register WebSocket callback
streaming.register_trade_callback(_handle_websocket_trade_update)

# Register market data quote callback
market_data_streaming.register_quote_callback(broadcast_quote_update)


# ==================== ROUTES ====================

@app.route('/')
def index():
    """Main trading UI"""
    return render_template('index.html',
                           paper_mode=USE_PAPER,
                           environment='PAPER' if USE_PAPER else 'LIVE')


@app.route('/api/stream')
def api_stream():
    """SSE endpoint for real-time trade updates"""
    def event_stream():
        global _sse_client_id
        with _sse_lock:
            _sse_client_id += 1
            client_id = _sse_client_id
            client_queue = queue.Queue(maxsize=100)
            _sse_clients[client_id] = client_queue

        logger.info(f"SSE client {client_id} connected")

        try:
            # Send initial connection message
            yield f"data: {json.dumps({'type': 'connected'})}\n\n"

            while True:
                try:
                    # Wait for messages with timeout
                    message = client_queue.get(timeout=30)
                    yield f"data: {message}\n\n"
                except queue.Empty:
                    # Send keepalive
                    yield f": keepalive\n\n"
        except GeneratorExit:
            pass
        finally:
            with _sse_lock:
                if client_id in _sse_clients:
                    del _sse_clients[client_id]
            logger.info(f"SSE client {client_id} disconnected")

    return Response(event_stream(), mimetype='text/event-stream')


# ==================== ACCOUNT API ====================

@app.route('/api/mode', methods=['GET'])
def api_get_mode():
    """Get current trading mode (paper/live)"""
    from config import get_trading_mode
    return jsonify({
        'paper': get_trading_mode(),
        'environment': 'PAPER' if get_trading_mode() else 'LIVE'
    })


@app.route('/api/mode', methods=['POST'])
def api_set_mode():
    """Switch trading mode (paper/live)"""
    from config import set_trading_mode, get_trading_mode
    data = request.get_json()
    paper = data.get('paper', True)

    old_mode = 'PAPER' if get_trading_mode() else 'LIVE'
    set_trading_mode(paper)
    restart_all_connections()  # Restart client and WebSocket with new credentials
    new_mode = 'PAPER' if get_trading_mode() else 'LIVE'

    logger.info(f"Switched trading mode from {old_mode} to {new_mode}")

    return jsonify({
        'success': True,
        'paper': paper,
        'environment': new_mode
    })


@app.route('/api/account')
def api_account():
    """Get account details"""
    client = get_client()
    return jsonify(client.get_account())


# ==================== POSITIONS API ====================

@app.route('/api/positions')
def api_positions():
    """Get all positions"""
    client = get_client()
    return jsonify(client.get_positions())


# ==================== QUOTES API ====================

@app.route('/api/quote/<symbol>')
def api_quote(symbol):
    """Get quote for a symbol"""
    client = get_client()
    return jsonify(client.get_quote(symbol.upper()))


@app.route('/api/quotes/subscribe', methods=['POST'])
def api_subscribe_quotes():
    """Subscribe to real-time quotes for symbols"""
    data = request.get_json()
    symbols = data.get('symbols', [])

    if not symbols:
        return jsonify({'success': False, 'error': 'No symbols provided'})

    if not isinstance(symbols, list):
        symbols = [symbols]

    symbols = [s.upper() for s in symbols]

    # Check subscription limit (30 for Basic plan)
    current_subs = market_data_streaming.get_subscribed_symbols()
    new_count = len(set(current_subs) | set(symbols))

    if new_count > 30:
        return jsonify({
            'success': False,
            'error': f'Subscription limit exceeded. Basic plan allows max 30 symbols. Current: {len(current_subs)}, Requested additional: {len(symbols)}',
            'current_count': len(current_subs),
            'limit': 30
        })

    # Start streaming if not already
    market_data_streaming.start_market_streaming()
    market_data_streaming.subscribe_quotes(symbols)

    return jsonify({
        'success': True,
        'subscribed': symbols,
        'all_subscribed': market_data_streaming.get_subscribed_symbols(),
        'count': len(market_data_streaming.get_subscribed_symbols())
    })


@app.route('/api/quotes/unsubscribe', methods=['POST'])
def api_unsubscribe_quotes():
    """Unsubscribe from real-time quotes for symbols"""
    data = request.get_json()
    symbols = data.get('symbols', [])

    if not symbols:
        return jsonify({'success': False, 'error': 'No symbols provided'})

    if not isinstance(symbols, list):
        symbols = [symbols]

    symbols = [s.upper() for s in symbols]

    market_data_streaming.unsubscribe_quotes(symbols)

    return jsonify({
        'success': True,
        'unsubscribed': symbols,
        'all_subscribed': market_data_streaming.get_subscribed_symbols()
    })


@app.route('/api/quotes/subscriptions')
def api_quote_subscriptions():
    """Get list of currently subscribed symbols"""
    return jsonify({
        'symbols': market_data_streaming.get_subscribed_symbols(),
        'count': len(market_data_streaming.get_subscribed_symbols()),
        'limit': 30,
        'stream_connected': market_data_streaming.get_market_stream().connected
    })


# ==================== ORDERS API ====================

@app.route('/api/orders')
def api_orders():
    """Get orders"""
    client = get_client()
    status = request.args.get('status', 'open')

    # For 'open' status, also include 'held' orders (stop-limit waiting for trigger)
    if status == 'open':
        result = client.get_orders('open')
        held_result = client.get_orders('held')
        if result.get('success') and held_result.get('success'):
            result['orders'].extend(held_result['orders'])
        return jsonify(result)

    return jsonify(client.get_orders(status))


@app.route('/api/orders/<order_id>')
def api_order(order_id):
    """Get specific order"""
    client = get_client()
    return jsonify(client.get_order(order_id))


@app.route('/api/orders/<order_id>/fill-status')
def api_order_fill_status(order_id):
    """Check if order is filled and return fill price"""
    client = get_client()
    result = client.get_order(order_id)

    if not result.get('success'):
        return jsonify(result)

    order = result['order']

    if order['status'] == 'filled':
        # Check if we have exit strategy for this order
        exit_strategy = _pending_exit_strategies.get(order_id)

        response = {
            'filled': True,
            'fill_price': order.get('filled_avg_price'),
            'filled_qty': order.get('filled_qty')
        }

        if exit_strategy:
            fill_price = order.get('filled_avg_price', 0)
            exit_strategy['fill_price'] = fill_price
            _save_exit_strategies()  # Persist fill price

            # Handle different strategy types
            if exit_strategy['strategy_type'] == 'profit-target':
                # Calculate profit price and place close order immediately
                profit_offset_type = exit_strategy.get('profit_offset_type', 'dollar')
                profit_offset = exit_strategy.get('profit_offset', 0.5)
                original_side = exit_strategy.get('side', 'BUY')

                logger.info(f"Profit target: fill_price={fill_price}, offset_type={profit_offset_type}, offset={profit_offset}, original_side={original_side}")

                # For BUY orders: profit when price goes UP (fill_price + offset)
                # For SELL orders (short): profit when price goes DOWN (fill_price - offset)
                if profit_offset_type == 'percent':
                    if original_side == 'BUY':
                        profit_price = fill_price * (1 + profit_offset / 100)
                    else:
                        profit_price = fill_price * (1 - profit_offset / 100)
                else:
                    if original_side == 'BUY':
                        profit_price = fill_price + profit_offset
                    else:
                        profit_price = fill_price - profit_offset

                logger.info(f"Calculated profit_price={profit_price}")

                # Close order is opposite of entry
                close_side = 'sell' if original_side == 'BUY' else 'buy'

                # Place limit order to close position
                profit_result = client.place_limit_order(
                    symbol=exit_strategy['symbol'],
                    side=close_side,
                    qty=exit_strategy['quantity'],
                    limit_price=round(profit_price, 2)
                )

                if profit_result.get('success'):
                    response['profit_order_placed'] = True
                    response['profit_price'] = round(profit_price, 2)
                    response['profit_order_id'] = profit_result['order']['id']
                    response['profit_side'] = close_side
                    exit_strategy['profit_price'] = profit_price
                    exit_strategy['status'] = 'profit_placed'
                    logger.info(f"Placed profit target {close_side} for {exit_strategy['symbol']} @ ${profit_price}")
                    # Clean up
                    del _pending_exit_strategies[order_id]
                    _save_exit_strategies()
                else:
                    response['profit_order_placed'] = False
                    response['error'] = profit_result.get('error')
                    logger.error(f"Failed to place profit target: {profit_result.get('error')}")

            elif exit_strategy['strategy_type'] == 'bracket':
                # Bracket order - place TP and SL orders
                original_side = exit_strategy.get('side', 'BUY')
                close_side = 'sell' if original_side == 'BUY' else 'buy'

                tp_offset = exit_strategy.get('tp_offset', 0.5)
                tp_type = exit_strategy.get('tp_type', 'dollar')
                sl_offset = exit_strategy.get('sl_offset', 0.25)
                sl_type = exit_strategy.get('sl_type', 'dollar')

                # Calculate TP price
                # For BUY: TP above fill, for SELL: TP below fill
                if tp_type == 'percent':
                    if original_side == 'BUY':
                        tp_price = fill_price * (1 + tp_offset / 100)
                    else:
                        tp_price = fill_price * (1 - tp_offset / 100)
                else:
                    if original_side == 'BUY':
                        tp_price = fill_price + tp_offset
                    else:
                        tp_price = fill_price - tp_offset

                # Calculate SL price
                # For BUY: SL below fill, for SELL: SL above fill
                if sl_type == 'percent':
                    if original_side == 'BUY':
                        sl_price = fill_price * (1 - sl_offset / 100)
                    else:
                        sl_price = fill_price * (1 + sl_offset / 100)
                else:
                    if original_side == 'BUY':
                        sl_price = fill_price - sl_offset
                    else:
                        sl_price = fill_price + sl_offset

                tp_price = round(tp_price, 2)
                sl_price = round(sl_price, 2)
                sl_limit_price = round(sl_price - 0.01, 2) if original_side == 'BUY' else round(sl_price + 0.01, 2)

                logger.info(f"Bracket: fill={fill_price}, TP={tp_price}, SL={sl_price}")

                # Place SL stop-limit order FIRST (risk management)
                sl_result = client.place_stop_limit_order(
                    symbol=exit_strategy['symbol'],
                    side=close_side,
                    qty=exit_strategy['quantity'],
                    stop_price=sl_price,
                    limit_price=sl_limit_price
                )

                # Place TP limit order
                tp_result = client.place_limit_order(
                    symbol=exit_strategy['symbol'],
                    side=close_side,
                    qty=exit_strategy['quantity'],
                    limit_price=tp_price
                )

                response['bracket_orders_placed'] = False

                if tp_result.get('success') and sl_result.get('success'):
                    response['bracket_orders_placed'] = True
                    response['tp_price'] = tp_price
                    response['sl_price'] = sl_price
                    response['tp_order_id'] = tp_result['order']['id']
                    response['sl_order_id'] = sl_result['order']['id']
                    exit_strategy['tp_price'] = tp_price
                    exit_strategy['sl_price'] = sl_price
                    exit_strategy['status'] = 'bracket_placed'
                    logger.info(f"Placed bracket TP/SL for {exit_strategy['symbol']}: TP={tp_price}, SL={sl_price}")
                    # Clean up
                    del _pending_exit_strategies[order_id]
                    _save_exit_strategies()
                else:
                    errors = []
                    if not tp_result.get('success'):
                        errors.append(f"TP: {tp_result.get('error')}")
                    if not sl_result.get('success'):
                        errors.append(f"SL: {sl_result.get('error')}")
                    response['error'] = '; '.join(errors)
                    logger.error(f"Failed to place bracket orders: {response['error']}")

            else:
                # Confirmation stop or trailing stop - calculate trigger price
                trigger_type = exit_strategy.get('trigger_type', 'dollar')
                trigger_offset = exit_strategy.get('trigger_offset', 0)

                if trigger_type == 'percent':
                    trigger_price = fill_price * (1 + trigger_offset / 100)
                else:
                    trigger_price = fill_price + trigger_offset

                response['trigger_price'] = round(trigger_price, 2)
                exit_strategy['trigger_price'] = trigger_price
                exit_strategy['status'] = 'waiting_trigger'
                _save_exit_strategies()  # Persist the status change

        return jsonify(response)

    return jsonify({'filled': False, 'status': order['status']})


@app.route('/api/orders/place', methods=['POST'])
def api_place_order():
    """Place an order with optional exit strategy"""
    client = get_client()
    data = request.get_json()

    symbol = data.get('symbol', '').upper()
    side = data.get('side', '').upper()
    quantity = int(data.get('quantity', 1))
    order_type = data.get('order_type', 'MARKET')
    limit_price = data.get('limit_price')
    limit_price_type = data.get('limit_price_type')  # 'manual', 'bid', or 'ask'
    exit_strategy = data.get('exit_strategy', 'none')

    if not symbol or not side:
        return jsonify({'success': False, 'error': 'Symbol and side required'})

    # Handle limit price type (bid/ask/manual)
    if order_type == 'LIMIT' and limit_price_type in ['bid', 'ask']:
        quote_result = client.get_quote(symbol)
        if not quote_result.get('success'):
            return jsonify({'success': False, 'error': f"Failed to get quote: {quote_result.get('error')}"})

        if limit_price_type == 'bid':
            limit_price = quote_result['quote']['bid']
        else:
            limit_price = quote_result['quote']['ask']

        logger.info(f"Using {limit_price_type} price: ${limit_price} for {symbol}")

    # Handle BRACKET orders - use Alpaca's native bracket order
    if exit_strategy == 'bracket':
        tp_offset = float(data.get('bracket_tp_offset', 0.5))
        tp_type = data.get('bracket_tp_type', 'dollar')
        sl_offset = float(data.get('bracket_sl_offset', 0.25))
        sl_type = data.get('bracket_sl_type', 'dollar')

        # For market orders, estimate fill price from current quote
        if order_type == 'MARKET':
            quote_result = client.get_quote(symbol)
            if not quote_result.get('success'):
                return jsonify({'success': False, 'error': f"Failed to get quote: {quote_result.get('error')}"})

            # Use bid for SELL, ask for BUY
            if side == 'BUY':
                estimated_fill = quote_result['quote']['ask']
            else:
                estimated_fill = quote_result['quote']['bid']

            logger.info(f"Estimated fill price for {symbol} {side}: ${estimated_fill}")
        else:
            if not limit_price:
                return jsonify({'success': False, 'error': 'Limit price required'})
            estimated_fill = limit_price

        # Calculate TP and SL prices from estimated fill
        if tp_type == 'percent':
            if side == 'BUY':
                tp_price = estimated_fill * (1 + tp_offset / 100)
            else:
                tp_price = estimated_fill * (1 - tp_offset / 100)
        else:
            if side == 'BUY':
                tp_price = estimated_fill + tp_offset
            else:
                tp_price = estimated_fill - tp_offset

        if sl_type == 'percent':
            if side == 'BUY':
                sl_price = estimated_fill * (1 - sl_offset / 100)
            else:
                sl_price = estimated_fill * (1 + sl_offset / 100)
        else:
            if side == 'BUY':
                sl_price = estimated_fill - sl_offset
            else:
                sl_price = estimated_fill + sl_offset

        tp_price = round(tp_price, 2)
        sl_price = round(sl_price, 2)

        # Place native bracket order
        result = client.place_bracket_order(
            symbol=symbol,
            side=side,
            qty=quantity,
            entry_price=limit_price if order_type == 'LIMIT' else None,
            take_profit_price=tp_price,
            stop_loss_price=sl_price
        )

        if result.get('success'):
            logger.info(f"Placed native bracket order for {symbol}: TP={tp_price}, SL={sl_price}")
            return jsonify({
                'success': True,
                'order': result['order'],
                'bracket': {
                    'tp_price': tp_price,
                    'sl_price': sl_price,
                    'estimated_fill': estimated_fill
                }
            })
        else:
            return jsonify(result)

    # Place the main order (for non-bracket strategies)
    if order_type == 'LIMIT':
        if not limit_price:
            return jsonify({'success': False, 'error': 'Limit price required'})
        result = client.place_limit_order(symbol, side, quantity, limit_price)
    else:
        result = client.place_market_order(symbol, side, quantity)

    if not result.get('success'):
        return jsonify(result)

    order_id = result['order']['id']

    # Handle exit strategies
    monitoring_config = None

    if exit_strategy == 'profit-target':
        _pending_exit_strategies[order_id] = {
            'symbol': symbol,
            'quantity': quantity,
            'side': side,
            'strategy_type': 'profit-target',
            'profit_offset_type': data.get('profit_offset_type', 'dollar'),
            'profit_offset': float(data.get('profit_offset', 0.5)),
            'fill_timeout': int(data.get('fill_timeout', 15)),
            'fill_price': None,
            'profit_price': None,
            'status': 'waiting_fill',
            'created_at': datetime.utcnow().isoformat()
        }
        _save_exit_strategies()
        monitoring_config = {
            'strategy': 'profit-target',
            'fill_timeout': int(data.get('fill_timeout', 15))
        }
        logger.info(f"Created profit target for order {order_id}")

    elif exit_strategy == 'confirmation-stop':
        _pending_exit_strategies[order_id] = {
            'symbol': symbol,
            'quantity': quantity,
            'side': side,
            'strategy_type': 'confirmation-stop',
            'trigger_type': data.get('cs_trigger_type', 'dollar'),
            'trigger_offset': float(data.get('cs_trigger_offset', 0.5)),
            'stop_type': data.get('cs_stop_type', 'dollar'),
            'stop_offset': float(data.get('cs_stop_offset', 0.25)),
            'fill_timeout': int(data.get('fill_timeout', 15)),
            'trigger_timeout': int(data.get('trigger_timeout', 300)),
            'fill_price': None,
            'trigger_price': None,
            'status': 'waiting_fill',
            'created_at': datetime.utcnow().isoformat()
        }
        _save_exit_strategies()
        monitoring_config = {
            'strategy': 'confirmation-stop',
            'fill_timeout': int(data.get('fill_timeout', 15)),
            'trigger_timeout': int(data.get('trigger_timeout', 300))
        }
        logger.info(f"Created confirmation stop for order {order_id}")

    elif exit_strategy == 'trailing-stop':
        _pending_exit_strategies[order_id] = {
            'symbol': symbol,
            'quantity': quantity,
            'side': side,
            'strategy_type': 'trailing-stop',
            'trigger_type': data.get('tsl_trigger_type', 'dollar'),
            'trigger_offset': float(data.get('tsl_trigger_offset', 0.5)),
            'trail_type': data.get('tsl_trail_type', 'dollar'),
            'trail_amount': float(data.get('tsl_trail_amount', 0.25)),
            'fill_timeout': int(data.get('fill_timeout', 15)),
            'trigger_timeout': int(data.get('trigger_timeout', 300)),
            'fill_price': None,
            'trigger_price': None,
            'status': 'waiting_fill',
            'created_at': datetime.utcnow().isoformat()
        }
        _save_exit_strategies()
        monitoring_config = {
            'strategy': 'trailing-stop',
            'fill_timeout': int(data.get('fill_timeout', 15)),
            'trigger_timeout': int(data.get('trigger_timeout', 300))
        }
        logger.info(f"Created trailing stop for order {order_id}")

    return jsonify({
        'success': True,
        'order': result['order'],
        'monitoring': monitoring_config
    })


@app.route('/api/orders/<order_id>/cancel', methods=['POST'])
def api_cancel_order(order_id):
    """Cancel an order"""
    client = get_client()
    result = client.cancel_order(order_id)

    # Clean up any pending exit strategy
    if order_id in _pending_exit_strategies:
        del _pending_exit_strategies[order_id]
        _save_exit_strategies()

    return jsonify(result)


# ==================== EXIT STRATEGY API ====================

@app.route('/api/exit-strategy/<order_id>/check-trigger')
def api_check_trigger(order_id):
    """Check if trigger price has been reached for an exit strategy"""
    client = get_client()

    exit_strategy = _pending_exit_strategies.get(order_id)
    if not exit_strategy:
        logger.warning(f"check-trigger: No exit strategy found for {order_id}")
        return jsonify({'error': 'No exit strategy found', 'triggered': False})

    # If still waiting for fill, check if order is now filled
    if exit_strategy['status'] == 'waiting_fill':
        order_result = client.get_order(order_id)
        if order_result.get('success') and order_result['order']['status'] == 'filled':
            fill_price = order_result['order'].get('filled_avg_price', 0)
            exit_strategy['fill_price'] = fill_price

            # Calculate trigger price
            trigger_type = exit_strategy.get('trigger_type', 'dollar')
            trigger_offset = exit_strategy.get('trigger_offset', 0)

            if trigger_type == 'percent':
                trigger_price = fill_price * (1 + trigger_offset / 100)
            else:
                trigger_price = fill_price + trigger_offset

            exit_strategy['trigger_price'] = trigger_price
            exit_strategy['status'] = 'waiting_trigger'
            _save_exit_strategies()
            logger.info(f"check-trigger: Updated order {order_id} to waiting_trigger, trigger_price=${trigger_price}")

    if exit_strategy['status'] != 'waiting_trigger':
        logger.warning(f"check-trigger: Order {order_id} status is {exit_strategy['status']}, not waiting_trigger")
        return jsonify({'error': f'Not waiting for trigger (status: {exit_strategy["status"]})', 'triggered': False})

    symbol = exit_strategy['symbol']
    trigger_price = exit_strategy.get('trigger_price', 0)

    # Get current price
    quote_result = client.get_quote(symbol)
    if not quote_result.get('success'):
        return jsonify({'error': quote_result.get('error'), 'triggered': False})

    current_price = quote_result['quote']['last']

    response = {
        'triggered': False,
        'current_price': current_price,
        'trigger_price': trigger_price
    }

    # Check if trigger hit (for BUY orders, price goes UP)
    # For SELL orders (shorts), price would need to go DOWN
    if exit_strategy['side'] == 'BUY':
        if current_price >= trigger_price:
            response['triggered'] = True
    else:
        if current_price <= trigger_price:
            response['triggered'] = True

    # If triggered, place the stop order
    if response['triggered']:
        original_side = exit_strategy.get('side', 'BUY')
        close_side = 'sell' if original_side == 'BUY' else 'buy'

        if exit_strategy['strategy_type'] == 'confirmation-stop':
            # Calculate stop price
            stop_type = exit_strategy.get('stop_type', 'dollar')
            stop_offset = exit_strategy.get('stop_offset', 0.25)

            # For BUY: stop is BELOW current price (protect against drop)
            # For SELL (short): stop is ABOVE current price (protect against rise)
            if stop_type == 'percent':
                if original_side == 'BUY':
                    stop_price = current_price * (1 - stop_offset / 100)
                else:
                    stop_price = current_price * (1 + stop_offset / 100)
            else:
                if original_side == 'BUY':
                    stop_price = current_price - stop_offset
                else:
                    stop_price = current_price + stop_offset

            # Limit price: slightly worse than stop to ensure fill
            if original_side == 'BUY':
                limit_price = stop_price - 0.01  # Sell limit below stop
            else:
                limit_price = stop_price + 0.01  # Buy limit above stop

            # Place stop limit order to close position
            stop_result = client.place_stop_limit_order(
                symbol=symbol,
                side=close_side,
                qty=exit_strategy['quantity'],
                stop_price=stop_price,
                limit_price=limit_price
            )

            if stop_result.get('success'):
                response['stop_price'] = stop_price
                response['stop_order_id'] = stop_result['order']['id']
                exit_strategy['status'] = 'stop_placed'
                logger.info(f"Placed stop limit {close_side} for {symbol}: stop={stop_price}, limit={limit_price}")

                # Broadcast update to SSE clients
                broadcast_trade_update({
                    'type': 'trigger_hit',
                    'order_id': order_id,
                    'symbol': symbol,
                    'stop_price': stop_price,
                    'stop_order_id': stop_result['order']['id']
                })
            else:
                response['error'] = stop_result.get('error')

        elif exit_strategy['strategy_type'] == 'trailing-stop':
            # Place trailing stop order
            trail_type = exit_strategy.get('trail_type', 'dollar')
            trail_amount = exit_strategy.get('trail_amount', 0.25)

            stop_result = client.place_trailing_stop_order(
                symbol=symbol,
                side=close_side,
                qty=exit_strategy['quantity'],
                trail_type=trail_type,
                trail_amount=trail_amount
            )

            if stop_result.get('success'):
                response['trail_amount'] = trail_amount
                response['stop_order_id'] = stop_result['order']['id']
                exit_strategy['status'] = 'stop_placed'
                logger.info(f"Placed trailing stop for {symbol}: trail={trail_amount} ({trail_type})")

                # Broadcast update to SSE clients
                broadcast_trade_update({
                    'type': 'trigger_hit',
                    'order_id': order_id,
                    'symbol': symbol,
                    'trail_amount': trail_amount,
                    'stop_order_id': stop_result['order']['id']
                })
            else:
                response['error'] = stop_result.get('error')

        # Clean up the pending strategy
        if response.get('stop_order_id'):
            del _pending_exit_strategies[order_id]
            _save_exit_strategies()

    return jsonify(response)


# ==================== RUN ====================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    debug = os.environ.get('FLASK_DEBUG', 'true').lower() == 'true'
    logger.info(f"Starting Alpaca Trading System on port {port} (paper={USE_PAPER})")

    # Start WebSocket streaming
    logger.info("Starting WebSocket streaming...")
    streaming.start_streaming()

    # Start market data streaming
    logger.info("Starting market data streaming (IEX feed)...")
    market_data_streaming.start_market_streaming()

    app.run(host='0.0.0.0', port=port, debug=debug)
