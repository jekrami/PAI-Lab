<!--
Description: Al Brooks Price Action Strategy — Full Compliance Evaluation
Date: 2026-02-23
Writer: J.Ekrami
Co-writer: Antigravity
Version: 2.0.0
-->

# Al Brooks Price Action — Full Compliance Evaluation

**Codebase audited:** PAI-Lab (all 12 source files)
**Date:** 2026-02-23
**Overall Grade:** B− (upgraded from C+ after recent changes)

---

## Evaluation Method

Every concept from Al Brooks' three-book series (*Trading Price Action: Trends, Trading Ranges, Reversals*) was checked against the actual code. Each is classified as:

| Symbol | Meaning |
|--------|---------|
| ✅ | **Fully implemented** — logic matches Brooks' definition |
| ⚠️ | **Partially implemented** — skeleton exists but simplifies or misses nuance |
| ❌ | **Not implemented** — concept is absent from the codebase |

---

## 1 · Market Context (Brooks: "Read the chart first")

| # | Al Brooks Concept | Status | Code Evidence | Notes |
|---|---|---|---|---|
| 1.1 | **Always-In Direction** — is the market always-in long or always-in short? | ⚠️ | `TrendAnalyzer.analyze()` computes slope + bullish/bearish move ratio → outputs `direction` | Captures trend bias via linear regression. Brooks' always-in concept is more nuanced (based on the most recent strong signal bar, not a statistical average). |
| 1.2 | **Structural Trend (HH/HL or LH/LL)** | ✅ | `MarketEnvironmentClassifier.classify()` compares first-half vs second-half highs/lows | Correctly checks structural progression. Trades are only allowed in matching structural environments (bull H2 in bull trend, bear L2 in bear trend). |
| 1.3 | **Tight Trading Range (TTR) Detection** | ✅ | `MarketEnvironmentClassifier.classify()` — counts overlapping bars (≥5/7) with small bodies (avg_body < 0.5 × avg_range) | Returns `"tight_trading_range"` which blocks all signals. Correctly mirrors Brooks' rule: "Do not trade inside a TTR." |
| 1.4 | **Broad Trading Range Detection** | ⚠️ | Returns `"trading_range"` as fallback when neither bull nor bear structure is detected | Does not differentiate a broad TR from simple indecision. Brooks treats broad TRs (with tradable swings) differently from TTRs. |
| 1.5 | **Breakout Detection** | ⚠️ | `BreakoutDetector.detect()` checks if close breaks recent high/low with above-average range | Exists but is **never called** in the signal pipeline (`core_engine.py` does not invoke it). Dead code. |
| 1.6 | **High/Low of Day Context** | ⚠️ | `feature_extractor.py` calculates `dist_to_hod_atr` and `dist_to_lod_atr` | Computed as ML features (the AI model can learn to use them) but **not** used as hard filters. Brooks actively avoids certain setups near HOD/LOD. |
| 1.7 | **Opening Gap Analysis** | ⚠️ | `feature_extractor.py` calculates `gap_atr` (session open vs prior close) | Same as above — fed to ML, not used as a direct rule. Brooks classifies gaps as "measuring" or "exhaustion" and uses them for target selection. |
| 1.8 | **First Hour / Opening Range** | ❌ | — | Brooks heavily uses the first-hour range as support/resistance. No concept of "first hour" exists. |
| 1.9 | **Prior Day High/Low as S/R** | ❌ | — | Prior day's range is a key Brooks reference. Only gap is computed, not the prior day high/low as levels. |
| 1.10 | **Volatility Regime** | ✅ | `VolatilityAnalyzer.regime()` classifies as high/low/normal volatility | Exists and is correct, though Brooks doesn't use "regime" per se — he reads it from bar sizes directly. |

---

## 2 · Signal Bars & Entry Bars

| # | Al Brooks Concept | Status | Code Evidence | Notes |
|---|---|---|---|---|
| 2.1 | **Signal Bar Quality (close position)** | ✅ | `SecondEntryDetector.detect()` requires `close_pos > 0.65` (bull) or `< 0.35` (bear) | Brooks wants the signal bar to close near its extreme. Implemented correctly. |
| 2.2 | **Signal Bar Body Ratio** | ✅ | Requires `body_ratio > 0.4` | Brooks dislikes dojis as signal bars. This filter enforces a meaningful body. |
| 2.3 | **Stop Entry (enter above/below signal bar)** | ✅ | `entry_price = row["high"]` (backtest) / `candle["high"]` (live) | Correct — Brooks enters on a stop order one tick above the signal bar high for longs. |
| 2.4 | **Trend Bar vs Doji Classification** | ⚠️ | `PriceActionAnalyzer.trend_bar_info()` uses `body > 1.2 × avg_body` | Mechanical threshold. Brooks uses a more holistic reading: tail length, overlap with prior bars, and relative position. |
| 2.5 | **Climactic / Exhaustion Bar Detection** | ⚠️ | `PriceActionAnalyzer.trend_bar_info()` flags `climactic = True` if `sequence ≥ 3` and `range > 1.3 × avg_range` | The concept exists but is **never consumed** by the trading pipeline. Dead feature. |
| 2.6 | **Follow-Through Bar Assessment** | ❌ | — | Brooks judges a signal bar's reliability by the **next bar's** behavior. The system enters immediately without waiting for follow-through confirmation. |
| 2.7 | **Outside Bar / Inside Bar Logic** | ❌ | — | Brooks treats inside bars (ii) and outside bars as specific setups with distinct rules. Not detected. |
| 2.8 | **Bar Counting (consecutive same-direction bars)** | ⚠️ | `PriceActionAnalyzer` counts strong-bar sequences | Exists but only feeds the `climactic` flag, which itself is unused. |

---

## 3 · Setups (H1/H2/L1/L2 and Others)

| # | Al Brooks Concept | Status | Code Evidence | Notes |
|---|---|---|---|---|
| 3.1 | **H2 Setup (2nd push up after pullback in bull)** | ✅ | `SecondEntryDetector.detect()` with `bias="bullish"` walks backward through Leg 2 → Bounce H1 → Leg 1 → Impulse | Recently rewritten to explicitly trace two legs. Correctly mirrors the visual H2 pattern. |
| 3.2 | **L2 Setup (2nd push down after pullback in bear)** | ✅ | Same detector with `bias="bearish"` — symmetric logic for L2 | Correct symmetry for shorts. |
| 3.3 | **H1 / L1 (First pullback entry)** | ❌ | — | The detector **requires** two legs. An H1 (single-leg pullback) is never traded. Brooks considers H1s valid in strong trends. |
| 3.4 | **H3 / H4 (Third/Fourth pullback entries)** | ❌ | — | Only H2/L2 is supported. Brooks uses H3/H4 as increasingly reliable setups in strong trends. |
| 3.5 | **Wedge / 3-Push Reversal** | ❌ | — | Brooks' strongest reversal setup. No wedge detection logic exists. A wedge is three pushes to a new extreme with decreasing momentum. |
| 3.6 | **Micro Double Bottom / Top** | ❌ | — | Common Brooks pullback pattern (two bars testing the same low). Not implemented. |
| 3.7 | **Failed Breakout Setup** | ❌ | — | Brooks trades the failure of a breakout attempt (e.g., break above a range that reverses). Not present. |
| 3.8 | **Pullback Depth Filter** | ✅ | `core_engine.py` requires `pullback_depth / atr ≥ DEPTH_THRESHOLD_ATR` (1.0) | Ensures the pullback is "meaningful." Correct concept. |
| 3.9 | **Pullback Duration Filter** | ✅ | `core_engine.py` requires `PULLBACK_MIN (2) ≤ bars ≤ PULLBACK_MAX (4)` | Brooks wants 2-5 bar pullbacks typically. This matches. |

---

## 4 · Trade Management (Targets, Stops, Scaling)

| # | Al Brooks Concept | Status | Code Evidence | Notes |
|---|---|---|---|---|
| 4.1 | **Measured Move Targets** | ✅ | `resolvers.py` — if `target_mode == "measured_move"`, target = `impulse_size_raw` (prior leg length) | Correctly uses the prior leg's distance to project the target. This is a core Brooks principle. |
| 4.2 | **ATR-Based Fallback Stops** | ✅ | `ATR_STOP = 1.30` used for stop distance | A reasonable mechanical stop. Brooks prefers placing stops beyond the signal bar or the pullback extreme, which is more contextual. |
| 4.3 | **Scalp vs Swing Decision** | ❌ | — | Brooks adjusts risk-reward based on context quality: strong trends → swing (hold for measured move), weak context → scalp (quick 1:1). The system always uses the same target mode. |
| 4.4 | **Partial Profit / Scaling Out** | ❌ | — | Brooks recommends taking partial profits at the first target and trailing the rest. The system is all-in / all-out. |
| 4.5 | **Trailing Stop Logic** | ❌ | — | Brooks trails stops to breakeven after the first leg or to swing lows. Not implemented. |
| 4.6 | **Scratch Trade (Exit at Breakeven)** | ❌ | — | Brooks scratches trades that don't show immediate follow-through. Not present. |
| 4.7 | **Weekend/Session Close Protection** | ⚠️ | `config.py` has `close_before_weekend: True` for XAUUSD | Config flag exists but **no code checks or enforces it** in `resolvers.py` or `live_runner.py`. Dead config. |

---

## 5 · Risk & Capital Management

| # | Al Brooks Concept | Status | Code Evidence | Notes |
|---|---|---|---|---|
| 5.1 | **Fixed Fractional Risk per Trade** | ✅ | `PositionSizer.size()` — risks `risk_fraction (1%)` of equity per trade | Standard risk management. Brooks recommends 1-2% risk per trade. |
| 5.2 | **Daily Loss Limit** | ✅ | `RiskManager` enforces `max_daily_loss = -5` (ATR units) | Reasonable circuit breaker. |
| 5.3 | **Max Drawdown Hard Stop** | ✅ | `RiskManager` enforces `max_total_drawdown = -15` (ATR units) | Prevents catastrophic ruin. |
| 5.4 | **Loss Streak Protection** | ✅ | `RiskManager` triggers hard stop after `max_loss_streak = 5` | Brooks suggests stepping aside after consecutive losses. Implemented. |
| 5.5 | **Regime-Based Pause** | ✅ | `RegimeGuard` pauses trading when recent z-score < -1.0 vs baseline | Statistical quality gate — unique to this system. Not a Brooks concept per se, but compatible. |
| 5.6 | **AI Probability Gating** | ✅ | `RollingController` — logistic regression with adaptive threshold | Not a Brooks concept, but acts as a compensator for missing contextual rules. Learns which structures work. |
| 5.7 | **Asset-Specific State Segregation** | ✅ | `StateManager` saves to `engine_state_{asset_id}.pkl` | BTC model never contaminates Gold model. Correct architecture. |

---

## 6 · Multi-Asset Readiness

| # | Concept | Status | Evidence | Notes |
|---|---|---|---|---|
| 6.1 | **Asset Profiles** | ✅ | `config.py` → `ASSETS` dict with per-asset session, target_mode, etc. | Profiles exist for BTCUSDT and XAUUSD. |
| 6.2 | **Session-Aware Trading** | ⚠️ | Session config stored (`"08:00-17:00_EST"`) but **not enforced** in code | No logic checks current time against session window. Trades would still fire outside Gold's active hours. |
| 6.3 | **London / NY Open Awareness** | ❌ | — | Brooks (especially on ES/Gold) keys off institutional session opens. No concept of specific session opens. |

---

## Summary Scorecard

| Category | Items | ✅ Full | ⚠️ Partial | ❌ Missing |
|---|---|---|---|---|
| **Market Context** (1.x) | 10 | 3 | 5 | 2 |
| **Signal / Entry Bars** (2.x) | 8 | 3 | 3 | 2 |
| **Setups** (3.x) | 9 | 5 | 0 | 4 |
| **Trade Management** (4.x) | 7 | 2 | 1 | 4 |
| **Risk & Capital** (5.x) | 7 | 7 | 0 | 0 |
| **Multi-Asset** (6.x) | 3 | 1 | 1 | 1 |
| **TOTAL** | **44** | **21 (48%)** | **10 (23%)** | **13 (30%)** |

---

## Compliance Grade: B−

### What the system does well:
- **Core H2/L2 detection** with explicit two-legged pullback recognition — the foundational Brooks setup
- **Structural trend gating** — only trades in the direction of the higher-timeframe structure
- **TTR avoidance** — correctly blocks signals inside tight ranges
- **Measured Move targets** — dynamically sizes targets based on the prior impulse leg
- **Capital protection** — comprehensive risk management with daily limits, drawdown stops, and streak protection
- **AI shortcut** — the ML layer compensates for missing discretionary judgment by learning from outcomes

### What needs work:
- **Dead code** — `BreakoutDetector`, `climactic` flag, `close_before_weekend` config exist but are never consumed
- **Session enforcement** — asset profiles are defined but session-time logic is not enforced
- **No additional setups** — only H2/L2 is traded; H1, H3/H4, wedges, and failed breakouts are absent
- **No trade management nuance** — no trailing stops, no scaling, no scalp-vs-swing decision
- **No follow-through** — enters on the signal bar without waiting for the next bar's confirm

### Biggest gap vs Brooks:
Al Brooks' methodology is **deeply contextual** — the same H2 shape in different market contexts receives entirely different treatment. The code correctly identifies the mechanical structure of an H2, but treats all H2s equally. The AI layer partially compensates, but the discretionary dimension (e.g., "this H2 is at the HOD in a broad trading range late in the day, so skip it") cannot be fully captured without explicit rules.
