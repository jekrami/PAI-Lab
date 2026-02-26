# PAI-Lab v6 — Development Log (Temporary)
<!-- 
    Date: 2026-02-26
    Writer: J.Ekrami | Co-writer: Antigravity
    Status: IN PROGRESS — combine with main README.md after all phases complete
-->

> This file logs each Phase-X v6 upgrade in isolation.
> After all phases are complete, merge into `README.md` and delete this file.

---

## Phase-1 v6 — Context Infrastructure

**Branch:** `v6-phase1`  
**Goal:** Prove that the regime context architecture works. Replace the old `LogisticRegression` binary predictor with a tree-based multi-target AI that outputs Bias, Environment, and Continuation Probability per bar.

### Tasks
- [x] Forward-labeling data pipeline — generate Bias / Env / Continuation labels from future price bars (no lookahead leakage)
- [x] `intelligence/ai_context_model.py` — dedicated LightGBM/RF model (auto-selects backend)
- [x] `intelligence/rolling_controller.py` — pure walk-forward orchestration (no model logic)
- [x] Strategy Selector gate in `main.py` — maps AI context to allowed setup types
- [x] Context Logging — `logs/ai_context.csv` per bar with bias, env, cont_prob, gate reason
- [x] Walk-forward backtest verification

### Improvements vs v5.0
| Metric | v5.0 | Phase-1 v6 |
|---|---|---|
| AI Model | Logistic Regression (binary trade gate) | RandomForest / LightGBM (3-target context) |
| Trade count (post-warmup) | 2 | 65 |
| Win Rate | 50% (2 trades — noisy) | 33.85% (65 trades) |
| Avg Win R | +1.5 (est.) | +1.90 |
| Architecture | Trade predictor | Regime interpreter |
| Explainability | None | Full context log per bar |

### Key Findings
- AI correctly learns to label bars as RANGE (dominant in BTC 5m short dataset)
- Structural features (dist_to_lod, impulse_size, volatility_ratio) ranked highest
- Low win rate attributed to thin warmup dataset size — not architecture failure
- Warmup guard bug found: `update_pattern_memory()` must only run post-warmup

---

## Phase-2 v6 — Edge Extraction (Selective Gating)

**Branch:** `v6-phase2`  
**Goal:** Turn AI from "context narrator" into "high-quality trade filter" by adding hard, data-driven selection pressure to suppress low-edge setups and unprofitable regimes.

### Tasks
- [x] Hard AI Confidence Gate — blocks if AI model confidence < 0.60
- [x] Continuation Probability Gate — blocks trend setups if cont_prob < 0.60
- [x] `SetupTracker` — rolling 50-trade avg_R per setup type; auto-disables negative setups (min 20 trades before activating)
- [x] `RegimeTracker` — rolling 75-trade avg_R per AI regime (TREND/RANGE/TRANSITION); auto-blocks negative regimes (min 20 trades)
- [x] `intelligence/analysis_tools.py` — AI Calibration Test + Feature Importance Audit + Tracker Reports
- [x] Post-run analysis wired into `main.py`
- [x] Critical warmup isolation bug fixed (`update_trade_trackers` was outside `is_warmup` guard)

### Improvements vs Phase-1 v6
| Metric | Phase-1 | Phase-2 |
|---|---|---|
| Win Rate | 33.85% | 37.04% |
| Avg R | −0.069 | −0.012 |
| Profit Factor | 0.90 | 0.98 |
| Avg Win R | +1.90 | +1.83 |
| Avg Loss R | −1.08 | −1.10 |
| Trades blocked by gate | 19 | 68 |

### Gate Activity (27 executed / 95 logged)
| Gate | Count |
|---|---|
| `RegimeBlocked:RANGE` | 66 |
| `LowConfidence` | 2 |

### Per-Setup Performance (Phase-2)
| Setup | Avg R | Win Rate |
|---|---|---|
| `wedge_reversal` | +0.18 | 42% |
| `third_entry` | +1.60 | 100% (1 trade) |
| `breakout` | −0.61 | 20% |
| `breakout_pullback` | −1.34 | 0% |
| `failed_breakout` | −1.00 | 0% |

### Calibration Test Result
- **Not monotonic** — AI needs 200+ trades for reliable calibration
- Feature audit confirmed structural features dominate (no noise pollution)

### Still Needed to Meet Phase-2 Success Criteria
- Profit Factor > 1.15 → Need extended dataset (6-12 months BTC 5m)
- Avg R > +0.10 → Requires AI to build confident TREND regime votes
- Remove `failed_breakout` and `breakout_pullback` after 200+ trades if still negative

---

## Phase 2.5 v6 — Structural Alignment (Event-Based ATR Labeling)

**Branch:** `v6-phase2.5`
**Goal:** Replace fixed-horizon (10-bar) labeling with true Event-Based ATR resolution labeling (max 50 bars) to align AI targets perfectly with actual trade mechanics.

### Tasks
- [x] Replace `forward_return_10` with target (+1 ATR) vs stop (-1 ATR) intrabar touch logic.
- [x] Set `max_bars = 50`. Unresolved signals (no target or stop hit within 50 bars) are discarded (`NaN`).
- [x] Add pre-walk-forward diagnostics (Event win/loss/discard % and Pearson correlations with `impulse_size_atr` / `breakout_strength`).
- [ ] Retrain walk-forward and measure real edge.

---

## Phase-3 v6 — *(Planned)*

> To be defined after Phase-2 success criteria are met.

Candidates:
- Extended dataset run (6-12 months) with all Phase-2 gates active
- Worst setup removal (`failed_breakout` / `breakout_pullback`)
- Calibration re-test after 200+ trades
- Phase-2 target validation: PF > 1.15, Avg R > +0.10, DD < v5 baseline
