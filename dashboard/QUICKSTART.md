# 2026-02-17 | v1.0.0 | Quick Start Guide | Writer: J.Ekrami | Co-writer: Gemini 2.0 Flash Thinking
# PAI-Lab Dashboard - Quick Start

## 🚀 Launch Dashboard

```bash
cd d:\MyProjects\PAI-Lab
python dashboard/live_monitor.py
```

Open browser to: **http://localhost:7860**

## 📊 What You'll See

### On First Launch (No Trading Data Yet)
- Equity curve will show "No equity data available yet"
- Recent trades table will show "No trades yet"
- All status panels will show default/empty states

### With Live Data (After Running live_runner.py)
- **Equity Curve**: Blue line showing cumulative P&L in ATR units
- **Recent Trades**: Last 20 trades with green (bullish) / red (bearish) indicators
- **Current Position**: Shows OPEN position details or "No Position"
- **Regime Status**: GREEN (active) or RED (paused)
- **Risk Metrics**: Live performance statistics
- **System Health**: Time since last update

## 🔄 Features

- **Auto-Refresh**: Updates every 60 seconds automatically
- **Manual Refresh**: Click "🔄 Refresh Now" button
- **No Database Required**: Reads directly from CSV logs
- **Safe**: Read-only, won't affect trading

## 🎯 Typical Workflow

1. **Start Live Trading**:
   ```bash
   python live_runner.py
   ```

2. **Start Dashboard** (in separate terminal):
   ```bash
   python dashboard/live_monitor.py
   ```

3. **Monitor**: Open browser to http://localhost:7860

4. **Watch**: Dashboard updates automatically as trades execute

## 🛑 Stop Dashboard

Press `Ctrl+C` in the terminal where dashboard is running.

## 🌐 Remote Access

If running on a server, access from any browser:
```
http://YOUR_SERVER_IP:7860
```

Make sure port 7860 is open in your firewall.

## ❓ Troubleshooting

**"Port 7860 already in use"**
- Another instance is running
- Stop it with Ctrl+C or change port in `live_monitor.py`

**"No data available"**
- Normal if live_runner.py hasn't executed any trades yet
- Check that log files exist in `logs/` directory

**Dashboard not updating**
- Check that live_runner.py is still running
- Verify log files are being written
- Try manual refresh button

## 📝 Note

Dashboard reads from:
- `logs/live_metrics.csv`
- `logs/live_trades.csv`
- `logs/live_regime_events.csv`

If these files are empty, dashboard shows placeholder messages.
