# PAI-Lab Live Monitor Dashboard

Real-time monitoring dashboard for PAI-Lab paper trading operations.

## Features

- **Live Equity Curve** - Track your paper trading equity in real-time
- **Recent Trades Table** - View last 20 trades with outcomes
- **Current Position Status** - Monitor active positions
- **Regime Status Indicator** - Know when RegimeGuard pauses trading
- **Risk Metrics Panel** - Current equity, expectancy, winrate, etc.
- **System Health** - Last update time and system status
- **Auto-Refresh** - Updates every 60 seconds automatically

## Installation

The dashboard requires Gradio and Plotly:

```bash
pip install gradio plotly
```

## Usage

### Start the Dashboard

```bash
python dashboard/live_monitor.py
```

The dashboard will be available at: `http://localhost:7860`

### Access from Remote Machine

If running on a remote server, access via:

```
http://YOUR_SERVER_IP:7860
```

Make sure port 7860 is open in your firewall.

## Dashboard Layout

### Top Section
- **Refresh Button** - Manual refresh trigger
- **Last Updated** - Timestamp of last dashboard update

### Main Panels

#### Left Side (2/3 width)
- **Equity Curve** - Interactive Plotly chart showing cumulative returns
- **Recent Trades Table** - Last 20 trades with color-coded outcomes

#### Right Side (1/3 width)
- **Current Position** - Active position details (if any)
- **Regime Status** - RegimeGuard state (active/paused)
- **Risk Metrics** - Key performance metrics
- **System Health** - Live trading engine status

## Data Sources

The dashboard reads from:
- `logs/live_metrics.csv` - Metrics logged by TelemetryLogger
- `logs/live_trades.csv` - Trade history
- `logs/live_regime_events.csv` - Regime state changes

## Color Coding

- 🟢 **Green** - Bullish trades, active status, wins
- 🔴 **Red** - Bearish trades, paused status, losses
- 🟡 **Yellow** - Warning states, delayed updates
- ⚪ **White** - Neutral states

## Troubleshooting

### Dashboard shows "No data available"
- Ensure `live_runner.py` is running and has executed at least one trade
- Check that log files exist in `logs/` directory

### Dashboard not refreshing
- Check browser console for errors
- Restart the dashboard with `Ctrl+C` and re-run

### Port 7860 already in use
- Change port in `live_monitor.py`: `demo.launch(server_port=7861)`

## Notes

- Dashboard is read-only and does not affect trading operations
- Safe to run concurrently with `live_runner.py`
- Auto-refresh can be disabled by removing `every=60` parameter
- Uses minimal resources (refreshes data, not entire page)
