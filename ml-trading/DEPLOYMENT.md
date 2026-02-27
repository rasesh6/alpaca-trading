# ML Trading System - Railway Deployment Guide

## Prerequisites
- IB Gateway service running on Railway
- GitHub repository connected to Railway

## Deployment Steps

### 1. Create New Service in Railway

1. Go to your Railway project (IB-gateway And IB-news-monitor)
2. Click **+ New Service**
3. Select **GitHub Repo**
4. Choose `alpaca-trading` repository
5. Select the `ml-trading` folder (or root if needed)

### 2. Configure Service

1. Railway will auto-detect the Dockerfile
2. Set the following **Variables**:

```
IB_GATEWAY_HOST=ib-gateway.railway.internal
IB_GATEWAY_PORT=4001
PORT=3000
```

3. The service will connect to IB Gateway via **private networking**

### 3. Deploy

1. Click **Deploy**
2. Wait for build to complete (~2-3 minutes)
3. Check logs for: `Starting ML Trading API on port 3000`

### 4. Set Public Domain (Optional)

1. Go to **Settings** → **Networking**
2. Add a public domain: `ml-trading.up.railway.app`
3. Port: 3000

## API Endpoints

Once deployed, the API will be available at:
- Local (Railway internal): `http://ml-trading.railway.internal:3000`
- Public (if enabled): `https://ml-trading.up.railway.app`

### Health Check
```
GET /health
```

### Train Model
```
POST /train/SOXL?days=365
```

### Get Signal
```
GET /signal/SOXL
```

### Get Quote (NBBO)
```
GET /quote/SOXL
```

### Run Backtest
```
POST /backtest/SOXL?days=365&capital=10000
```

### Full Pipeline
```
POST /full/SOXL?days=365
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    RAILWAY NETWORK                      │
│                                                         │
│  ┌─────────────────┐      ┌─────────────────────────┐  │
│  │   IB Gateway    │      │    ML Trading System    │  │
│  │  Port 4001      │◄────►│  Port 3000              │  │
│  │                 │      │                         │  │
│  │ ib-gateway.     │      │  /train, /signal,       │  │
│  │ railway.internal│      │  /quote, /backtest      │  │
│  └─────────────────┘      └─────────────────────────┘  │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

## Testing After Deployment

### From Another Railway Service
```bash
curl http://ml-trading.railway.internal:3000/health
curl http://ml-trading.railway.internal:3000/signal/SOXL
```

### From Public Internet (if public domain enabled)
```bash
curl https://ml-trading.up.railway.app/health
curl https://ml-trading.up.railway.app/signal/SOXL
```

## Troubleshooting

### Connection Refused to IB Gateway
- Verify IB Gateway is running: Check Railway logs
- Verify private networking: Use `ib-gateway.railway.internal`
- Check IB Gateway port: Should be 4001 (API port)

### Model Training Fails
- Check IB Gateway authentication
- Check logs for data fetch errors
- Verify yfinance fallback is working

### Timeout Errors
- Increase timeout in api_server.py
- Check IB Gateway CPU/memory usage
- Verify IB Gateway is not overloaded
