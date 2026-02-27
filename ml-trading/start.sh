#!/bin/bash
# ML Trading System - Railway Start Script

set -e

echo "=========================================="
echo "ML Trading System - Starting"
echo "=========================================="
echo "IB Gateway: ${IB_GATEWAY_HOST}:${IB_GATEWAY_PORT}"
echo "Port: ${PORT:-3000}"
echo "=========================================="

# Wait for IB Gateway to be ready
echo "Waiting for IB Gateway..."
sleep 10

# Start the API server
echo "Starting API server..."
exec python api_server.py
