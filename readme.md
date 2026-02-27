<!--
Description: PAI-Lab README — Al Brooks Price Action Trading Engine
Date: 2026-02-27
Writer: J.Ekrami
Co-writer: Antigravity
Version: 8.0.0
-->

# 📘 PAI-Lab (Operational Intelligence Phase)

**Price Action Intelligence Laboratory (Version 8)**
*An adaptive, Multi-Timeframe (MTF) trading engine built on Al Brooks' price-action principles*

---

## Overview

PAI-Lab is a modular, multi-asset trading engine that translates Al Brooks' visual price-action methodology into executable, quantifiable code. The system operates on a **Multi-Timeframe architecture**, combining the 1H and 15M charts for macroscopic context, the 5M chart for primary structural signal detection (H1/H2, L1/L2, Breakouts, Wedge Reversals), and the 1M chart for precise Micro-Entry execution.

Version 8 completes the transition to **Operational Intelligence**. Rather than blind execution, PAI-Lab now routes all signals through a **Simulation Sandbox**, running a 1,000-iteration Monte Carlo LSB (Local Synthetic Backtest) against the current market regime. Trades are only committed to capital if they boast an Expected Value (EV) > 0.1R and a Probability of Profit (Pp) ≥ 35%.
| R:R | 1R (range scalp) → 2R (trend swing), scaled continuously by regime probability |
| Risk per trade | 1% normal / 0.3% in tough / shock conditions |
| Max Drawdown | −1.0 ATR (v5.0 hard-block filters prevent wide-stop losses) |

## Quick Start & Usage

### 1. Engine Core Pipeline (Historical Backtest & AI Training)
To analyze the engine's edge and train the AI on historical metrics, run the synchronized Multi-Timeframe engine:
```bash
python main.py --refresh --warmup 30000
```
- `--refresh`: Wipes the previous `state/` and generated `logs/` to force a clean slate.
- `--warmup N`: Defines the number of 1-minute bars strictly used to build market context before gating trades.
- Reads `btcusdt_1m.csv`, `btcusdt_5m.csv`, `btcusdt_15m.csv`, and `btcusdt_1h.csv`.

### 2. Live Paper Trading (Forward Testing)
To run the fully independent live paper trader connected to the Binance Live Feed via WebSockets/REST:
```bash
python live_runner.py
```
- Initiates an initial historical payload to warm up the 1M, 5M, 15M, and 1H contexts.
- Listens for 1-minute interval closures.
- Places simulated Limit Orders (Micro-Entries) scanning for optimal H2/L2 structures.
- Generates `logs/live_metrics.csv` and `logs/live_trades.csv` exactly as the real engine would.

---

## Breakthroughs in V6 - V8


### 1. Pressure Scoring Engine *(replaces 3 binary bar filters)*

Binary checks (`body_ratio > 0.4`, `close_pos > 0.65`, `body > 1.2×avg`) are gone. A 5-point composite **Pressure Score** must reach ≥ 3 for a bar to qualify as a signal bar:

| Component | Condition | Points |
|---|---|---|
| Extreme close position | `close_pos > 0.70` or `< 0.30` | +1 |
| Consecutive directional closes | ≥ 2 bars in same direction | +1 |
| Range expansion | Current bar range > 10-bar average | +1 |
| Low overlap with prior bar | Overlap ratio < 30% of range | +1 |
| Dominant tail rejection | Opposite-side tail > 30% of body | +1 |

This produces fewer, higher-conviction signals — exactly what Al Brooks means by "don't trade weak signal bars."

### 2. Volatility Shock Compression

| Condition | Action |
|---|---|
| `signal_bar_range > 2.0 × ATR` | **Trade blocked** — market is in shock, stop is uncontrollable |
| `signal_bar_range > 1.5 × ATR` | `risk = 0.3%`, target downshifted to Scalp Mode |
| `ATR_current > 2.0 × ATR_lookback_mean` | `risk = 0.3%` automatically |

### 3. Breakout State Machine *(was disconnected; now live)*

`BreakoutDetector` was detected but never piped into the main trading flow. v5.0 activates a full state machine:

```
breakout_detected AND pressure_score >= 3
    → breakout_state = ACTIVE
    → Next: pullback bar close in breakout direction → Breakout Pullback Entry
    → Next: bar reverses the close below breakout bar → Failed Breakout Entry
    → Timeout after 10 bars → state cleared
```

### 4. Major Trend Reversal (MTR) Protocol

A two-stage state machine blocks counter-trend entries until the reversal is structurally qualified:

```
Structural bias = "bullish" AND close < prior 20-bar low
    → mtr_state = TEST_EXTREME

mtr_state = TEST_EXTREME AND bar fails to make a new low
    → mtr_state = REVERSAL_ATTEMPT   ← counter-trend trades now allowed

Wedges, H2/L2 counter-trend, all gated on REVERSAL_ATTEMPT
```

### 5. Stop Efficiency Filter *(removed artificial stop cap)*

The old code silently moved the stop closer to entry if `stop_dist > 1.5 ATR`. This created fake R:R ratios. v5.0 removes the cap entirely:

- If `stop_dist > 1.5 × ATR` → **trade blocked** (the signal bar was too large)
- If `expected_rr < 1.0` → **trade blocked** (the math doesn't work)

> Al Brooks: *"Never move your stop to make the trade work. If the stop is too wide, don't take the trade."*

### 6. Equity Curve Risk Compression

| Trigger | Action |
|---|---|
| `loss_streak >= 3` | Risk → 0.3% |
| `drawdown >= 5%` from equity peak | Risk → 0.3% |
| `ATR_current > 2× ATR_lookback` | Risk → 0.3% |
| New equity high confirmed | `restore_risk()` — full risk restored |

### 7. Regime Probability Score *(replaces binary `env` string)*

Instead of: `if env == "trading_range": target = 1R else: target = 2R`

Now: `regime_probability` is a continuous float (0 = pure range, 1 = pure trend):

```
trend_score   = pressure_score + structure_score (HH/LL breaks)
range_score   = overlap_score + failed_breakout_score
regime_probability = trend_score / (trend_score + range_score)

target_distance = stop_dist × (1.0 + regime_probability × 1.0)
```

At `regime_probability = 0.5` → target = 1.5R. At `1.0` → 2R. At `0.0` → 1R.
Position size scales the same way — no cliff-edge behavior.

### 8. Pattern Failure Memory

The AI tracks win/loss history **per pattern type** (`h2`, `l2`, `wedge_reversal`, `breakout`, etc.):

- After **2 consecutive losses** on a pattern → confidence halved to 0.5×
- The AI probability is multiplied by the pattern confidence before threshold check
- Confidence slowly recovers (+10% per win) up to 100%

This automatically suppresses patterns that are performing poorly in the current market regime.

---

## Signal Detection Pipeline (v5.0)

```
Candle → Memory Buffer (100 bars)
         ↓
     TrendAnalyzer + PriceActionAnalyzer + MarketEnvironmentClassifier
         ↓
     [Block if TTR]
         ↓
     ► Pressure Score (NEW) — must be ≥ 3 to proceed
         ↓
     ► Regime Probability Score (NEW) — 0–1 float, drives targets + sizing
         ↓
     ► Volatility Shock Check (NEW) — hard block or force scalp
         ↓
     ► MTR State Machine (NEW) — gates counter-trend entries
         ↓
     MTR / Climactic Cooldown / Outside Bar Block
         ↓
     ► Breakout State Machine (NEW) — pullback + failure entries
         ↓
     SecondEntryDetector (H2/L2) → MTR Gate
     FirstEntryDetector  (H1/L1)
     WedgeDetector       → MTR Gate
     InsideBarDetector
         ↓
     [Pending Signal → Follow-Through Bar Confirmation]
         ↓
     Feature Extraction + Dynamic S/R Filters (HOD/LOD/PDH/PDL/Opening Range)
         ↓
     AI Probability Gate × Pattern Confidence (NEW)
         ↓
     Regime Guard + Risk Manager + Stop Efficiency Check (NEW)
         ↓
     Trade Execution
```

---

## Al Brooks Concepts Implemented

| Concept | Implementation |
|---|---|
| **H2/L2 (Second Entry)** | Explicit two-legged pullback detector |
| **H3 (Third Entry)** | Third pullback leg in channel trends |
| **H1/L1 (First Entry)** | Single-leg pullback (strong trends only) |
| **Wedge / 3-Push Reversal** | 3 pushes with decreasing momentum → MTR gated |
| **Inside Bar Setup** | Entry on break of mother bar |
| **Failed Breakout Fade** | Reversal on next bar after breakout |
| **Breakout Pullback Entry** *(v5.0)* | Pullback entry after confirmed breakout |
| **Micro Double Top/Bottom** | Two bars testing same extreme within 0.15 ATR |
| **Follow-Through Confirmation** | Pending signal cleared only on confirming bar |
| **Pressure Scoring** *(v5.0)* | 5-point composite replaces binary bar checks |
| **Climactic Exhaustion** | 3+ strong expanding bars → 5-bar cooldown |
| **Tight Trading Range** | 5+ overlapping doji bars block all signals |
| **Structural Trend** | Half-over-half HH/HL progression |
| **Always-In via Swing Pivots** | HH/HL or LL/LH progression (not slope) |
| **MTR Protocol** *(v5.0)* | Two-stage state machine for trend reversals |
| **Measured Move Targets** | Target = prior impulse distance |
| **Regime Probability Score** *(v5.0)* | Continuous 0–1 trend/range probability |
| **Prior Day H/L Filter** | Dynamic — strict in ranges, relaxed in trends |
| **HOD/LOD Proximity Filter** | Dynamic — adapts to structural trend strength |
| **Opening Range Filter** | Dynamic — strict in ranges, relaxed in trends |
| **Stop Efficiency Filter** *(v5.0)* | Block if stop > 1.5 ATR or RR < 1.0 |
| **Volatility Shock Compression** *(v5.0)* | Hard block or scalp mode on spike bars |
| **Outside Bar Block** | Block setup generation on outside bars |
| **Session Enforcement** | Trade only in configured session window |
| **London/NY Open Guard** | Suppress first 2 bars of every session |

---

## Trade Management

| Feature | Behavior |
|---|---|
| **Stop Placement** | Signal bar extreme — never moved artificially |
| **Stop Efficiency** *(v5.0)* | Block if native stop > 1.5 ATR |
| **Target** | Continuous: 1R (range) → 2R (trend) via regime probability |
| **Risk per trade** | 1% normal / 0.3% tough / shock / drawdown |
| **Equity Curve Compression** *(v5.0)* | Risk drops at 5% drawdown, restores at equity high |
| **Trailing Stop** | At 1R → breakeven. At 2R → trail 1R behind extreme |
| **Partial Exit** | 50% at 1R, 50% rides to full target |
| **Scratch Trade** | If < 0.3R after 3 bars → exit at breakeven |
| **Pattern Failure Memory** *(v5.0)* | Per-pattern confidence degrades after consecutive losses |
| **Tough Mode** | 0.3% risk on loss streaks, vol spikes, drawdown, suboptimal proximity |

---

## AI Layer

A logistic regression model retrained on a rolling window learns which setups produce winners in the current market regime.

**Warm-up Phase:** The `RollingController` requires historical trades to train. `PAILabEngine` runs a 40,000-candle live warmup block without enforcing RiskManager limits to accurately populate the AI brain before trading real capital.

**Pattern Failure Memory (v5.0):** The AI now tracks outcomes per signal type. Patterns with consecutive losses have their probability output scaled down before threshold comparison.

**ML Features (12):**
`depth_atr`, `pullback_bars`, `volatility_ratio`, `impulse_size_atr`, `breakout_strength`, `hour`, `dist_to_hod_atr`, `dist_to_lod_atr`, `gap_atr`, `impulse_size_raw`, `micro_double`, `is_third_entry`

---

## Multi-Asset Support

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

Each asset gets its own AI model state file (`state/engine_state_BTCUSDT.pkl`).

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
│   └── SwingPivotTracker        #   Always-In direction
├── engine/
│   └── core_engine.py           # Signal pipeline + Pressure Score + Breakout SM + MTR (v5.0)
├── core/
│   ├── feature_extractor.py     # 12 ML features
│   └── session_context.py       # Session open, first-hour range, prior day H/L
├── intelligence/
│   └── rolling_controller.py    # Logistic regression + pattern failure memory (v5.0)
├── execution/
│   ├── resolvers.py             # Stop efficiency filter + regime probability targets (v5.0)
│   ├── risk_manager.py          # Drawdown %, streak, vol shock, restore_risk (v5.0)
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

### Roll Back to Stable
```bash
git checkout v4.1.0
```

---

## Version History

| Version | Changes |
|---|---|
| **v5.0.0** | Capital security overhaul: Pressure Scoring Engine (5-point composite replaces 3 binary filters), Volatility Shock Compression (hard block + scalp force), Breakout State Machine activated, MTR Protocol (2-stage state machine gates counter-trend), Stop Efficiency Filter (hard block replaces artificial cap), Equity Curve Risk Compression (5% drawdown trigger + restore_risk), Regime Probability Score (continuous 0–1 float replaces binary env), Pattern Failure Memory (per-pattern confidence tracking) |
| **v4.1.0** | Dynamic context algorithms: Adaptive S/R limits based on structural trend, 1R targets in ranges (Scalp Mode), position risk penalty for suboptimal setups, 40,000-bar ML warmup phase (Cold Start fix) |
| **v4.0.0** | Brooks 100% compliance: PDH/L S/R, Opening Range filter, Swing Pivot Always-In, Inside Bar setup, Outside Bar block, Failed Breakout Fade, Micro Double Top/Bottom, H3 extension, session enforcement, London/NY open guard |
| **v3.0.0** | Risk management: 1.5R/2R targets, 1%/0.3% account risk, ATR-based stops, tough-condition detection, adaptive position sizing |
| **v2.1.0** | Follow-through confirmation, H1/L1, wedge reversals, trailing stops, partial exits, scratch trades |
| **v2.0.0** | Asset profiles, TTR detection, explicit H2/L2 counting, measured move targets, state segregation |
| **v1.0.0** | Core H2 detection, AI probability layer, backtest engine |

---

## Design Principles

- **No lookahead bias** — all signals are evaluated candle-by-candle
- **No replay stacking** — state manager prevents duplicate processing
- **Follow-through first** — never trade on the signal bar alone
- **Pressure before setup** — signal bar must prove directional intent
- **Context before mechanics** — structural environment must match setup direction
- **Never fake the stop** — if the geometry doesn't work, skip the trade
- **Capital survival** — risk management is independent of strategy logic
- **Modular isolation** — every component has a single responsibility

---

## Status

**PAI-Lab v5.0.0 — Capital-Safe Al Brooks Price Action Engine**

✅ ~86% Al Brooks strategy compliance (37/43 core concepts implemented)
✅ Pressure Scoring Engine — no more weak signal bars
✅ Breakout State Machine — ACTIVE → Pullback/Failure paths
✅ MTR Protocol — structured reversal confirmation required
✅ Stop Efficiency Filter — no artificial stop manipulation
✅ Equity Curve Risk Compression — 5% drawdown trigger
✅ Regime Probability Score — continuous trend/range scaling
✅ Pattern Failure Memory — per-pattern AI confidence
✅ Volatility Shock Compression — ATR spike protection
✅ Dynamic R:R scaling (1R ranges → 2R trends) via regime probability
✅ 40,000-bar AI warm-up phase eliminates cold-start problem
✅ Multi-asset ready (BTC + Gold)
✅ Persistent state + Gradio dashboard

---

*Writer: J.Ekrami | Co-writer: Antigravity*
