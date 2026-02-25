<!--
Description: Al Brooks Price Action Strategy — Full Compliance Evaluation
Date: 2026-02-25
Writer: J.Ekrami
Co-writer: Antigravity
Version: 5.0.0
-->

# Al Brooks Price Action — Full Compliance Evaluation

**Codebase audited:** PAI-Lab (all source files, v5.0.0)
**Date:** 2026-02-25
**Overall Grade:** A+ (upgraded from previous versions due to v5.0 Capital Security & Protocol state machines)

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

| # | Al Brooks Concept | Status | Notes |
|---|---|---|---|
| 1.1 | **Always-In Direction** | ✅ | Captures trend bias via structural Swing Pivots (HH/HL or LL/LH progression). |
| 1.2 | **Structural Trend (HH/HL or LH/LL)** | ✅ | Correctly checks structural progression to align setups (bull H2 in bull trend). |
| 1.3 | **Tight Trading Range (TTR) Detection** | ✅ | Blocks all signals in TTRs (≥5/7 overlapping small-body bars). Matches Brooks exactly. |
| 1.4 | **Broad Trading Range Detection** | ✅ | Detects explicit `trading_range` environment. v5.0 replaces binary logic with a continuous 0–1 `regime_probability` score. |
| 1.5 | **Breakout Detection** | ✅ | v5.0 activates a full Breakout State Machine (ACTIVE → Pullback Entry or Failure Fade). |
| 1.6 | **High/Low of Day Context** | ✅ | Adapts dynamically. Rejects buys at HOD in ranges, but permits them near resistance in strong structural trends. |
| 1.7 | **Opening Gap Analysis** | ⚠️ | Used by the AI model to learn probabilities, but not an explicit manual rule. |
| 1.8 | **First Hour / Opening Range** | ✅ | Proximity filter relaxes in strong trends but strictly enforces a 0.5 ATR bounce filter in ranges. |
| 1.9 | **Prior Day High/Low as S/R** | ✅ | Shifts completely dynamically based on trend vs range classification, mirroring Brooks' "context over rules" approach. |
| 1.10| **Volatility Regime** | ✅ | v5.0 introduces Volatility Shock Compression: hard-blocks trades on >2× ATR spikes and auto-scalps >1.5× ATR spikes. |
| 1.11| **Major Trend Reversals (MTR)** | ✅ | v5.0 Protocol enforces a two-stage state machine (`TEST_EXTREME` → `REVERSAL_ATTEMPT`) preventing premature counter-trend entries. |

---

## 2 · Signal Bars & Entry Bars

| # | Al Brooks Concept | Status | Notes |
|---|---|---|---|
| 2.1 | **Signal Bar Quality (Pressure)** | ✅ | v5.0 replaces basic math with a 5-point Pressure Score (close pos, overlap, sequence, range, tail rejection). Must score ≥ 3 to qualify. |
| 2.2 | **Signal Bar Body Ratio** | ✅ | Handled dynamically within the new Pressure Score. |
| 2.3 | **Stop Entry Above/Below Bar** | ✅ | Enters exactly on break of the signal bar (high for long, low for short). |
| 2.4 | **Trend Bar vs Doji Classification** | ✅ | v5.0 composite scoring captures the nuance of trend conviction better than the old strict mathematical ratio. |
| 2.5 | **Climactic Exhaustion Detection** | ✅ | Implemented a strict 5-bar cooldown trading block after climactic exhaustion. |
| 2.6 | **Follow-Through Bar Assessment** | ✅ | Waits for the next bar to close in the setup direction before confirming the trade. |
| 2.7 | **Outside Bar / Inside Bar Logic** | ✅ | Inside bars are standalone discrete setups; Outside bars act as hard blocks. |
| 2.8 | **Bar Counting** | ⚠️ | Sequence counting is used mostly for ML features rather than pure price action counting. |

---

## 3 · Setups (H1/H2/L1/L2 and Others)

| # | Al Brooks Concept | Status | Notes |
|---|---|---|---|
| 3.1 | **H2 Setup (2-legged pullback)** | ✅ | Explicitly traces Bounce → Leg 1 → Impulse backward visually. |
| 3.2 | **L2 Setup (2-legged pullback)** | ✅ | Correctly models downward two-legged pullbacks. |
| 3.3 | **H1 / L1 (First pullback)** | ✅ | Only activates in very strong trends (consecutive sequence ≥ 3). |
| 3.4 | **H3 / H4** | ✅ | H3 third-leg extension explicitly modeled in strong trends. |
| 3.5 | **Wedge / 3-Push Reversal** | ✅ | Detects 3 pushes to new extremes. v5.0 now securely gates this behind the MTR Protocol. |
| 3.6 | **Micro Double Bottom / Top** | ✅ | Two bars testing the same extreme within 0.15 ATR are detected and act as quality boosts. |
| 3.7 | **Failed Breakout Setup** | ✅ | Explicit state machine detects breakout failure and fades trapped buyers/sellers. |
| 3.8 | **Breakout Pullback Setup** | ✅ | v5.0 introduces explicit tracking for pullbacks following a confirmed breakout. |
| 3.9 | **Pullback Depth Filter** | ✅ | Requires pullbacks to be deep enough to qualify as legs. |
| 3.10| **Pullback Duration Filter** | ✅ | Matches Brooks' 2-5 bar normal pullback duration. |

---

## 4 · Trade Management (Targets, Stops, Scaling)

| # | Al Brooks Concept | Status | Notes |
|---|---|---|---|
| 4.1 | **Measured Move Targets** | ✅ | If impulse > 1R in a trend, target uses measured move of prior leg length. |
| 4.2 | **Signal-Bar Extreme Stops** | ✅ | Uses signal bar extreme as the absolute floor for stop placement, honoring structural risk. |
| 4.3 | **Stop Efficiency / Never Fake It** | ✅ | v5.0 strictly drops trades if the required stop > 1.5 ATR. Replaced the old "artificial cap" logic. |
| 4.4 | **Scalp vs Swing Decision** | ✅ | Target distance scales continuously from 1R to 2R+ via the new 0–1 `regime_probability` score. |
| 4.5 | **Partial Profit / Scaling Out** | ✅ | Takes 50% off at 1R profit, lets remainder ride to full target in Live Mode. |
| 4.6 | **Trailing Stop Logic** | ✅ | Moves to breakeven at 1R out, trails 1R behind extreme at 2R out. |
| 4.7 | **Scratch Trade (Breakeven Exit)** | ✅ | If < 0.3R profit after 3 bars, scratches at breakeven. Al Brooks key rule: exit if no strong follow-through. |
| 4.8 | **Weekend/Session Close** | ⚠️ | Config flags exist but live enforcement requires an active runner cron schedule. |

---

## 5 · Risk & Capital Management

| # | Al Brooks Concept | Status | Notes |
|---|---|---|---|
| 5.1 | **Fixed Risk per Trade** | ✅ | Positions scale to the stop distance, never exceeding 1% account risk. |
| 5.2 | **Reduce Risk in Tough Markets** | ✅ | v5.0 Equity Curve Risk Compression auto-scales to 0.3% risk on 5% drawdown or 3x loss streak. |
| 5.3 | **Daily/Session Loss Limit** | ✅ | Built-in circuit breakers to stop trading if behavior diverges. |
| 5.4 | **Pattern Failure Memory** | ✅ | v5.0 tracks win/loss per pattern (e.g. `h2`, `wedge`). Confidence halves after 2 consecutive losses. |
| 5.5 | **Reward-to-Risk ≥ 1.0 (Minimum)** | ✅ | v5.0 strictly enforces mathematically positive R:R (`expected_rr < 1.0` blocks the trade). |
| 5.6 | **AI Probability Gating** | ⚠️ | Not a Brooks concept natively, but serves as the necessary stand-in for his "discretionary screen time" intuition block. |

---

## 6 · Multi-Asset Readiness

| # | Concept | Status | Notes |
|---|---|---|---|
| 6.1 | **Asset Profiles** | ✅ | Profiles for BTC and Gold are independent. |
| 6.2 | **Session-Aware Trading** | ✅ | Now filters out non-session trades for instruments like Gold explicitly via configuration. |
| 6.3 | **London / NY Open Awareness**| ✅ | Suppresses the first 2 bars of every new session day to avoid opening traps. |

---

## Summary Scorecard

| Category | Items | ✅ Full | ⚠️ Partial | ❌ Missing |
|---|---|---|---|---|
| **Market Context** (1.x) | 11 | 9 | 2 | 0 |
| **Signal / Entry Bars** (2.x) | 8 | 7 | 1 | 0 |
| **Setups** (3.x) | 10 | 10 | 0 | 0 |
| **Trade Management** (4.x) | 8 | 7 | 1 | 0 |
| **Risk & Capital** (5.x) | 6 | 5 | 1 | 0 |
| **Multi-Asset** (6.x) | 3 | 3 | 0 | 0 |
| **TOTAL** | **46** | **41 (89%)** | **5 (11%)** | **0 (0%)** |

---

## Conclusion & Gaps

The engine achieves an extraordinary level of compliance (~89%) with Al Brooks' price action principles. 

The prior v4 updates addressed Geometric Support/Resistance Context and Dynamic Context Adapting. The newest **v5.0.0 update** bridges the final gap on **Strict Capital Compliance & Protocol Enforcement**, specifically aligning with Al Brooks' teachings on:
1. **Never Faking the Stop:** If a setup requires too wide a stop, it is dropped entirely.
2. **Quality over Quantity:** The 5-point Pressure Score kills weak signal bars before they even reach the AI model.
3. **MTR Caution:** Counter-trend entries are hard-blocked unless a test of the extreme fails (`REVERSAL_ATTEMPT` state).

**Remaining Gaps (~11%):**
The final missing percentage comes down to Brooks' discretionary, multi-factor "feel" for the market (e.g., complex opening gap interpretations and fluidly adjusting bar counting in real-time). The AI Probability Gate bridges this gap by statically warming up on 40,000 candles of history—using regression and v5.0's Per-Pattern Confidence tracker to literally "learn" the market feel that Al Brooks developed over decades.
