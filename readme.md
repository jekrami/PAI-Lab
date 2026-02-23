# 📘 PAI-Lab

**Price Action Intelligence Laboratory**
*Adaptive, State-Persistent Trading Engine*

---

## 1. Project Vision

PAI-Lab was built to explore whether structured Price Action concepts (inspired by Al Brooks methodology) can be transformed into a:

* Quantifiable
* Adaptive
* Survivable
* Production-ready trading engine

The goal is not a static backtest bot.

The goal is a modular intelligent system that:

* Learns from its own trades
* Detects when its edge deteriorates
* Protects capital automatically
* Survives restarts
* Can transition safely to live forward testing

---

## 2. Strategy Foundation

### Core Logic (Current Implementation)

* Market: **BTC 5m**
* Pattern: **High-2 Trend Resumption**
* Context: Structural Bull Trend (HH/HL confirmation)
* Entry: Stop entry above signal bar
* Target: 1 ATR
* Stop: 1.3 ATR
* Filters:

  * Pullback depth constraint
  * Structural trend confirmation
  * Volatility alignment

All signals are evaluated strictly candle-by-candle (no lookahead bias).

---

## 3. Evolution of the System

PAI-Lab evolved through several phases:

### Phase 1 — Raw Pattern Testing

* Basic H2 detection
* Static ATR stop/target
* Manual statistical slicing

Result:
Edge exists but unstable across regimes.

---

### Phase 2 — AI Augmentation

* Logistic regression classifier
* Feature engineering:

  * depth_atr
  * pullback_bars
  * volatility_ratio
  * impulse_size_atr
  * breakout_strength
  * hour
* Probability-based trade filtering
* Threshold optimization

Result:
Edge separation between A+ and B- setups.

---

### Phase 3 — Adaptive Learning

* Rolling training window
* Dynamic probability threshold adjustment
* Walk-forward validation

Result:
Stable out-of-sample performance.

---

### Phase 4 — Regime Intelligence

* Statistical RegimeGuard
* Z-score based performance degradation detection
* Separation of statistical weakness vs capital risk

Result:
System can pause when edge statistically vanishes.

---

### Phase 5 — Risk Management Layer

* Hard capital protection module
* Drawdown limits
* Loss streak control
* Volatility spike detection
* Final trade gatekeeper

Result:
Capital survivability independent of strategy logic.

---

### Phase 6 — Persistence & Continuity

* Full state persistence
* Model memory survives restart
* Chronological index resume
* Deterministic performance reconstruction

Result:
Engine survives reboot without replay corruption.

---

## 4. Current Architecture (v1.2)

| Layer              | Responsibility                              |
| ------------------ | ------------------------------------------- |
| Strategy           | Structural price action detection           |
| Feature Engine     | Quantitative feature extraction             |
| RollingController  | AI probability scoring & adaptive threshold |
| RegimeGuard        | Statistical edge decay detection            |
| RiskManager        | Hard capital protection                     |
| PerformanceMonitor | Deterministic metrics reconstruction        |
| TelemetryLogger    | Trade & regime logging                      |
| StateManager       | Long-term memory persistence                |
| Main Engine        | Sequential backtest execution               |
| Live Runner        | Independent live paper trading loop         |
| BinanceLiveFeed    | Historical + latest closed candle retrieval |
| PositionSizer      | Volatility-based fixed-fraction sizing      |

All modules are isolated and responsibility-driven.

This is intentional architectural discipline.

---

## 5. Current Performance (BTC 5m Historical Simulation)

Typical run:

* Trades: 131
* Expectancy: +0.17 ATR
* Winrate: ~64%
* Max Drawdown: -9.6 ATR
* Sharpe Proxy: ~0.15

After restart:

* Trade count remains stable
* Metrics reconstructed correctly
* No replay stacking

System integrity verified.

---

## 6. What We Have Achieved

We now have:

* Adaptive edge detection
* Statistical regime awareness
* Hard capital protection
* Persistent memory
* Chronological integrity
* Modular, production-ready structure

This is no longer a research script.
It is a trading engine framework.

---

## 7. What Is NOT Yet Implemented

* Multi-asset orchestration
* Real-money exchange execution adapter
* Advanced position sizing models (beyond basic fixed-fraction)
* Rich monitoring/analytics dashboard
* Deployment automation / containerization

---

## 8. Immediate Next Logical Steps

1. Run extended backtests via `python main.py` and inspect `PerformanceMonitor` metrics for different data slices.
2. Run live paper trading via `python live_runner.py` and monitor behavior under real-time Binance 5m candles.
3. Use `python tools/plot_performance.py` to visualize equity curve from persisted state.

---

## 9. Long-Term Roadmap

1. Live paper feed integration
2. Bearish symmetry implementation
3. Position sizing engine (volatility-scaled growth)
4. Multi-market support
5. Portfolio risk coordination
6. Live exchange execution
7. Monitoring dashboard
8. Deployment containerization

---

## 10. Core Design Principles

* No lookahead bias
* No replay stacking
* No hidden state
* No implicit resets
* All modules single responsibility
* Statistical protection separated from capital protection
* Deterministic reconstruction after restart

---

## 11. Monitoring & Observability

**Real-Time Dashboard (v1.3+)**

PAI-Lab now includes a web-based monitoring dashboard built with Gradio.

**Start Dashboard:**

```bash
python dashboard/live_monitor.py
```

Access at: `http://localhost:7860`

**Dashboard Features:**

* Live equity curve visualization
* Recent trades table (last 20 trades)
* Current position status
* Regime status indicator (active/paused)
* Risk metrics panel
* System health monitoring
* Auto-refresh every 60 seconds

**Use Case:**

Monitor live paper trading operations without watching terminal logs. Perfect for running `live_runner.py` on a remote server and checking status from any browser.

---

## 12. Status

**PAI-Lab v1.3 — Adaptive Engine with Monitoring Dashboard**

Stable
Persistent
Chronologically sound
Ready for forward validation
Operational visibility enabled

