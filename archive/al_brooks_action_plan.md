<!--
Description: Comprehensive Al Brooks Strategy Compliance Evaluation and Multi-Asset Upgrade Plan
Date: 2026-02-23
Writer: J.Ekrami
Co-writer: Antigravity
Version: 1.1.0
-->

# PAI-Lab: Al Brooks Strategy Compliance & Multi-Asset Action Plan

This document provides a comprehensive evaluation of the current PAI-Lab trading engine against Al Brooks' Price Action principles and outlines the strategic roadmap for evolving the system. 

The primary goal of this evolution is to migrate from a rigid, BTC-only (24/7 volatile crypto) testing environment to a robust, context-aware system capable of trading traditional assets with distinct session behaviors, specifically **Gold (XAUUSD)**.

---

## Part 1: Compliance Evaluation (Current State: C+)

The current logic captures the **mechanical skeleton** of an Al Brooks H2/L2 trade (pullback in trend -> reversal bar -> enter above/below) but lacks deep discretionary context.

### ✅ Fully Implemented
- **H2 / L2 Setups**: Pullbacks are detected and trades are triggered on strong reversal signal bars (`SecondEntryDetector`).
- **Structural Trend Context**: Higher Highs / Higher Lows (for bull bias) and inverse for bear bias ensure trading with the trend (`MarketEnvironmentClassifier`).
- **Signal Bar Quality**: Requires a strong close (e.g., >0.7) and solid body ratio.
- **Stop Entry Mechanics**: Entries placed above the high / below the low of the signal candle.

### ⚠️ Partially Implemented / Mechanized
- **"Second" Entry Counting**: Counts consecutive pullback bars to define depth, completely missing the explicit tracking of the first failed attempt (H1/L1).
- **Trend Bar vs. Doji Distinction**: Uses a hard mathematical average math (`body > 1.2 × avg_body`) rather than contextual overlap or tail analysis. 
- **Pullback Quality**: Evaluated via fixed ATR depth and bar count, missing the visual "two-legged" structural requirement.

### ❌ Not Implemented (Critical Gaps)
- **Measured Move Targets**: Currently relies on fixed, rigid 1.0 ATR mathematically-derived targets.
- **Trading Range (TTR) Avoidance**: No detection logic to actively block trades when price tightens into a trading range.
- **Session-Aware Context**: Zero awareness of High of Day (HOD) / Low of Day (LOD), Opening Gaps, or specific asset session liquidity (e.g., NY Open).
- **Follow-Through / Always-In direction**: Lacks formal verification of the market's "always-in" state.

---

## Part 2: Mult-Asset Action Plan (Gold & BTC)

To achieve the best possible outcome based on Al Brooks’ methodology, the system must pivot from rigid math to flexible context. BTC is an excellent testing ground for raw logic due to its 24/7 volatility, but Gold brings institutional session timings, opening gaps, and cleaner measured moves.

### Phase 1: Contextual Intelligence Upgrades (`engine/pai_engine.py`)
1. **Explicit Leg Counting (H1/H2 vs just pullbacks)**
   - Rewrite `SecondEntryDetector` to identify the absolute swing high/low of the first pullback leg (H1), the subsequent minor trend push, and the second pullback (H2). 
2. **Tight Trading Range (TTR) Detection**
   - Implement bar overlap calculations in the `MarketEnvironmentClassifier`. If the last 5-10 bars overlap by more than 50% with shrinking bodies, classify as a TTR and disable H2/L2 entries.
3. **Session High/Low & Gap Context**
   - Introduce daily anchor points. For Gold, track the London and NY opens. For BTC, track the UTC daily open. Filter setups based on proximity to these major support/resistance levels.

### Phase 2: Dynamic Execution (`execution/resolvers.py` & `config.py`)
1. **Measured Move Targets**
   - Abandon hardcoded `1.0 ATR` targets. 
   - Dynamically size targets based on the size of the prior trend leg (e.g., Target = distance from the start of the bull trend leg to its climax).
2. **Asset Profiling & Session Guardians**
   - Implement an `AssetProfile` config system:
     ```python
     ASSETS = {
         "BTCUSDT": {"session": "24/7", "target_mode": "measured_move", "atr_filter": 1.0},
         "XAUUSD": {"session": "08:00-17:00_EST", "close_before_weekend": True}
     }
     ```
   - Automatically flatten (close) Gold positions moving into Friday's NY close to avoid massive weekend gaps.

### Phase 3: AI Probability Layer Re-training (`intelligence/rolling_controller.py`)
The `RollingController` acts as a compensator for missing hardcoded logic by implicitly recognizing profitable price structures. 
- **Action**: The AI models must be segregated by asset. A logistic model trained on 100 BTC trades will fail on Gold because the contextual significance of a 1 ATR move is different. 
- Introduce asset-specific probability weighting based on historical performance per ticker.

---

### Conclusion
By implementing **Measured Moves**, **TTR Avoidance**, and **Asset-Specific Session Logic**, the system will graduate from a mechanical algorithmic skeleton to a context-dependent, institutional-grade Price Action trader mirroring Al Brooks' principles.
