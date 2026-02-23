<!--
Description: PAI-Lab README — Al Brooks Price Action Trading Engine
Date: 2026-02-23
Writer: J.Ekrami
Co-writer: Antigravity
Version: 3.0.0
-->

# 📘 PAI-Lab

**Price Action Intelligence Laboratory**
*An adaptive trading engine built on Al Brooks' price-action principles*

---

## Overview

PAI-Lab is a modular, multi-asset trading engine that translates Al Brooks' visual price-action methodology into executable, quantifiable code. It detects structural setups (H1, H2, L1, L2, breakouts, wedge reversals), validates them through follow-through bar confirmation, and manages trades with context-aware targets, trailing stops, and partial exits — all gated by an AI probability layer and capital protection system.

**Current performance (BTC 5m backtest — pre-AI bootstrap):**

| Metric | Value |
|---|---|
| Trades | 79 |
| Win Rate | 36.7% |
| Expectancy | −0.05 ATR |
| R:R Ratio | 1.5:1 (scalp) / 2:1 (swing) |
| Risk per trade | 1% normal / 0.3% tough |
| Max Drawdown | −15.1 ATR |

---

## How It Works

### 1. Signal Detection Pipeline

Every 5-minute candle passes through this pipeline:

```
Candle → Memory Buffer (100 bars)
         ↓
     TrendAnalyzer          → bull/bear/neutral bias
     PriceActionAnalyzer    → bar type, tails, overlap, climactic, inside/outside
     MarketEnvironmentClassifier → structural bull/bear/TTR/trading range
         ↓
     [Block if TTR or climactic exhaustion]
         ↓
     SecondEntryDetector    → H2/L2 explicit two-legged pullback
     FirstEntryDetector     → H1/L1 single-leg (strong trends only, sequence ≥ 3)
     WedgeDetector          → 3-push reversal with decreasing momentum
     BreakoutDetector       → breakout above/below recent range
         ↓
     [Pending Signal → wait for Follow-Through Bar]
         ↓
     Feature Extraction     → 10+ ML features
         ↓
     HOD/LOD Hard Filter    → block buys at session high, sells at session low
         ↓
     AI Probability Gate    → logistic regression with adaptive threshold
         ↓
     Regime & Risk Guards   → statistical and capital protection
         ↓
     Trade Execution
```

### 2. Al Brooks Concepts Implemented

| Concept | Implementation |
|---|---|
| **H2/L2 (Second Entry)** | Explicit two-legged pullback detector walks backward through Leg 2 → Bounce → Leg 1 → Impulse |
| **H1/L1 (First Entry)** | Single-leg pullback, only in very strong trends (3+ consecutive strong bars) |
| **Wedge / 3-Push Reversal** | Detects 3 pushes to new extremes with decreasing momentum, enters counter-trend |
| **Follow-Through Confirmation** | Signal bars are stored as "pending" — only confirmed if the next bar closes in the signal direction |
| **Signal Bar Quality** | Close position > 0.65 (bull) / < 0.35 (bear), body ratio > 0.4 |
| **Tail Analysis** | Upper/lower tail ratios expose signal weakness |
| **Climactic Exhaustion** | 3+ strong consecutive bars with expanding range suppress entries |
| **Tight Trading Range** | 5+ overlapping doji bars block all signals |
| **Structural Trend** | Half-over-half high/low progression confirms bull/bear structure |
| **Measured Move Targets** | Target = distance of prior impulse leg |
| **HOD/LOD Proximity Filter** | Suppress buys within 0.5 ATR of session high |
| **Inside/Outside Bar** | Detected and flagged in price action output |
| **Breakout Detection** | Range breakouts with strong bar quality act as fallback entries |

### 3. Trade Management (Live Mode)

| Feature | Behavior |
|---|---|
| **Stop Placement** | ATR-based (1.0 ATR) with signal bar extreme as minimum floor |
| **Target** | 1.5× stop distance (scalp) or 2× for measured move swings |
| **Risk per trade** | 1% of account (normal) / 0.3% (tough conditions) |
| **Trailing Stop** | At 1R → stop moves to breakeven. At 2R → trails 1R behind extreme |
| **Partial Exit** | 50% taken at 1R profit, 50% rides to full target |
| **Scratch Trade** | If < 0.3R after 3 bars → exit at breakeven |
| **Scalp vs Swing** | Context quality score: low → 1.5R scalp, high → 2R measured move |
| **Tough Mode** | Auto-reduces risk to 0.3% on loss streaks, vol spikes, low WR |
| **Weekend Close** | Flatten positions Friday 16:00 EST for session-based assets |
| **Session Window** | Only detect signals within configured session hours |

### 4. AI Layer

A logistic regression model retrained on a rolling window learns which setups produce winners. It outputs a probability, and trades are filtered by an adaptive threshold optimized on recent expectancy.

**ML Features (10):**
`depth_atr`, `pullback_bars`, `volatility_ratio`, `impulse_size_atr`, `breakout_strength`, `hour`, `dist_to_hod_atr`, `dist_to_lod_atr`, `gap_atr`, `impulse_size_raw`

---

## Multi-Asset Support

PAI-Lab is designed for multi-asset trading with per-asset configuration:

```python
ASSETS = {
    "BTCUSDT": {
        "session": "24/7",
        "target_mode": "measured_move",
        "close_before_weekend": False
    },
    "XAUUSD": {
        "session": "08:00-17:00_EST",
        "target_mode": "measured_move",
        "close_before_weekend": True
    }
}
```

Each asset gets its own AI model state file (`state/engine_state_BTCUSDT.pkl`), ensuring models trained on BTC never contaminate Gold signals.

---

## Architecture

```
PAI-Lab/
├── config.py                    # Global config + asset profiles
├── pai_engine.py                # Core price action analysis modules
│   ├── MarketMemory             #   Sliding candle buffer
│   ├── TrendAnalyzer            #   Slope + momentum direction
│   ├── PriceActionAnalyzer      #   Bar type, tails, overlap, climactic
│   ├── SecondEntryDetector      #   H2/L2 explicit leg counting
│   ├── FirstEntryDetector       #   H1/L1 single-leg setups
│   ├── WedgeDetector            #   3-push reversal pattern
│   ├── BreakoutDetector         #   Range breakout detection
│   ├── MarketEnvironmentClassifier  #  TTR / structural trend
│   └── VolatilityAnalyzer       #   ATR and volatility regime
├── engine/
│   └── core_engine.py           # Signal pipeline + follow-through + HOD/LOD filter
├── core/
│   ├── feature_extractor.py     # 10 ML features
│   └── session_context.py       # Session open, first-hour range, prior day H/L
├── intelligence/
│   └── rolling_controller.py    # Logistic regression + adaptive threshold
├── execution/
│   ├── resolvers.py             # Backtest + Live resolvers (trailing, scaling, scratch)
│   ├── risk_manager.py          # Drawdown, streak, volatility protection
│   ├── regime_guard.py          # Statistical edge decay detection
│   ├── position_sizer.py        # Fixed-fraction volatility sizing
│   ├── state_manager.py         # Per-asset state persistence
│   ├── performance_monitor.py   # Equity, returns, metrics
│   └── telemetry_logger.py      # Trade and regime event logging
├── data/
│   └── live_feed.py             # Binance candle retrieval
├── dashboard/
│   └── live_monitor.py          # Gradio web dashboard
├── main.py                      # Backtest runner
└── live_runner.py               # Live paper trading loop
```

---

## Quick Start

### Backtest
```bash
pip install -r requirements.txt
python main.py
```

### Live Paper Trading
```bash
python live_runner.py
```

### Dashboard
```bash
python dashboard/live_monitor.py
# Access at http://localhost:7860
```

---

## Version History

| Version | Changes |
|---|---|
| **v3.0.0** | Al Brooks risk management: 1.5R/2R targets, 1%/0.3% account risk, ATR-based stops, tough-condition detection, adaptive position sizing, correct directional entries |
| **v2.1.0** | Follow-through confirmation, H1/L1, wedge reversals, trailing stops, partial exits, scratch trades, session context, HOD/LOD filter, inside/outside bar detection |
| **v2.0.0** | Asset profiles, TTR detection, explicit H2/L2 two-legged counting, measured move targets, session features, state segregation |
| **v1.3.0** | Gradio monitoring dashboard, live BTC paper trading |
| **v1.2.0** | Regime guard, risk manager, state persistence, position sizing |
| **v1.0.0** | Core H2 detection, AI probability layer, backtest engine |

---

## Design Principles

- **No lookahead bias** — all signals are evaluated candle-by-candle
- **No replay stacking** — state manager prevents duplicate processing
- **Follow-through first** — never trade on the signal bar alone
- **Context before mechanics** — structural environment must match the setup direction
- **Capital survival** — risk management is independent of strategy logic
- **Modular isolation** — every component has a single responsibility

---

## Status

**PAI-Lab v3.0.0 — Al Brooks Risk-Managed Price Action Engine**

✅ 1.5:1 reward-to-risk (scalp) / 2:1 (swing)
✅ 1% account risk per trade, 0.3% in tough conditions
✅ Adaptive tough-condition detection (vol spike, loss streak, low WR)
✅ Multi-asset ready (BTC + Gold profiles configured)
✅ 6 setup types (H1, H2, L1, L2, breakout, wedge reversal)
✅ Context-aware trade management (trailing, scaling, scratch)
✅ Session-aware signal filtering
✅ AI-gated with adaptive thresholds
✅ Persistent state across restarts

---

*Writer: J.Ekrami | Co-writer: Antigravity*
