/**
 * Alpaca Trading Terminal - Frontend Application
 */

// State
let accountData = null;
let currentQuote = null;
let fillCheckInterval = null;
let eventSource = null;
let pendingOrders = {};  // Track orders with exit strategies
let lastPlacedOrder = null;  // Track last placed order for status updates
let orderStatusInterval = null;  // Interval for order status polling
let isStreamingQuotes = false;  // Track if streaming mode is active
let streamingSymbol = null;  // Currently streaming symbol

// ==================== UTILITIES ====================

function formatCurrency(value) {
    if (value === null || value === undefined) return '-';
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD'
    }).format(value);
}

function formatPercent(value) {
    if (value === null || value === undefined) return '-';
    const sign = value >= 0 ? '+' : '';
    return `${sign}${value.toFixed(2)}%`;
}

// ==================== TRADING MODE TOGGLE ====================

function handleModeToggle() {
    const toggle = document.getElementById('trading-mode-toggle');
    const isLive = toggle.checked;

    if (isLive) {
        // Show confirmation for live mode
        const confirmed = confirm(
            '⚠️ SWITCHING TO LIVE TRADING\n\n' +
            'You are about to switch to LIVE trading mode.\n' +
            'Real money will be at risk!\n\n' +
            'Are you sure you want to continue?'
        );
        if (!confirmed) {
            toggle.checked = false;  // Revert
            return;
        }
    }

    fetch('/api/mode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ paper: !isLive })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            updateModeUI(data.paper);
            // Refresh account data for new mode
            loadAccount();
            loadPositions();
            loadOrders();
        } else {
            alert('Failed to switch mode: ' + (data.error || 'Unknown error'));
            toggle.checked = !isLive;  // Revert on error
        }
    })
    .catch(error => {
        console.error('Error switching mode:', error);
        alert('Error switching mode');
        toggle.checked = !isLive;  // Revert on error
    });
}

function updateModeUI(isPaper) {
    const toggle = document.getElementById('trading-mode-toggle');
    const paperLabel = document.getElementById('paper-label');
    const liveLabel = document.getElementById('live-label');

    toggle.checked = !isPaper;

    if (isPaper) {
        paperLabel.classList.add('active');
        paperLabel.classList.remove('live');
        liveLabel.classList.remove('active', 'live');
        document.body.classList.remove('live-mode');
    } else {
        paperLabel.classList.remove('active');
        liveLabel.classList.add('active', 'live');
        document.body.classList.add('live-mode');
    }
}

function loadTradingMode() {
    fetch('/api/mode')
        .then(response => response.json())
        .then(data => {
            updateModeUI(data.paper);
        })
        .catch(error => console.error('Error loading trading mode:', error));
}

// ==================== SSE STREAMING ====================

function connectSSE() {
    if (eventSource) {
        eventSource.close();
    }

    eventSource = new EventSource('/api/stream');

    eventSource.onopen = () => {
        console.log('SSE connected');
    };

    eventSource.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            handleSSEMessage(data);
        } catch (e) {
            console.error('SSE parse error:', e);
        }
    };

    eventSource.onerror = (error) => {
        console.error('SSE error:', error);
        // Reconnect after 5 seconds
        setTimeout(connectSSE, 5000);
    };
}

function handleSSEMessage(data) {
    console.log('SSE message:', data.type, data);

    switch (data.type) {
        case 'connected':
            console.log('SSE connection confirmed');
            break;

        case 'quote':
            // Real-time quote update from WebSocket
            handleStreamingQuote(data);
            break;

        case 'fill':
            // Order filled, update UI
            handleOrderFill(data);
            break;

        case 'profit_placed':
            // Profit target order placed via WebSocket
            handleProfitPlaced(data);
            break;

        case 'profit_failed':
            // Profit target order failed
            handleProfitFailed(data);
            break;

        case 'bracket_placed':
            // Bracket TP/SL orders placed via WebSocket
            handleBracketPlaced(data);
            break;

        case 'bracket_failed':
            // Bracket orders failed
            handleBracketFailed(data);
            break;

        case 'trigger_hit':
            // Trigger price reached, stop order placed
            handleTriggerHit(data);
            break;

        case 'trade_update':
            // General trade update
            handleTradeUpdate(data);
            break;
    }
}

function handleOrderFill(data) {
    console.log(`Order ${data.order_id} filled at ${data.fill_price}`);

    // Check if we're monitoring this order
    if (pendingOrders[data.order_id]) {
        const order = pendingOrders[data.order_id];

        // Update status card
        updateOrderStatus('waiting_trigger',
            `✅ Filled @ ${formatCurrency(data.fill_price)}. Waiting for trigger @ ${formatCurrency(data.trigger_price)}...`
        );

        // Start trigger monitoring (polling still needed for price check)
        startTriggerMonitoring(data.order_id, order.config);
    }

    // Refresh UI
    loadOrders();
    loadPositions();
    loadAccount();
}

function handleProfitPlaced(data) {
    console.log(`Profit target placed for ${data.symbol} @ ${data.profit_price}`);

    // Clear monitoring
    if (fillCheckInterval) {
        clearInterval(fillCheckInterval);
    }

    if (pendingOrders[data.order_id]) {
        delete pendingOrders[data.order_id];
    }

    // Update status
    updateOrderStatus('complete',
        `✅ Filled @ ${formatCurrency(data.fill_price)}. Profit sell placed @ ${formatCurrency(data.profit_price)}`
    );

    // Refresh UI
    loadOrders();
    loadPositions();
}

function handleProfitFailed(data) {
    console.log(`Profit target failed for ${data.symbol}: ${data.error}`);

    // Update status
    updateOrderStatus('error', `❌ Profit order failed: ${data.error}`);

    // Refresh UI
    loadOrders();
}

function handleBracketPlaced(data) {
    console.log(`Bracket orders placed for ${data.symbol}: TP=${data.tp_price}, SL=${data.sl_price}`);

    // Clear monitoring
    if (fillCheckInterval) {
        clearInterval(fillCheckInterval);
    }

    if (pendingOrders[data.order_id]) {
        delete pendingOrders[data.order_id];
    }

    // Update status
    updateOrderStatus('complete',
        `✅ Filled @ ${formatCurrency(data.fill_price)}. TP @ ${formatCurrency(data.tp_price)}, SL @ ${formatCurrency(data.sl_price)}`
    );

    // Refresh UI
    loadOrders();
    loadPositions();
}

function handleBracketFailed(data) {
    console.log(`Bracket orders failed for ${data.symbol}: ${data.error}`);

    // Update status
    updateOrderStatus('error', `❌ Bracket orders failed: ${data.error}`);

    // Refresh UI
    loadOrders();
}

function handleTriggerHit(data) {
    console.log(`Trigger hit for ${data.symbol}, stop order ${data.stop_order_id} placed`);

    // Clear monitoring
    if (fillCheckInterval) {
        clearInterval(fillCheckInterval);
    }

    if (pendingOrders[data.order_id]) {
        delete pendingOrders[data.order_id];
    }

    // Update status
    const stopPrice = data.stop_price ? `@ ${formatCurrency(data.stop_price)}` : `@ ${data.trail_amount} trail`;
    updateOrderStatus('complete', `✅ Trigger hit! Stop order placed ${stopPrice}`);

    // Refresh UI
    loadOrders();
    loadPositions();
}

function handleTradeUpdate(data) {
    console.log(`Trade update: ${data.event} for ${data.symbol}`);

    // Refresh orders on any trade update
    loadOrders();
}

// ==================== ACCOUNT ====================

async function loadAccount() {
    try {
        const response = await fetch('/api/account');
        const data = await response.json();

        if (data.success && data.account) {
            accountData = data.account;
            document.getElementById('cash').textContent = formatCurrency(data.account.cash);
            document.getElementById('buying-power').textContent = formatCurrency(data.account.buying_power);
            document.getElementById('portfolio-value').textContent = formatCurrency(data.account.portfolio_value);
            document.getElementById('connection-status').textContent = 'Connected';
            document.getElementById('connection-status').classList.add('authenticated');
        } else {
            document.getElementById('connection-status').textContent = 'Error';
            console.error('Account error:', data.error);
        }
    } catch (e) {
        console.error('Failed to load account:', e);
        document.getElementById('connection-status').textContent = 'Disconnected';
    }
}

// ==================== POSITIONS ====================

async function loadPositions() {
    try {
        const response = await fetch('/api/positions');
        const data = await response.json();

        const container = document.getElementById('positions-list');

        if (data.success && data.positions && data.positions.length > 0) {
            container.innerHTML = data.positions.map(pos => `
                <div class="position-item">
                    <div class="pos-main">
                        <span class="position-symbol">${pos.symbol}</span>
                        <span class="position-qty">${pos.qty} shares</span>
                        <span class="position-pnl ${pos.unrealized_pl >= 0 ? 'positive' : 'negative'}">
                            ${formatCurrency(pos.unrealized_pl)} (${formatPercent(pos.unrealized_plpc)})
                        </span>
                    </div>
                    <div class="pos-details">
                        <span>Entry: ${formatCurrency(pos.avg_entry_price)}</span>
                        <span>Current: ${formatCurrency(pos.current_price)}</span>
                        <span>Value: ${formatCurrency(pos.market_value)}</span>
                    </div>
                </div>
            `).join('');
        } else {
            container.innerHTML = '<div class="placeholder-text">No positions</div>';
        }
    } catch (e) {
        console.error('Failed to load positions:', e);
    }
}

// ==================== ORDERS ====================

async function loadOrders() {
    try {
        const response = await fetch('/api/orders?status=open');
        const data = await response.json();

        const container = document.getElementById('orders-list');

        if (data.success && data.orders && data.orders.length > 0) {
            container.innerHTML = data.orders.map(order => `
                <div class="order-item">
                    <div class="order-main">
                        <span class="order-symbol">${order.symbol}</span>
                        <span class="order-action ${order.side}">${order.side}</span>
                        <span>${order.qty} @ ${order.limit_price ? formatCurrency(order.limit_price) : 'MKT'}</span>
                    </div>
                    <div class="order-details">
                        <span>${order.type}</span>
                        <span>${order.status}</span>
                    </div>
                    <div class="order-actions">
                        <button class="btn btn-danger btn-small" onclick="cancelOrder('${order.id}')">Cancel</button>
                    </div>
                </div>
            `).join('');
        } else {
            container.innerHTML = '<div class="placeholder-text">No open orders</div>';
        }
    } catch (e) {
        console.error('Failed to load orders:', e);
    }
}

async function cancelOrder(orderId) {
    try {
        const response = await fetch(`/api/orders/${orderId}/cancel`, { method: 'POST' });
        const data = await response.json();

        if (data.success) {
            loadOrders();
            loadPositions();
        } else {
            alert('Failed to cancel: ' + data.error);
        }
    } catch (e) {
        console.error('Cancel order failed:', e);
        alert('Cancel failed: ' + e.message);
    }
}

// ==================== QUOTES ====================

async function getQuote() {
    const symbol = document.getElementById('quote-symbol').value.toUpperCase();
    if (!symbol) return;

    try {
        const response = await fetch(`/api/quote/${symbol}`);
        const data = await response.json();

        if (data.success && data.quote) {
            currentQuote = data.quote;
            displayQuote(data.quote);

            // Pre-fill order symbol
            document.getElementById('order-symbol').value = symbol;
        } else {
            alert('Quote error: ' + (data.error || 'Unknown error'));
        }
    } catch (e) {
        console.error('Quote failed:', e);
        alert('Failed to get quote: ' + e.message);
    }
}

function displayQuote(quote) {
    document.getElementById('quote-display').style.display = 'block';
    document.getElementById('quote-symbol-display').textContent = quote.symbol;
    document.getElementById('quote-last').textContent = formatCurrency(quote.last);
    document.getElementById('quote-bid').textContent = formatCurrency(quote.bid);
    document.getElementById('quote-ask').textContent = formatCurrency(quote.ask);
    document.getElementById('quote-bid-size').textContent = `x${quote.bid_size || ''}`;
    document.getElementById('quote-ask-size').textContent = `x${quote.ask_size || ''}`;
}

// ==================== STREAMING QUOTES ====================

async function toggleStreaming() {
    const symbol = document.getElementById('quote-symbol').value.toUpperCase();
    if (!symbol) {
        alert('Please enter a symbol first');
        return;
    }

    const btn = document.getElementById('stream-toggle-btn');
    const badge = document.getElementById('streaming-badge');

    if (isStreamingQuotes && streamingSymbol === symbol) {
        // Stop streaming this symbol
        await unsubscribeQuotes([symbol]);
        isStreamingQuotes = false;
        streamingSymbol = null;
        btn.textContent = 'Stream';
        btn.classList.remove('streaming');
        badge.style.display = 'none';
    } else {
        // If streaming a different symbol, unsubscribe first
        if (streamingSymbol) {
            await unsubscribeQuotes([streamingSymbol]);
        }

        // Start streaming new symbol
        const success = await subscribeQuotes([symbol]);
        if (success) {
            isStreamingQuotes = true;
            streamingSymbol = symbol;
            btn.textContent = 'Stop';
            btn.classList.add('streaming');
            badge.style.display = 'inline';
        }
    }
}

// Auto-stream quotes when symbol is entered
let symbolInputTimeout = null;

function setupAutoStreaming() {
    const symbolInput = document.getElementById('quote-symbol');

    symbolInput.addEventListener('input', () => {
        // Debounce - wait 500ms after user stops typing
        clearTimeout(symbolInputTimeout);
        symbolInputTimeout = setTimeout(async () => {
            const symbol = symbolInput.value.toUpperCase().trim();

            // Unsubscribe from previous symbol
            if (streamingSymbol && streamingSymbol !== symbol) {
                await unsubscribeQuotes([streamingSymbol]);
                streamingSymbol = null;
                isStreamingQuotes = false;
            }

            if (symbol && symbol.length > 0) {
                // Subscribe to new symbol
                const success = await subscribeQuotes([symbol]);
                if (success) {
                    streamingSymbol = symbol;
                    isStreamingQuotes = true;
                    console.log('Auto-subscribed to:', symbol);
                }
            } else {
                // Clear display if no symbol
                document.getElementById('quote-display').style.display = 'none';
            }
        }, 500);
    });
}

async function subscribeQuotes(symbols) {
    try {
        const response = await fetch('/api/quotes/subscribe', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ symbols: symbols })
        });
        const data = await response.json();

        if (!data.success) {
            alert('Subscription error: ' + (data.error || 'Unknown error'));
            return false;
        }

        console.log('Subscribed to quotes:', data.subscribed);
        return true;
    } catch (e) {
        console.error('Subscribe failed:', e);
        alert('Failed to subscribe: ' + e.message);
        return false;
    }
}

async function unsubscribeQuotes(symbols) {
    try {
        const response = await fetch('/api/quotes/unsubscribe', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ symbols: symbols })
        });
        const data = await response.json();

        if (data.success) {
            console.log('Unsubscribed from quotes:', data.unsubscribed);
        }
    } catch (e) {
        console.error('Unsubscribe failed:', e);
    }
}

function handleStreamingQuote(data) {
    const symbol = document.getElementById('quote-symbol').value.toUpperCase();

    // Only update if symbol matches what we're viewing
    if (data.symbol !== symbol) return;

    currentQuote = {
        symbol: data.symbol,
        bid: data.bid,
        ask: data.ask,
        bid_size: data.bid_size,
        ask_size: data.ask_size,
        last: data.last
    };

    displayQuote(currentQuote);

    // Flash effect on price update
    const lastEl = document.getElementById('quote-last');
    lastEl.classList.add('price-flash');
    setTimeout(() => lastEl.classList.remove('price-flash'), 200);
}

// ==================== ORDER ENTRY ====================

function toggleOrderType() {
    const orderType = document.getElementById('order-type').value;
    const limitSection = document.getElementById('limit-section');
    limitSection.style.display = orderType === 'LIMIT' ? 'block' : 'none';
}

function toggleLimitPriceInput() {
    const priceType = document.getElementById('limit-price-type').value;
    const manualInput = document.getElementById('manual-limit-input');
    manualInput.style.display = priceType === 'manual' ? 'block' : 'none';
}

function toggleExitStrategy() {
    const strategy = document.getElementById('exit-strategy').value;

    // Hide all exit strategy inputs
    document.getElementById('profit-target-input').style.display = 'none';
    document.getElementById('confirmation-stop-input').style.display = 'none';
    document.getElementById('trailing-stop-input').style.display = 'none';
    document.getElementById('bracket-input').style.display = 'none';

    // Show selected one and update its description
    if (strategy === 'profit-target') {
        document.getElementById('profit-target-input').style.display = 'block';
        updateProfitLabel();  // Update the description with current value
    } else if (strategy === 'confirmation-stop') {
        document.getElementById('confirmation-stop-input').style.display = 'block';
    } else if (strategy === 'trailing-stop') {
        document.getElementById('trailing-stop-input').style.display = 'block';
    } else if (strategy === 'bracket') {
        document.getElementById('bracket-input').style.display = 'block';
    }
}

function updateProfitLabel() {
    const type = document.getElementById('profit-offset-type').value;
    const value = parseFloat(document.getElementById('profit-offset').value) || 0.50;
    const side = document.getElementById('order-side').value;

    // Update description based on side
    // BUY: profit when price goes UP -> place LIMIT SELL at fill_price + offset
    // SELL (short): profit when price goes DOWN -> place LIMIT BUY at fill_price - offset
    const descEl = document.getElementById('profit-desc');
    if (type === 'percent') {
        descEl.textContent = `${value}%`;
    } else {
        descEl.textContent = `$${value.toFixed(2)}`;
    }

    // Update the strategy description
    const strategyDesc = document.getElementById('profit-strategy-desc');
    if (side === 'BUY') {
        strategyDesc.innerHTML = `On fill, place LIMIT SELL at fill_price + <span class="highlight">${type === 'percent' ? value + '%' : '$' + value.toFixed(2)}</span>`;
    } else {
        strategyDesc.innerHTML = `On fill, place LIMIT BUY at fill_price - <span class="highlight">${type === 'percent' ? value + '%' : '$' + value.toFixed(2)}</span>`;
    }
}

function updateSubmitButton() {
    const side = document.getElementById('order-side').value;
    const btn = document.getElementById('submit-order-btn');
    btn.textContent = side;
    btn.className = `btn ${side === 'SELL' ? 'btn-danger' : 'btn-buy'}`;

    // Update bracket order description
    const bracketDesc = document.getElementById('bracket-desc');
    if (bracketDesc) {
        if (side === 'BUY') {
            bracketDesc.textContent = 'BUY: TP above entry (profit), SL below entry (loss limit).';
        } else {
            bracketDesc.textContent = 'SELL: TP below entry (profit when drops), SL above entry (loss limit).';
        }
    }

    // Also update profit target label
    updateProfitLabel();
}

async function submitOrder() {
    const symbol = document.getElementById('order-symbol').value.toUpperCase();
    const quantity = parseInt(document.getElementById('order-quantity').value);
    const side = document.getElementById('order-side').value;
    const orderType = document.getElementById('order-type').value;
    const exitStrategy = document.getElementById('exit-strategy').value;

    if (!symbol || !quantity) {
        alert('Symbol and quantity required');
        return;
    }

    // Build order payload
    let payload = {
        symbol: symbol,
        side: side,
        quantity: quantity,
        order_type: orderType
    };

    // Handle limit price
    if (orderType === 'LIMIT') {
        const limitPriceType = document.getElementById('limit-price-type').value;

        if (limitPriceType === 'manual') {
            const limitPrice = parseFloat(document.getElementById('limit-price').value);
            if (!limitPrice) {
                alert('Limit price required for limit orders');
                return;
            }
            payload.limit_price = limitPrice;
        } else {
            // bid or ask - server will fetch quote and use appropriate price
            payload.limit_price_type = limitPriceType;
        }
    }

    // Add exit strategy params
    if (exitStrategy === 'bracket') {
        payload.exit_strategy = 'bracket';
        const tpOffset = parseFloat(document.getElementById('bracket-tp-offset').value);
        const slOffset = parseFloat(document.getElementById('bracket-sl-offset').value);
        const tpType = document.getElementById('bracket-tp-type').value;
        const slType = document.getElementById('bracket-sl-type').value;

        if (!tpOffset || !slOffset || tpOffset <= 0 || slOffset <= 0) {
            alert('Take Profit and Stop Loss offsets must be positive values');
            return;
        }

        payload.bracket_tp_offset = tpOffset;
        payload.bracket_sl_offset = slOffset;
        payload.bracket_tp_type = tpType;
        payload.bracket_sl_type = slType;
        payload.fill_timeout = parseInt(document.getElementById('bracket-fill-timeout').value);

    } else if (exitStrategy === 'profit-target') {
        payload.exit_strategy = 'profit-target';
        payload.profit_offset_type = document.getElementById('profit-offset-type').value;
        payload.profit_offset = parseFloat(document.getElementById('profit-offset').value);
        payload.fill_timeout = parseInt(document.getElementById('pt-fill-timeout').value);

    } else if (exitStrategy === 'confirmation-stop') {
        payload.exit_strategy = 'confirmation-stop';
        payload.cs_trigger_type = document.getElementById('cs-trigger-type').value;
        payload.cs_trigger_offset = parseFloat(document.getElementById('cs-trigger-offset').value);
        payload.cs_stop_type = document.getElementById('cs-stop-type').value;
        payload.cs_stop_offset = parseFloat(document.getElementById('cs-stop-offset').value);
        payload.fill_timeout = parseInt(document.getElementById('cs-fill-timeout').value);
        payload.trigger_timeout = parseInt(document.getElementById('cs-trigger-timeout').value);

    } else if (exitStrategy === 'trailing-stop') {
        payload.exit_strategy = 'trailing-stop';
        payload.tsl_trigger_type = document.getElementById('tsl-trigger-type').value;
        payload.tsl_trigger_offset = parseFloat(document.getElementById('tsl-trigger-offset').value);
        payload.tsl_trail_type = document.getElementById('tsl-trail-type').value;
        payload.tsl_trail_amount = parseFloat(document.getElementById('tsl-trail-amount').value);
        payload.fill_timeout = parseInt(document.getElementById('tsl-fill-timeout').value);
        payload.trigger_timeout = parseInt(document.getElementById('tsl-trigger-timeout').value);
    }

    try {
        const response = await fetch('/api/orders/place', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await response.json();

        showOrderResponse(data);

        if (data.success) {
            loadOrders();
            loadPositions();
            loadAccount();

            // Track orders with exit strategies for SSE handling
            if (exitStrategy !== 'none' && data.monitoring) {
                pendingOrders[data.order.id] = {
                    config: data.monitoring,
                    strategy: exitStrategy
                };

                // Show status card and start fill monitoring
                // WebSocket will handle fill detection, but we poll as backup
                if (exitStrategy === 'bracket') {
                    startBracketMonitoring(data.order.id, data.monitoring);
                } else if (exitStrategy === 'profit-target') {
                    startProfitTargetMonitoring(data.order.id, data.monitoring);
                } else if (exitStrategy === 'confirmation-stop') {
                    startConfirmationStopMonitoring(data.order.id, data.monitoring);
                } else if (exitStrategy === 'trailing-stop') {
                    startTrailingStopMonitoring(data.order.id, data.monitoring);
                }
            }

            // For market orders with exit strategies, check fill status immediately
            if (orderType === 'MARKET' && data.monitoring) {
                setTimeout(() => {
                    console.log('Market order - checking fill status immediately');
                    checkFillStatusImmediately(data.order.id, exitStrategy);
                }, 500);
            }

            // For bracket orders, update the response to show TP/SL info
            if (exitStrategy === 'bracket') {
                const side = document.getElementById('order-side').value;
                const closeSide = side === 'BUY' ? 'SELL' : 'BUY';

                setTimeout(() => {
                    updateOrderResponseForBracket(data.order.id, null, null, closeSide);
                }, 1000);
            }
        }
    } catch (e) {
        console.error('Order failed:', e);
        showOrderResponse({ success: false, error: e.message });
    }
}

function showOrderResponse(data) {
    const responseArea = document.getElementById('order-response');
    const responseContent = document.getElementById('order-response-content');
    responseArea.style.display = 'block';

    if (data.success) {
        responseArea.className = 'card response-area success';
        lastPlacedOrder = {
            id: data.order.id,
            symbol: data.order.symbol,
            side: data.order.side,
            qty: data.order.qty,
            status: data.order.status
        };

        updateOrderResponseDisplay();

        // Start polling for order status updates
        startOrderStatusPolling();
    } else {
        responseArea.className = 'card response-area error';
        responseContent.innerHTML = `<div class="error-text">❌ Error: ${data.error}</div>`;
        lastPlacedOrder = null;
    }
}

function updateOrderResponseDisplay() {
    if (!lastPlacedOrder) return;

    const responseContent = document.getElementById('order-response-content');
    const status = lastPlacedOrder.status;
    const fillPrice = lastPlacedOrder.fill_price;
    const filledQty = lastPlacedOrder.filled_qty;

    let statusIcon = '⏳';
    let statusClass = '';

    if (status === 'filled') {
        statusIcon = '✅';
        statusClass = 'status-filled';
    } else if (status === 'canceled' || status === 'cancelled') {
        statusIcon = '❌';
        statusClass = 'status-cancelled';
    } else if (status === 'rejected' || status === 'expired') {
        statusIcon = '⚠️';
        statusClass = 'status-error';
    }

    let fillInfo = '';
    if (fillPrice && parseFloat(fillPrice) > 0) {
        fillInfo = `<br>Fill Price: ${formatCurrency(fillPrice)}`;
    }
    if (filledQty && parseFloat(filledQty) > 0) {
        fillInfo += `<br>Filled Qty: ${filledQty}`;
    }

    responseContent.innerHTML = `
        <div class="success-text">${statusIcon} Order ${status.charAt(0).toUpperCase() + status.slice(1)}</div>
        <div class="order-summary ${statusClass}">
            <strong>${lastPlacedOrder.side}</strong> ${lastPlacedOrder.qty} ${lastPlacedOrder.symbol}
            <br>Order ID: ${lastPlacedOrder.id}
            <br>Status: ${status}
            ${fillInfo}
        </div>
    `;
}

async function updateOrderResponseForBracket(orderId, tpPrice, slPrice, closeSide) {
    try {
        // Fetch all orders to find the bracket children
        const res = await fetch('/api/orders?status=open');
        const data = await res.json();

        if (data.success && data.orders) {
            const tpOrder = data.orders.find(o => o.side === closeSide.toLowerCase() && o.type === 'limit' && o.limit_price);
            const slOrder = data.orders.find(o => o.type === 'stop' || o.type === 'stop_limit');

            const responseContent = document.getElementById('order-response-content');

            let bracketInfo = '';
            if (tpOrder) {
                bracketInfo += `<br>TP: ${formatCurrency(tpOrder.limit_price)}`;
            }
            if (slOrder) {
                bracketInfo += `<br>SL: ${formatCurrency(slOrder.stop_price || slOrder.limit_price)}`;
            }

            if (bracketInfo) {
                responseContent.innerHTML += `<div class="bracket-info" style="margin-top:8px;padding:8px;background:rgba(34,197,94,0.1);border-radius:4px;">${bracketInfo}</div>`;
            }
        }
    } catch (e) {
        console.error('Error updating bracket order display:', e);
    }
}

function startOrderStatusPolling() {
    if (orderStatusInterval) {
        clearInterval(orderStatusInterval);
    }

    async function checkOrderStatus() {
        if (!lastPlacedOrder) {
            clearInterval(orderStatusInterval);
            return;
        }

        try {
            const res = await fetch(`/api/orders/${lastPlacedOrder.id}`);
            const data = await res.json();

            if (data.success && data.order) {
                const newStatus = data.order.status;
                const statusChanged = newStatus !== lastPlacedOrder.status;

                lastPlacedOrder.status = newStatus;
                lastPlacedOrder.fill_price = data.order.filled_avg_price;
                lastPlacedOrder.filled_qty = data.order.filled_qty;

                if (statusChanged) {
                    console.log(`Order ${lastPlacedOrder.id} status changed to: ${newStatus}`);
                    updateOrderResponseDisplay();

                    // Stop polling if order is in a final state
                    if (['filled', 'canceled', 'cancelled', 'rejected', 'expired'].includes(newStatus)) {
                        clearInterval(orderStatusInterval);
                        loadOrders();
                        loadPositions();
                        loadAccount();
                    }
                }
            }
        } catch (e) {
            console.error('Order status check error:', e);
        }
    }

    // Check immediately and then every 1 second
    checkOrderStatus();
    orderStatusInterval = setInterval(checkOrderStatus, 1000);
}

// ==================== ORDER MONITORING ====================

async function checkFillStatusImmediately(orderId, strategy) {
    try {
        const res = await fetch(`/api/orders/${orderId}/fill-status`);
        const data = await res.json();
        console.log('Immediate fill check:', data);

        if (data.filled) {
            // Clear the polling interval if it exists
            if (fillCheckInterval) {
                clearInterval(fillCheckInterval);
            }

            if (strategy === 'profit-target') {
                if (data.profit_order_placed) {
                    updateOrderStatus('complete',
                        `✅ Filled @ ${formatCurrency(data.fill_price)}. Profit sell placed @ ${formatCurrency(data.profit_price)}`
                    );
                } else if (data.error) {
                    updateOrderStatus('error', `❌ Profit order failed: ${data.error}`);
                }
            } else if (strategy === 'bracket') {
                if (data.bracket_orders_placed) {
                    updateOrderStatus('complete',
                        `✅ Filled @ ${formatCurrency(data.fill_price)}. TP @ ${formatCurrency(data.tp_price)}, SL @ ${formatCurrency(data.sl_price)}`
                    );
                } else if (data.error) {
                    updateOrderStatus('error', `❌ Bracket orders failed: ${data.error}`);
                }
            } else if (strategy === 'confirmation-stop' || strategy === 'trailing-stop') {
                updateOrderStatus('waiting_trigger',
                    `✅ Filled @ ${formatCurrency(data.fill_price)}. Waiting for trigger @ ${formatCurrency(data.trigger_price)}...`
                );
                // Continue with trigger monitoring
                if (pendingOrders[orderId]) {
                    startTriggerMonitoring(orderId, pendingOrders[orderId].config);
                }
            }

            loadOrders();
            loadPositions();
            loadAccount();
            delete pendingOrders[orderId];
        }
    } catch (e) {
        console.error('Immediate fill check error:', e);
    }
}

function startProfitTargetMonitoring(orderId, config) {
    const statusCard = document.getElementById('order-status-card');
    const statusContent = document.getElementById('order-status-content');
    statusCard.style.display = 'block';

    const fillTimeout = config.fill_timeout || 15;
    let fillElapsed = 0;

    if (fillCheckInterval) clearInterval(fillCheckInterval);

    console.log(`Starting Profit Target monitoring for order ${orderId}, fill timeout: ${fillTimeout}s`);
    updateOrderStatus('waiting_fill', `Waiting for fill... (0/${fillTimeout}s)`);

    async function doMonitor() {
        try {
            const res = await fetch(`/api/orders/${orderId}/fill-status`);
            const data = await res.json();

            if (data.filled) {
                clearInterval(fillCheckInterval);
                console.log(`Order ${orderId} filled at ${data.fill_price}, profit target order should be placed`);

                // Check if profit target order was placed
                if (data.profit_order_placed) {
                    updateOrderStatus('complete',
                        `✅ Filled @ ${formatCurrency(data.fill_price)}. Profit sell placed @ ${formatCurrency(data.profit_price)}`
                    );
                } else if (data.error) {
                    updateOrderStatus('error', `❌ Profit order failed: ${data.error}`);
                }
                loadOrders();
                loadPositions();
                loadAccount();
                delete pendingOrders[orderId];
                return;
            }

            fillElapsed++;
            updateOrderStatus('waiting_fill', `Waiting for fill... (${fillElapsed}/${fillTimeout}s)`);

            if (fillElapsed >= fillTimeout) {
                clearInterval(fillCheckInterval);
                updateOrderStatus('timeout', `⚠️ Fill timeout. Cancelling order...`);
                console.log(`Fill timeout reached, cancelling order ${orderId}`);
                const cancelRes = await fetch(`/api/orders/${orderId}/cancel`, { method: 'POST' });
                const cancelData = await cancelRes.json();
                console.log('Cancel result:', cancelData);

                if (cancelData.success) {
                    updateOrderStatus('timeout', `⚠️ Fill timeout. Order cancelled.`);
                } else {
                    updateOrderStatus('error', `❌ Cancel failed: ${cancelData.error}`);
                }

                await new Promise(r => setTimeout(r, 500));
                loadOrders();
                loadPositions();
                loadAccount();
                delete pendingOrders[orderId];
            }
        } catch (e) {
            console.error('Profit target monitoring error:', e);
            fillElapsed++;
        }
    }

    fillCheckInterval = setInterval(doMonitor, 1000);
}

function startBracketMonitoring(orderId, config) {
    const statusCard = document.getElementById('order-status-card');
    const statusContent = document.getElementById('order-status-content');
    statusCard.style.display = 'block';

    const fillTimeout = config.fill_timeout || 15;
    let fillElapsed = 0;

    if (fillCheckInterval) clearInterval(fillCheckInterval);

    console.log(`Starting Bracket monitoring for order ${orderId}, fill timeout: ${fillTimeout}s`);
    updateOrderStatus('waiting_fill', `Waiting for fill... (0/${fillTimeout}s)`);

    async function doMonitor() {
        try {
            const res = await fetch(`/api/orders/${orderId}/fill-status`);
            const data = await res.json();

            if (data.filled) {
                clearInterval(fillCheckInterval);
                console.log(`Order ${orderId} filled at ${data.fill_price}, bracket orders should be placed`);

                // Check if bracket orders were placed
                if (data.bracket_orders_placed) {
                    updateOrderStatus('complete',
                        `✅ Filled @ ${formatCurrency(data.fill_price)}. TP @ ${formatCurrency(data.tp_price)}, SL @ ${formatCurrency(data.sl_price)}`
                    );
                } else if (data.error) {
                    updateOrderStatus('error', `❌ Bracket orders failed: ${data.error}`);
                }
                loadOrders();
                loadPositions();
                loadAccount();
                delete pendingOrders[orderId];
                return;
            }

            fillElapsed++;
            updateOrderStatus('waiting_fill', `Waiting for fill... (${fillElapsed}/${fillTimeout}s)`);

            if (fillElapsed >= fillTimeout) {
                clearInterval(fillCheckInterval);
                updateOrderStatus('timeout', `⚠️ Fill timeout. Cancelling order...`);
                console.log(`Fill timeout reached, cancelling order ${orderId}`);
                const cancelRes = await fetch(`/api/orders/${orderId}/cancel`, { method: 'POST' });
                const cancelData = await cancelRes.json();
                console.log('Cancel result:', cancelData);

                if (cancelData.success) {
                    updateOrderStatus('timeout', `⚠️ Fill timeout. Order cancelled.`);
                } else {
                    updateOrderStatus('error', `❌ Cancel failed: ${cancelData.error}`);
                }

                await new Promise(r => setTimeout(r, 500));
                loadOrders();
                loadPositions();
                loadAccount();
                delete pendingOrders[orderId];
            }
        } catch (e) {
            console.error('Bracket monitoring error:', e);
            fillElapsed++;
        }
    }

    fillCheckInterval = setInterval(doMonitor, 1000);
}

function startConfirmationStopMonitoring(orderId, config) {
    const statusCard = document.getElementById('order-status-card');
    const statusContent = document.getElementById('order-status-content');
    statusCard.style.display = 'block';

    const fillTimeout = config.fill_timeout || 15;
    const triggerTimeout = config.trigger_timeout || 300;
    let state = 'waiting_fill';
    let fillElapsed = 0;
    let triggerElapsed = 0;

    if (fillCheckInterval) clearInterval(fillCheckInterval);

    console.log(`Starting Confirmation Stop monitoring for order ${orderId}, fill timeout: ${fillTimeout}s`);
    updateOrderStatus('waiting_fill', `Waiting for fill... (0/${fillTimeout}s)`);

    async function doMonitor() {
        try {
            if (state === 'waiting_fill') {
                const res = await fetch(`/api/orders/${orderId}/fill-status`);
                const data = await res.json();

                if (data.filled) {
                    state = 'waiting_trigger';
                    fillElapsed = 0;
                    console.log(`Order ${orderId} filled at ${data.fill_price}`);
                    updateOrderStatus('waiting_trigger',
                        `✅ Filled @ ${formatCurrency(data.fill_price)}. Waiting for trigger @ ${formatCurrency(data.trigger_price)}...`
                    );
                    loadOrders();
                    return;
                }

                fillElapsed++;
                updateOrderStatus('waiting_fill', `Waiting for fill... (${fillElapsed}/${fillTimeout}s)`);

                if (fillElapsed >= fillTimeout) {
                    clearInterval(fillCheckInterval);
                    updateOrderStatus('timeout', `⚠️ Fill timeout. Cancelling order...`);
                    console.log(`Fill timeout reached, cancelling order ${orderId}`);
                    const cancelRes = await fetch(`/api/orders/${orderId}/cancel`, { method: 'POST' });
                    const cancelData = await cancelRes.json();
                    console.log('Cancel result:', cancelData);

                    if (cancelData.success) {
                        updateOrderStatus('timeout', `⚠️ Fill timeout. Order cancelled.`);
                    } else {
                        updateOrderStatus('error', `❌ Cancel failed: ${cancelData.error}`);
                    }

                    // Small delay to let Alpaca process the cancellation
                    await new Promise(r => setTimeout(r, 500));
                    loadOrders();
                    loadPositions();
                    loadAccount();
                }

            } else if (state === 'waiting_trigger') {
                const res = await fetch(`/api/exit-strategy/${orderId}/check-trigger`);
                const data = await res.json();

                if (data.triggered) {
                    clearInterval(fillCheckInterval);
                    updateOrderStatus('complete',
                        `✅ Trigger hit! Stop limit placed @ ${formatCurrency(data.stop_price)}`
                    );
                    loadOrders();
                    loadPositions();
                    return;
                }

                triggerElapsed++;
                const priceInfo = data.current_price ? ` (${formatCurrency(data.current_price)} → ${formatCurrency(data.trigger_price)})` : '';
                updateOrderStatus('waiting_trigger',
                    `Waiting for trigger...${priceInfo} (${triggerElapsed}/${triggerTimeout}s)`
                );

                if (triggerElapsed >= triggerTimeout) {
                    clearInterval(fillCheckInterval);
                    updateOrderStatus('timeout', `⚠️ Trigger timeout. Position remains open without stop.`);
                }
            }
        } catch (e) {
            console.error('Monitoring error:', e);
            fillElapsed++; // Count errors toward timeout
        }
    }

    fillCheckInterval = setInterval(doMonitor, 1000);
}

function startTrailingStopMonitoring(orderId, config) {
    const statusCard = document.getElementById('order-status-card');
    const statusContent = document.getElementById('order-status-content');
    statusCard.style.display = 'block';

    const fillTimeout = config.fill_timeout || 15;
    const triggerTimeout = config.trigger_timeout || 300;
    let state = 'waiting_fill';
    let fillElapsed = 0;
    let triggerElapsed = 0;

    if (fillCheckInterval) clearInterval(fillCheckInterval);

    console.log(`Starting Trailing Stop monitoring for order ${orderId}, fill timeout: ${fillTimeout}s`);
    updateOrderStatus('waiting_fill', `Waiting for fill... (0/${fillTimeout}s)`);

    async function doMonitor() {
        try {
            if (state === 'waiting_fill') {
                const res = await fetch(`/api/orders/${orderId}/fill-status`);
                const data = await res.json();

                if (data.filled) {
                    state = 'waiting_trigger';
                    fillElapsed = 0;
                    console.log(`Order ${orderId} filled at ${data.fill_price}`);
                    updateOrderStatus('waiting_trigger',
                        `✅ Filled @ ${formatCurrency(data.fill_price)}. Waiting for trigger @ ${formatCurrency(data.trigger_price)}...`
                    );
                    loadOrders();
                    return;
                }

                fillElapsed++;
                updateOrderStatus('waiting_fill', `Waiting for fill... (${fillElapsed}/${fillTimeout}s)`);

                if (fillElapsed >= fillTimeout) {
                    clearInterval(fillCheckInterval);
                    updateOrderStatus('timeout', `⚠️ Fill timeout. Cancelling order...`);
                    console.log(`Fill timeout reached, cancelling order ${orderId}`);
                    const cancelRes = await fetch(`/api/orders/${orderId}/cancel`, { method: 'POST' });
                    const cancelData = await cancelRes.json();
                    console.log('Cancel result:', cancelData);

                    if (cancelData.success) {
                        updateOrderStatus('timeout', `⚠️ Fill timeout. Order cancelled.`);
                    } else {
                        updateOrderStatus('error', `❌ Cancel failed: ${cancelData.error}`);
                    }

                    // Small delay to let Alpaca process the cancellation
                    await new Promise(r => setTimeout(r, 500));
                    loadOrders();
                    loadPositions();
                    loadAccount();
                }

            } else if (state === 'waiting_trigger') {
                const res = await fetch(`/api/exit-strategy/${orderId}/check-trigger`);
                const data = await res.json();

                if (data.triggered) {
                    clearInterval(fillCheckInterval);
                    if (data.stop_order_id) {
                        updateOrderStatus('complete',
                            `✅ Trigger hit! Trailing stop placed @ ${data.trail_amount} trail`
                        );
                    } else if (data.error) {
                        updateOrderStatus('error', `❌ Trailing stop failed: ${data.error}`);
                    }
                    loadOrders();
                    loadPositions();
                    return;
                }

                triggerElapsed++;
                const priceInfo = data.current_price ? ` (${formatCurrency(data.current_price)} → ${formatCurrency(data.trigger_price)})` : '';
                updateOrderStatus('waiting_trigger',
                    `Waiting for trigger...${priceInfo} (${triggerElapsed}/${triggerTimeout}s)`
                );

                if (triggerElapsed >= triggerTimeout) {
                    clearInterval(fillCheckInterval);
                    updateOrderStatus('timeout', `⚠️ Trigger timeout. Position remains open without trailing stop.`);
                }
            }
        } catch (e) {
            console.error('Monitoring error:', e);
            fillElapsed++; // Count errors toward timeout
        }
    }

    fillCheckInterval = setInterval(doMonitor, 1000);
}

function updateOrderStatus(state, message) {
    const statusContent = document.getElementById('order-status-content');

    const stateLabels = {
        'waiting_fill': '⏳ Waiting for Fill',
        'waiting_trigger': '📈 Waiting for Trigger',
        'complete': '✅ Complete',
        'timeout': '⚠️ Timeout',
        'error': '❌ Error'
    };

    const stateColors = {
        'waiting_fill': '#ffc107',
        'waiting_trigger': '#17a2b8',
        'complete': '#28a745',
        'timeout': '#dc3545',
        'error': '#dc3545'
    };

    statusContent.innerHTML = `
        <div class="bracket-status">
            <div class="bracket-state" style="color: ${stateColors[state] || '#666'}">
                ${stateLabels[state] || state}
            </div>
            <div class="bracket-message">${message}</div>
        </div>
    `;
}

function startTriggerMonitoring(orderId, config) {
    const triggerTimeout = config.trigger_timeout || 300;
    let triggerElapsed = 0;

    async function doMonitor() {
        try {
            const res = await fetch(`/api/exit-strategy/${orderId}/check-trigger`);
            const data = await res.json();

            if (data.triggered) {
                clearInterval(fillCheckInterval);
                // SSE will handle the update, but we can show immediately
                const stopInfo = data.stop_price
                    ? `@ ${formatCurrency(data.stop_price)}`
                    : `@ ${data.trail_amount} trail`;
                updateOrderStatus('complete', `✅ Trigger hit! Stop order placed ${stopInfo}`);
                loadOrders();
                loadPositions();
                delete pendingOrders[orderId];
                return;
            }

            triggerElapsed++;
            const priceInfo = data.current_price ? ` (${formatCurrency(data.current_price)} → ${formatCurrency(data.trigger_price)})` : '';
            updateOrderStatus('waiting_trigger',
                `Waiting for trigger...${priceInfo} (${triggerElapsed}/${triggerTimeout}s)`
            );

            if (triggerElapsed >= triggerTimeout) {
                clearInterval(fillCheckInterval);
                updateOrderStatus('timeout', `⚠️ Trigger timeout. Position remains open without stop.`);
                delete pendingOrders[orderId];
            }
        } catch (e) {
            console.error('Trigger monitoring error:', e);
        }
    }

    // Poll every second for trigger
    fillCheckInterval = setInterval(doMonitor, 1000);
}

// ==================== INITIALIZATION ====================

document.addEventListener('DOMContentLoaded', () => {
    loadTradingMode();  // Load current trading mode
    loadAccount();
    loadPositions();
    loadOrders();

    // Start SSE connection for real-time updates
    connectSSE();

    // Setup auto-streaming for quotes
    setupAutoStreaming();

    // Load ML signals
    refreshMLSignals();

    document.getElementById('order-side').addEventListener('change', updateSubmitButton);
    document.getElementById('profit-offset-type').addEventListener('change', updateProfitLabel);
    document.getElementById('profit-offset').addEventListener('input', updateProfitLabel);

    // Refresh every 30 seconds as backup (SSE handles real-time)
    setInterval(() => {
        loadAccount();
        loadPositions();
        loadOrders();
    }, 30000);

    // Refresh ML signals every 5 minutes
    setInterval(refreshMLSignals, 300000);

    // Enter key for quote
    document.getElementById('quote-symbol').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') getQuote();
    });
});

// ==================== ML TRADING FUNCTIONS ====================

let mlSignals = {};
let mlConfidence = 0.70;

function updateMLConfidence() {
    const slider = document.getElementById('ml-confidence');
    mlConfidence = slider.value / 100;
    document.getElementById('ml-confidence-value').textContent = slider.value + '%';
}

async function refreshMLSignals() {
    const signalsDiv = document.getElementById('ml-signals');
    signalsDiv.innerHTML = '<div class="ml-loading">Loading signals...</div>';

    try {
        const response = await fetch('/api/ml/signals?symbols=SOXL,NVDA,SPY,QQQ');
        const data = await response.json();

        if (data.signals) {
            mlSignals = data.signals;
            renderMLSignals(data.signals);
        } else {
            signalsDiv.innerHTML = '<div class="ml-error">Error loading signals</div>';
        }
    } catch (error) {
        console.error('Error fetching ML signals:', error);
        signalsDiv.innerHTML = '<div class="ml-error">Connection error</div>';
    }
}

function renderMLSignals(signals) {
    const signalsDiv = document.getElementById('ml-signals');
    let html = '';

    const symbolOrder = ['SOXL', 'NVDA', 'SPY', 'QQQ'];

    for (const symbol of symbolOrder) {
        const signal = signals[symbol];
        if (!signal) continue;

        const itemClass = signal.signal.toLowerCase();
        const confidencePct = (signal.confidence * 100).toFixed(1);
        const isActive = signal.confidence >= mlConfidence && signal.signal !== 'HOLD';
        const confidenceClass = signal.confidence >= 0.7 ? 'high' :
                               signal.confidence >= 0.5 ? 'medium' : 'low';

        html += `
            <div class="ml-signal-item ${itemClass}">
                <span class="ml-signal-symbol">${symbol}</span>
                <span class="ml-signal-action ${itemClass}">${signal.signal}</span>
                <span class="ml-signal-confidence ${confidenceClass}">${confidencePct}%</span>
            </div>
        `;
    }

    signalsDiv.innerHTML = html || '<div class="placeholder-text">No signals available</div>';
}

async function executeMLAutoTrade() {
    const confirmed = confirm(
        '⚡ ML SWING AUTO-TRADE\n\n' +
        'This will execute SWING TRADES (5-day horizon) for all symbols with confidence >= ' + (mlConfidence * 100).toFixed(0) + '%\n\n' +
        'Current signals:\n' +
        Object.entries(mlSignals).map(([s, d]) => `${s}: ${d.signal} (${(d.confidence * 100).toFixed(1)}%)`).join('\n') +
        '\n\nProceed with PAPER trading?'
    );

    if (!confirmed) return;

    const btn = event.target;
    btn.disabled = true;
    btn.textContent = '⏳ Trading...';

    try {
        const response = await fetch(
            `/api/ml/auto-trade?symbols=SOXL,NVDA,SPY,QQQ&min_confidence=${mlConfidence}`,
            { method: 'POST' }
        );
        const data = await response.json();

        if (data.success) {
            const ordersCount = data.orders.length;
            const signalsCount = Object.keys(data.signals).length;

            alert(
                `✅ Auto-Trade Complete\n\n` +
                `Signals analyzed: ${signalsCount}\n` +
                `Orders placed: ${ordersCount}\n` +
                (data.errors.length ? `Errors: ${data.errors.length}` : '')
            );

            // Refresh positions and orders
            loadPositions();
            loadOrders();
            loadAccount();
        } else {
            alert('❌ Auto-trade failed: ' + data.error);
        }
    } catch (error) {
        console.error('Auto-trade error:', error);
        alert('❌ Connection error during auto-trade');
    } finally {
        btn.disabled = false;
        btn.textContent = '⚡ Auto-Trade';
    }
}
