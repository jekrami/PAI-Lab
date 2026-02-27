# 2026-02-26 | Phase-2 v6 | AI Analysis Tools (Calibration + Feature Importance) | Writer: J.Ekrami | Co-writer: Antigravity
# v6.1.0
"""
Run AFTER a backtest to audit the AI context model:
  1. AI Calibration Test  — Bin continuation_prob into 10 deciles, measure
                            actual win frequency per bucket. Monotonic = model learning.
  2. Feature Importance   — Export top features from RF/LGBM model.
                            Top features MUST be structural (pressure, breakout), not noise.
  3. Setup Expectancy     — Print per-setup rolling stats.
  4. Regime Expectancy    — Print per-regime rolling stats.

Usage: python intelligence/analysis_tools.py
"""

import sys
import os
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def calibration_test(context_log_path: str = "logs/ai_context.csv",
                     trades_log_path: str  = "logs/trades.csv"):
    """
    Bins continuation_prob into 10 deciles and checks if actual win rate
    is monotonically increasing. If yes, model has predictive edge.
    """
    print("=" * 60)
    print("AI CALIBRATION TEST — Continuation Probability vs Reality")
    print("=" * 60)

    ctx    = pd.read_csv(context_log_path)
    trades = pd.read_csv(trades_log_path)

    executed = ctx[ctx["final_execution"] == True].reset_index(drop=True)
    trades   = trades.reset_index(drop=True)
    n        = min(len(executed), len(trades))

    if n < 20:
        print(f"  [Warning] Not enough data ({n} trades). Run with more candles.\n")
        return

    merged = executed.iloc[:n].copy()
    merged["outcome"] = trades["outcome"].astype(int).iloc[:n].values

    bins = np.linspace(0, 1, 11)
    merged["prob_bin"] = pd.cut(merged["ai_cont_prob"], bins=bins, include_lowest=True)

    table = merged.groupby("prob_bin", observed=True)["outcome"].agg(
        count="count", win_freq="mean"
    )
    print(table.to_string())
    wins = table["win_freq"].dropna().values
    print(table.to_string())
    wins = table["win_freq"].dropna().values
    is_monotonic = all(wins[i] <= wins[i + 1] for i in range(len(wins) - 1))
    print(f"\n  Monotonic: {'YES — model learning edge' if is_monotonic else 'NO — model not calibrated'}")
    print()


def feature_importance_report(controller):
    """
    Extracts and prints feature importances from the trained AI model.
    Requires passing a live RollingController instance.
    """
    print("=" * 60)
    print("FEATURE IMPORTANCE AUDIT")
    print("=" * 60)

    model = controller.ai_model

    if not model.is_trained:
        print("  [Warning] Model not trained yet.\n")
        return

    bias_model = model.model_bias
    feature_names = list(controller.feature_buffer[-1].keys()) if controller.feature_buffer else []

    for name, m in [("Bias", bias_model), ("Environment", model.model_env), ("Continuation", model.model_cont)]:
        print(f"\n  [{name} Model] Top-10 Features:")
        if hasattr(m, "feature_importances_"):
            imp = m.feature_importances_
            pairs = sorted(zip(feature_names, imp), key=lambda x: -x[1]) if feature_names else enumerate(imp)
            for rank, (feat, score) in enumerate(list(pairs)[:10], 1):
                print(f"    {rank:2}. {str(feat):<35} {score:.4f}")
        else:
            print("    No importances available.")
    print()


def setup_regime_report(controller):
    """
    Prints rolling setup expectancy and regime expectancy tables.
    """
    print("=" * 60)
    print("SETUP-LEVEL ROLLING EXPECTANCY")
    print("=" * 60)
    for k, v in controller.setup_tracker.stats().items():
        status = "[DISABLED]" if v["disabled"] else "[Active]"
        print(f"  {k:<25}  trades={v['count']:>3}  avg_R={v['avg_R']:>7.4f}  {status}")

    print()
    print("=" * 60)
    print("PER-REGIME ROLLING EXPECTANCY")
    print("=" * 60)
    for k, v in controller.regime_tracker.stats().items():
        status = "[BLOCKED]" if v["blocked"] else "[Active]"
        print(f"  {k:<15}  trades={v['count']:>3}  avg_R={v['avg_R']:>7.4f}  {status}")
    print()


if __name__ == "__main__":
    # Standalone calibration test from existing logs
    calibration_test()
    print("Note: For Feature Importance and Tracker reports, import and call")
    print("      feature_importance_report(controller) and setup_regime_report(controller)")
    print("      from within main.py after the simulation completes.")
