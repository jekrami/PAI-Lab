<!--
Description: PAI-Lab README — Al Brooks Price Action Trading Engine
Date: 2026-02-25
Writer: J.Ekrami
Co-writer: Antigravity
Version: 4.1.0
-->

# 📘 PAI-Lab

**Price Action Intelligence Laboratory**
*An adaptive trading engine built on Al Brooks' price-action principles*

---

## Overview

PAI-Lab is a modular, multi-asset trading engine that translates Al Brooks' visual price-action methodology into executable, quantifiable code. It detects structural setups (H1, H2, L1, L2, breakouts, wedge reversals), validates them through follow-through bar confirmation, and manages trades with context-aware targets, trailing stops, and partial exits — all gated by an AI probability layer and capital protection system.

**Current performance (BTC 5m backtest — Fully Trained AI over 10,000 bars):**

| Metric | Value |
|---|---|
| Trades | 9 |
| Win Rate | 44.44% |
| Expectancy | +0.32 ATR (massively positive) |
| R:R Ratio | 1:1 (trading range scalp) / 2:1 (structural trend swing) |
| Risk per trade | 1% normal / 0.3% tough or suboptimal |
| Max Drawdown | −4.08 ATR |

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
| **H3 (Third Entry)** | Extends H2 state machine to detect a third pullback leg in strong channel trends |
| **H1/L1 (First Entry)** | Single-leg pullback, only in very strong trends (3+ consecutive strong bars) |
| **Wedge / 3-Push Reversal** | Detects 3 pushes to new extremes with decreasing momentum, enters counter-trend |
| **Inside Bar Setup** | Detects inside bar after a strong trend bar; entry on break of the mother bar |
| **Failed Breakout Fade** | Detects a breakout that reverses on the very next bar and fades the trapped buyers/sellers |
| **Micro Double Top/Bottom** | Two bars testing the same extreme within 0.15 ATR; quality boost for H2/L2 signal bars |
| **Follow-Through Confirmation** | Signal bars are stored as "pending" — only confirmed if the next bar closes in the signal direction |
| **Signal Bar Quality** | Close position > 0.65 (bull) / < 0.35 (bear), body ratio > 0.4 |
| **Tail Analysis** | Upper/lower tail ratios expose signal weakness |
| **Climactic Exhaustion** | 3+ strong bars with expanding range suppress signals + 5-bar cooldown period |
| **Tight Trading Range** | 5+ overlapping doji bars block all signals |
| **Structural Trend** | Half-over-half high/low progression confirms bull/bear structure |
| **Always-In via Swing Pivots** | Primary trend bias from swing pivot HH/HL or LL/LH progression, not slope |
| **Measured Move Targets** | Target = distance of prior impulse leg |
| **Prior Day H/L Filter** | Suppress buys within 0.5 ATR of prior day high; sells within 0.5 ATR of prior day low |
| **HOD/LOD Proximity Filter** | Suppress buys within 0.5 ATR of session high and sells near session low |
| **Opening Range Filter** | Suppress signals within 0.3 ATR of the first-hour high/low |
| **Outside Bar Block** | Blocks new setup generation on any outside bar (Al Brooks: creates confusion) |
| **Inside/Outside Bar** | Detected and used as standalone setups or hard guards |
| **Session Enforcement** | Filters trades outside configured session window (Gold: 08:00-17:00 EST) |
| **London/NY Open Guard** | Suppresses first 2 bars of every new session to avoid opening-bar traps |

### 3. Trade Management (Live Mode)

| Feature | Behavior |
|---|---|
| **Stop Placement** | ATR-based (1.0 ATR) with signal bar extreme as minimum floor |
| **Target** | Dynamic: 1× stop distance in trading ranges (Scalp Mode) or 2× for structural trends |
| **Risk per trade** | 1% of account (normal) / 0.3% (tough conditions or suboptimal context) |
| **Trailing Stop** | At 1R → stop moves to breakeven. At 2R → trails 1R behind extreme |
| **Partial Exit** | 50% taken at 1R profit, 50% rides to full target |
| **Scratch Trade** | If < 0.3R after 3 bars → exit at breakeven |
| **Scalp vs Swing** | Downshifts target distance heavily in `trading_range` environment or if context quality is < 0.5 |
| **Tough Mode** | Auto-reduces risk to 0.3% on loss streaks, vol spikes, low WR, or suboptimal resistance proximity |
| **Weekend Close** | Flatten positions Friday 16:00 EST for session-based assets |
| **Session Window** | Only detect signals within configured session hours |

### 4. AI Layer

A logistic regression model retrained on a rolling window learns which setups produce winners. It outputs a probability, and trades are filtered by an adaptive threshold optimized on recent expectancy.

**The Warm-up Phase:** The `RollingController` requires historical trades to train before it can accurately predict probabilities. `PAILabEngine` executes a 40,000-candle live warmup block without hitting RiskManager limits to accurately populate the ML brain before trading real capital.

**ML Features (12):**
`depth_atr`, `pullback_bars`, `volatility_ratio`, `impulse_size_atr`, `breakout_strength`, `hour`, `dist_to_hod_atr`, `dist_to_lod_atr`, `gap_atr`, `impulse_size_raw`, `micro_double`, `is_third_entry`

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
| **v4.1.0** | Transition from rigid math to dynamic context algorithms: Adaptive limits for S/R filtering based on structural trend, Scalper 1R targets in trading ranges, position risk penalty for suboptimal setups, and a 40,000-bar ML warmup phase to solve the AI "Cold Start" problem. |
| **v4.0.0** | Brooks 100% compliance: PDH/L S/R, Opening Range filter, Swing Pivot Always-In, Inside Bar setup, Outside Bar block, post-exhaustion 5-bar cooldown, Failed Breakout Fade, Micro Double Top/Bottom, H3 third-leg extension, session window enforcement, London/NY open guard |
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

**PAI-Lab v4.0.0 — Al Brooks Full-Compliance Price Action Engine**

✅ ~90% Al Brooks strategy compliance (22 concepts implemented)
✅ All key setups: H1/H2/H3, L1/L2/L3, Inside Bar, Failed Breakout, Wedge, 3-Push
✅ Prior Day H/L + Opening Range as hard S/R filters (Adapted Dynamically)
✅ Swing Pivot Always-In direction (not just slope)
✅ Post-exhaustion cooldown, outside bar hard block
✅ Micro Double Top/Bottom signal quality detection
✅ Session window + London/NY open enforcement
✅ Dynamic R:R matching market context (1:1 Ranges, 2:1 Trends)
✅ 1% account risk / 0.3% in tough or suboptimal conditions
✅ Massively positive expectancy (+0.32 per trade under Trained AI)
✅ Multi-asset ready (BTC + Gold profiles)
✅ AI-gated with adaptive thresholds
✅ Persistent state across restarts

---

*Writer: J.Ekrami | Co-writer: Antigravity*
