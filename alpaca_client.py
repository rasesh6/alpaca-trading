"""
Alpaca API Client

Simple wrapper around alpaca-trade-api for trading operations.
Alpaca has a modern REST API with 99.9% uptime and ~1.5ms latency.
"""
import logging
import alpaca_trade_api as alpaca
from config import API_KEY, SECRET_KEY, BASE_URL, USE_PAPER

logger = logging.getLogger(__name__)


class AlpacaClient:
    """Wrapper for Alpaca trading and market data APIs"""

    def __init__(self):
        self.api = alpaca.REST(
            key_id=API_KEY,
            secret_key=SECRET_KEY,
            base_url=BASE_URL
        )
        self.paper = USE_PAPER
        logger.info(f"AlpacaClient initialized (paper={USE_PAPER}, base_url={BASE_URL})")

    # ==================== ACCOUNT ====================

    def get_account(self):
        """Get account details including buying power, cash, portfolio value"""
        try:
            account = self.api.get_account()
            return {
                'success': True,
                'account': {
                    'id': account.id,
                    'cash': float(account.cash),
                    'buying_power': float(account.buying_power),
                    'portfolio_value': float(account.portfolio_value),
                    'equity': float(account.equity),
                    'status': account.status,
                    'trading_blocked': account.trading_blocked,
                    'transfers_blocked': account.transfers_blocked,
                }
            }
        except Exception as e:
            logger.error(f"Failed to get account: {e}")
            return {'success': False, 'error': str(e)}

    # ==================== POSITIONS ====================

    def get_positions(self):
        """Get all open positions"""
        try:
            positions = self.api.list_positions()
            result = []
            for pos in positions:
                result.append({
                    'symbol': pos.symbol,
                    'qty': float(pos.qty),
                    'side': pos.side,
                    'market_value': float(pos.market_value),
                    'cost_basis': float(pos.cost_basis),
                    'avg_entry_price': float(pos.avg_entry_price),
                    'current_price': float(pos.current_price),
                    'unrealized_pl': float(pos.unrealized_pl),
                    'unrealized_plpc': float(pos.unrealized_plpc) * 100,  # Convert to percentage
                    'change_today': float(pos.change_today) * 100 if pos.change_today else 0,
                })
            return {'success': True, 'positions': result}
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            return {'success': False, 'error': str(e)}

    # ==================== QUOTES ====================

    def get_quote(self, symbol: str):
        """Get latest quote for a symbol"""
        try:
            quote = self.api.get_latest_quote(symbol)
            return {
                'success': True,
                'quote': {
                    'symbol': symbol,
                    'bid': float(quote.bid_price),
                    'ask': float(quote.ask_price),
                    'bid_size': int(quote.bid_size),
                    'ask_size': int(quote.ask_size),
                    'last': (float(quote.bid_price) + float(quote.ask_price)) / 2,  # Mid price
                    'timestamp': quote.timestamp.isoformat() if hasattr(quote, 'timestamp') else None,
                }
            }
        except Exception as e:
            logger.error(f"Failed to get quote for {symbol}: {e}")
            return {'success': False, 'error': str(e)}

    # ==================== ORDERS ====================

    def get_orders(self, status: str = 'open'):
        """Get orders (open by default)"""
        try:
            if status == 'all':
                orders = self.api.list_orders()
            else:
                orders = self.api.list_orders(status=status)

            result = []
            for order in orders:
                result.append({
                    'id': order.id,
                    'client_order_id': order.client_order_id,
                    'symbol': order.symbol,
                    'side': order.side,
                    'qty': float(order.qty) if order.qty else 0,
                    'filled_qty': float(order.filled_qty) if order.filled_qty else 0,
                    'type': order.type,
                    'limit_price': float(order.limit_price) if order.limit_price else None,
                    'stop_price': float(order.stop_price) if order.stop_price else None,
                    'status': order.status,
                    'created_at': order.created_at.isoformat() if order.created_at else None,
                    'filled_at': order.filled_at.isoformat() if order.filled_at else None,
                    'filled_avg_price': float(order.filled_avg_price) if order.filled_avg_price else None,
                })
            return {'success': True, 'orders': result}
        except Exception as e:
            logger.error(f"Failed to get orders: {e}")
            return {'success': False, 'error': str(e)}

    def place_market_order(self, symbol: str, side: str, qty: int, client_order_id: str = None):
        """Place a market order"""
        try:
            order = self.api.submit_order(
                symbol=symbol,
                qty=qty,
                side=side.lower(),
                type='market',
                time_in_force='day',
                client_order_id=client_order_id,
            )
            logger.info(f"Placed market order: {order.id} - {side} {qty} {symbol}")
            return {
                'success': True,
                'order': {
                    'id': order.id,
                    'client_order_id': order.client_order_id,
                    'symbol': order.symbol,
                    'side': order.side,
                    'qty': float(order.qty),
                    'status': order.status,
                }
            }
        except Exception as e:
            logger.error(f"Failed to place market order: {e}")
            return {'success': False, 'error': str(e)}

    def place_limit_order(self, symbol: str, side: str, qty: int, limit_price: float, client_order_id: str = None):
        """Place a limit order"""
        try:
            order = self.api.submit_order(
                symbol=symbol,
                qty=qty,
                side=side.lower(),
                type='limit',
                time_in_force='day',
                limit_price=str(limit_price),
                client_order_id=client_order_id,
            )
            logger.info(f"Placed limit order: {order.id} - {side} {qty} {symbol} @ ${limit_price}")
            return {
                'success': True,
                'order': {
                    'id': order.id,
                    'client_order_id': order.client_order_id,
                    'symbol': order.symbol,
                    'side': order.side,
                    'qty': float(order.qty),
                    'limit_price': float(order.limit_price),
                    'status': order.status,
                }
            }
        except Exception as e:
            logger.error(f"Failed to place limit order: {e}")
            return {'success': False, 'error': str(e)}

    def cancel_order(self, order_id: str):
        """Cancel an order by ID"""
        try:
            self.api.cancel_order(order_id)
            logger.info(f"Cancelled order: {order_id}")
            return {'success': True, 'message': f'Order {order_id} cancelled'}
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return {'success': False, 'error': str(e)}

    def get_order(self, order_id: str):
        """Get a specific order by ID"""
        try:
            order = self.api.get_order(order_id)
            return {
                'success': True,
                'order': {
                    'id': order.id,
                    'symbol': order.symbol,
                    'side': order.side,
                    'qty': float(order.qty) if order.qty else 0,
                    'filled_qty': float(order.filled_qty) if order.filled_qty else 0,
                    'type': order.type,
                    'limit_price': float(order.limit_price) if order.limit_price else None,
                    'status': order.status,
                    'filled_at': order.filled_at.isoformat() if order.filled_at else None,
                    'filled_avg_price': float(order.filled_avg_price) if order.filled_avg_price else None,
                }
            }
        except Exception as e:
            logger.error(f"Failed to get order {order_id}: {e}")
            return {'success': False, 'error': str(e)}

    def place_stop_limit_order(self, symbol: str, side: str, qty: int,
                                 stop_price: float, limit_price: float):
        """Place a stop limit order"""
        try:
            order = self.api.submit_order(
                symbol=symbol,
                qty=qty,
                side=side.lower(),
                type='stop_limit',
                time_in_force='day',
                stop_price=str(stop_price),
                limit_price=str(limit_price),
            )
            logger.info(f"Placed stop limit order: {order.id} - {side} {qty} {symbol} @ stop={stop_price}, limit={limit_price}")
            return {
                'success': True,
                'order': {
                    'id': order.id,
                    'symbol': order.symbol,
                    'side': order.side,
                    'qty': float(order.qty),
                    'stop_price': float(order.stop_price),
                    'limit_price': float(order.limit_price),
                    'status': order.status,
                }
            }
        except Exception as e:
            logger.error(f"Failed to place stop limit order: {e}")
            return {'success': False, 'error': str(e)}

    def place_trailing_stop_order(self, symbol: str, side: str, qty: int,
                                   trail_type: str = 'dollar', trail_amount: float = 0.25):
        """
        Place a trailing stop order.
        trail_type: 'dollar' or 'percent'
        trail_amount: the trail distance
        """
        try:
            order_kwargs = {
                'symbol': symbol,
                'qty': qty,
                'side': side.lower(),
                'type': 'trailing_stop',
                'time_in_force': 'day',
            }

            if trail_type == 'percent':
                order_kwargs['trail_percent'] = str(trail_amount)
            else:
                order_kwargs['trail_price'] = str(trail_amount)

            order = self.api.submit_order(**order_kwargs)
            logger.info(f"Placed trailing stop order: {order.id} - {side} {qty} {symbol} @ trail={trail_amount} ({trail_type})")
            return {
                'success': True,
                'order': {
                    'id': order.id,
                    'symbol': order.symbol,
                    'side': order.side,
                    'qty': float(order.qty),
                    'trail_type': trail_type,
                    'trail_amount': trail_amount,
                    'status': order.status,
                }
            }
        except Exception as e:
            logger.error(f"Failed to place trailing stop order: {e}")
            return {'success': False, 'error': str(e)}

    # ==================== BRACKET ORDERS ====================

    def place_bracket_order(self, symbol: str, side: str, qty: int,
                            entry_price: float = None,
                            take_profit_price: float = None,
                            stop_loss_price: float = None):
        """
        Place a bracket order with optional take profit and stop loss.
        If entry_price is None, uses market order for entry.
        """
        try:
            order_class = 'bracket'
            order_type = 'limit' if entry_price else 'market'

            order_kwargs = {
                'symbol': symbol,
                'qty': qty,
                'side': side.lower(),
                'type': order_type,
                'time_in_force': 'day',
                'order_class': order_class,
            }

            if entry_price:
                order_kwargs['limit_price'] = str(entry_price)

            if take_profit_price:
                order_kwargs['take_profit'] = {'limit_price': str(take_profit_price)}

            if stop_loss_price:
                # Stop loss needs both stop_price and limit_price
                # Use a slightly worse limit price to ensure fill
                order_kwargs['stop_loss'] = {
                    'stop_price': str(stop_loss_price),
                    'limit_price': str(round(stop_loss_price - 0.01, 2))
                }

            order = self.api.submit_order(**order_kwargs)
            logger.info(f"Placed bracket order: {order.id} - {side} {qty} {symbol}")

            return {
                'success': True,
                'order': {
                    'id': order.id,
                    'symbol': order.symbol,
                    'side': order.side,
                    'qty': float(order.qty),
                    'status': order.status,
                }
            }
        except Exception as e:
            logger.error(f"Failed to place bracket order: {e}")
            return {'success': False, 'error': str(e)}

    def place_oco_order(self, symbol: str, side: str, qty: int,
                        take_profit_price: float,
                        stop_price: float, stop_limit_price: float):
        """
        Place an OCO (One-Cancels-Other) order.
        This places both a limit (TP) and stop-limit (SL) order.
        When one executes, the other is automatically cancelled.

        side: The side to CLOSE the position (opposite of entry)
        """
        try:
            order_kwargs = {
                'symbol': symbol,
                'qty': qty,
                'side': side.lower(),
                'time_in_force': 'day',
                'order_class': 'oco',
                'take_profit': {
                    'limit_price': str(take_profit_price),
                },
                'stop_loss': {
                    'stop_price': str(stop_price),
                    'limit_price': str(stop_limit_price),
                },
            }

            order = self.api.submit_order(**order_kwargs)
            logger.info(f"Placed OCO order: {order.id} - {side} {qty} {symbol} @ TP={take_profit_price}, SL={stop_price}")

            return {
                'success': True,
                'order': {
                    'id': order.id,
                    'symbol': order.symbol,
                    'side': order.side,
                    'qty': float(order.qty),
                    'status': order.status,
                }
            }
        except Exception as e:
            logger.error(f"Failed to place OCO order: {e}")
            return {'success': False, 'error': str(e)}


# Singleton instance
_client = None

def get_client() -> AlpacaClient:
    """Get the singleton AlpacaClient instance"""
    global _client
    if _client is None:
        _client = AlpacaClient()
    return _client


def reinitialize_client() -> AlpacaClient:
    """Reinitialize the client with current config (after mode switch)"""
    global _client
    # Get current values directly from config module (not reload)
    from config import API_KEY, SECRET_KEY, BASE_URL, USE_PAPER, get_trading_mode

    # Create new API instance with current credentials
    _client = AlpacaClient()
    _client.api = alpaca.REST(
        key_id=API_KEY,
        secret_key=SECRET_KEY,
        base_url=BASE_URL
    )
    _client.paper = get_trading_mode()
    logger.info(f"Reinitialized AlpacaClient (paper={_client.paper}, base_url={BASE_URL})")
    return _client
