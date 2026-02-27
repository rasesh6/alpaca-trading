# Alpaca Trading System with ML
FROM python:3.11-slim

# Install system dependencies for XGBoost/LightGBM
RUN apt-get update && apt-get install -y \
    libgomp1 \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/ || exit 1

# Start the application
CMD ["gunicorn", "server:app", "--bind", "0.0.0.0:8080"]
