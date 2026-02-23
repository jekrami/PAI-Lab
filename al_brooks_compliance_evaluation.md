<!--
Description: Al Brooks Price Action Strategy — Full Compliance Evaluation
Date: 2026-02-24
Writer: J.Ekrami
Co-writer: Antigravity
Version: 3.0.0
-->

# Al Brooks Price Action — Full Compliance Evaluation

**Codebase audited:** PAI-Lab (all source files, v3.0.0)
**Date:** 2026-02-24
**Overall Grade:** A− (upgraded from B− after v2.1.0 and v3.0.0 risk management updates)

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
| 1.1 | **Always-In Direction** | ⚠️ | Captures trend bias via linear regression rather than recent strong signal bars. |
| 1.2 | **Structural Trend (HH/HL or LH/LL)** | ✅ | Correctly checks structural progression to align setups (bull H2 in bull trend). |
| 1.3 | **Tight Trading Range (TTR) Detection** | ✅ | Blocks all signals in TTRs (≥5/7 overlapping small-body bars). Matches Brooks exactly. |
| 1.4 | **Broad Trading Range Detection** | ⚠️ | Fallback to `"trading_range"`; does not differentiate a broad tradable TR from simple indecision. |
| 1.5 | **Breakout Detection** | ⚠️ | Exists but currently unused in the main signal pipeline. |
| 1.6 | **High/Low of Day Context** | ✅ | Buy signals near session high and sell signals near session low are actively blocked. |
| 1.7 | **Opening Gap Analysis** | ⚠️ | Used by the AI model to learn probabilities, but not an explicit manual rule. |
| 1.8 | **First Hour / Opening Range** | ❌ | No explicit support/resistance mapping of the first hour range. |
| 1.9 | **Prior Day High/Low as S/R** | ❌ | Prior day's range is a key Brooks reference but is not modeled as hard price levels. |
| 1.10| **Volatility Regime** | ✅ | Classifies volatility to assist adaptive sizing and risk management (tough mode). |

---

## 2 · Signal Bars & Entry Bars

| # | Al Brooks Concept | Status | Notes |
|---|---|---|---|
| 2.1 | **Signal Bar Quality** | ✅ | Brooks requires signal bars closing near their extremes (`close_pos > 0.65` bull / `< 0.35` bear). |
| 2.2 | **Signal Bar Body Ratio** | ✅ | Enforces a meaningful body (`body_ratio > 0.4`), rejecting dojis. |
| 2.3 | **Stop Entry Above/Below Bar** | ✅ | Enters exactly on break of the signal bar (high for long, low for short). |
| 2.4 | **Trend Bar vs Doji Classification** | ⚠️ | Somewhat mechanical (`body > 1.2 × avg_body`) vs Brooks' highly contextual reading. |
| 2.5 | **Climactic Exhaustion Detection** | ⚠️ | Computed but not heavily weighted in the hard rules blocking trades. |
| 2.6 | **Follow-Through Bar Assessment** | ✅ | Waits for the next bar to close in the setup direction before confirming the trade. |
| 2.7 | **Outside Bar / Inside Bar Logic** | ⚠️ | Detected (ii, io patterns) but not used as standalone discrete trade setups. |
| 2.8 | **Bar Counting** | ⚠️ | Sequence counting is used mostly for ML features rather than pure price action counting. |

---

## 3 · Setups (H1/H2/L1/L2 and Others)

| # | Al Brooks Concept | Status | Notes |
|---|---|---|---|
| 3.1 | **H2 Setup (2-legged pullback)** | ✅ | Explicitly traces Bounce → Leg 1 → Impulse backward visually. |
| 3.2 | **L2 Setup (2-legged pullback)** | ✅ | Correctly models downward two-legged pullbacks. |
| 3.3 | **H1 / L1 (First pullback)** | ✅ | Only activates in very strong trends (consecutive sequence ≥ 3). |
| 3.4 | **H3 / H4** | ❌ | Not modeled. Al Brooks relies on these in strong trends for trap setups. |
| 3.5 | **Wedge / 3-Push Reversal** | ✅ | Detects 3 pushes to new extremes with decreasing momentum. |
| 3.6 | **Micro Double Bottom / Top** | ❌ | Common Brooks pullback pattern; not parsed. |
| 3.7 | **Failed Breakout Setup** | ❌ | Fading breakouts at support/resistance is missing. |
| 3.8 | **Pullback Depth Filter** | ✅ | Requires pullbacks to be deep enough to qualify as legs. |
| 3.9 | **Pullback Duration Filter** | ✅ | Matches Brooks' 2-5 bar normal pullback duration. |

---

## 4 · Trade Management (Targets, Stops, Scaling)

| # | Al Brooks Concept | Status | Notes |
|---|---|---|---|
| 4.1 | **Measured Move Targets** | ✅ | If impulse > 1.5R, target uses measured move of prior leg. |
| 4.2 | **Signal-Bar Extreme Stops** | ✅ | Uses signal bar extreme as the absolute floor for stop placement, honoring structural risk. |
| 4.3 | **Scalp vs Swing Decision** | ✅ | Context dynamically shifts target: defaults to scalp (1.5R) but extends to swing (up to 2R) for measured moves. |
| 4.4 | **Partial Profit / Scaling Out** | ✅ | Takes 50% off at 1R profit, lets remainder ride to full target in Live Mode. |
| 4.5 | **Trailing Stop Logic** | ✅ | Moves to breakeven at 1R out, trails 1R behind extreme at 2R out. |
| 4.6 | **Scratch Trade (Breakeven Exit)** | ✅ | If < 0.3R profit after 3 bars, scratches at breakeven. Al Brooks key rule: exit if no strong follow-through. |
| 4.7 | **Weekend/Session Close** | ⚠️ | Config flags exist but live enforcement requires an active runner cron schedule. |

---

## 5 · Risk & Capital Management

| # | Al Brooks Concept | Status | Notes |
|---|---|---|---|
| 5.1 | **Fixed Risk per Trade** | ✅ | Positions scale to the stop distance, never exceeding 1% account risk. |
| 5.2 | **Reduce Risk in Tough Markets** | ✅ | Auto-scales down to 0.3% risk "when unsure or in trading ranges," explicitly modeling Brooks' risk advice. |
| 5.3 | **Daily/Session Loss Limit** | ✅ | Built-in circuit breakers to stop trading if behavior diverges. |
| 5.4 | **Loss Streak Protection** | ✅ | Enforces stepping aside after bad streaks. |
| 5.5 | **Reward-to-Risk ≥ 1.5** | ✅ | Strictly enforces mathematically positive R:R, capping stops and scaling targets natively. |
| 5.6 | **AI Probability Gating** | ⚠️ | Not a Brooks concept, but acts as a stand-in for his discretionary intuition/experience filtering. |

---

## 6 · Multi-Asset Readiness

| # | Concept | Status | Notes |
|---|---|---|---|
| 6.1 | **Asset Profiles** | ✅ | Profiles for BTC and Gold are independent. |
| 6.2 | **Session-Aware Trading** | ✅ | Now filters out non-session trades for instruments like Gold explicitly via configuration. |
| 6.3 | **London / NY Open Awareness**| ❌ | Time-of-day feature exists for AI, but explicit opening pivots are not mapped mechanically. |

---

## Summary Scorecard

| Category | Items | ✅ Full | ⚠️ Partial | ❌ Missing |
|---|---|---|---|---|
| **Market Context** (1.x) | 10 | 4 | 4 | 2 |
| **Signal / Entry Bars** (2.x) | 8 | 4 | 4 | 0 |
| **Setups** (3.x) | 9 | 6 | 0 | 3 |
| **Trade Management** (4.x) | 7 | 6 | 1 | 0 |
| **Risk & Capital** (5.x) | 6 | 5 | 1 | 0 |
| **Multi-Asset** (6.x) | 3 | 2 | 0 | 1 |
| **TOTAL** | **43** | **27 (63%)** | **10 (23%)** | **6 (14%)** |

---

## Conclusion & Gaps

The engine has highly accurate mechanics for entries and capital preservation. Specifically, the v3.0.0 update fundamentally closed the gap on Al Brooks' Trade Management and Risk mandates (Signal-bar stops, dynamic 1.5R/2R targets, 1% positional risk scaling, and Tough Mode size reduction). 

**The biggest remaining gap: Geometric Support/Resistance Context.**
The engine is highly structural/momentum-based but is "blind" to horizontal price levels (Prior Day High/Low, opening range outlines, and major prior swing extremes mapped forward). Brooks uses these precise levels to filter H2/L2 trades or convert them into fading setups (Failed Breakouts). The AI partially compensates, but manual integration of hard support/resistance filters would elevate the strategy to Full Compliance.
