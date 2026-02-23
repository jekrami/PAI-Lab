<!--
Description: PAI-Lab — Live Test Run Guide
Date: 2026-02-23
Writer: J.Ekrami
Co-writer: Antigravity
Version: 2.1.0
-->

# PAI-Lab — Live Test Run Guide

## 1. Starting Live Paper Trading

```bash
cd /path/to/PAI-Lab
pip install -r requirements.txt
nohup python live_runner.py > output.log 2>&1 &
```

> Use `nohup` or `screen` so it survives SSH disconnects.
> Check it's running: `ps aux | grep live_runner`

---

## 2. Log & Report Locations

| Path | What's Inside |
|---|---|
| `logs/live_trades.csv` | Every trade: direction, entry/exit price, size, ATR, outcome, equity, probability, threshold |
| `logs/live_metrics.csv` | Per-trade snapshot: equity, rolling expectancy, winrate, volatility, adaptive threshold |
| `logs/live_regime_events.csv` | Regime state changes: pauses/resumes with z-scores |
| `state/engine_state_BTCUSDT.pkl` | Full AI state: model weights, feature history, equity, trade counter (survives restarts) |
| `output.log` | Raw console output (if using `nohup`) |

All CSV logs are **append-only** — watch in real time:
```bash
tail -f logs/live_trades.csv
```

---

## 3. Verifying AI Training

The AI trains itself after collecting **100 trades**. Before that, all valid setups are taken (pure price-action rules).

### Quick Checks

**Console / output.log:**
```
Current Adaptive Threshold: 0.65   ← default, not trained yet
Current Adaptive Threshold: 0.55   ← model trained and optimized
```

**CSV check:**
```bash
# See threshold changes over time
cut -d',' -f8 logs/live_metrics.csv | tail -20
```

**Python check:**
```python
import pickle
with open("state/engine_state_BTCUSDT.pkl", "rb") as f:
    state = pickle.load(f)
print(f"Trained: {state['trained']}")
print(f"Samples: {len(state['feature_history'])}")
print(f"Threshold: {state['current_threshold']}")
print(f"Total trades: {state['trade_counter']}")
```

---

## 4. What to Expect

| Timeframe | Behavior |
|---|---|
| **Day 1–2** | AI not trained yet — trades on pure Al Brooks rules. This is the bootstrap phase. |
| **After ~100 trades** | AI activates. Adaptive threshold shifts. Some setups get filtered. |
| **Ongoing** | Model retrains on last 100 trades, adapting to changing conditions. |

---

## 5. Dashboard (Optional)

```bash
python dashboard/live_monitor.py
# Access at http://your-server-ip:7860
```

Shows equity curve, recent trades, regime status, and risk metrics. Auto-refreshes every 60s.

---

## 6. Stopping & Resuming

**Stop:**
```bash
kill $(pgrep -f live_runner.py)
```

**Resume:** Just run `python live_runner.py` again — the `StateManager` loads the saved state from `state/engine_state_BTCUSDT.pkl` automatically. No data loss, no replay.

---

## 7. Next Steps (After Test Run)

- [ ] Review `logs/live_trades.csv` — check win/loss patterns
- [ ] Verify AI threshold adapted (should differ from 0.65)
- [ ] Review equity curve via dashboard or `tools/plot_performance.py`
- [ ] Proceed to real trading bot integration
