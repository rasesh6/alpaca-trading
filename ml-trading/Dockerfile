# ML Trading System - Railway Deployment
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install additional dependencies for Railway
RUN pip install --no-cache-dir \
    flask \
    flask-cors \
    waitress \
    gunicorn \
    ib_insync

# Copy application code
COPY . .

# Create directories for data and models
RUN mkdir -p /app/data /app/models

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PORT=3000
ENV IB_GATEWAY_HOST=ib-gateway.railway.internal
ENV IB_GATEWAY_PORT=4001

# Expose port
EXPOSE 3000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:3000/health || exit 1

# Start the API server
CMD ["python", "api_server.py"]
