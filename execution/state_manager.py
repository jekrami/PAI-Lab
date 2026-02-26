# 2026-02-26 | v2.0.0 | Engine state persistence | Writer: J.Ekrami | Co-writer: Antigravity
"""
state_manager.py

Saves and restores engine state across runs.
Updated to Phase-2 RollingController API (ai_model, feature_buffer, candle_buffer, atr_buffer).
"""

import os
import pickle


class StateManager:

    def __init__(self, asset_id="BTCUSDT", base_path="state"):
        self.asset_id = asset_id
        self.path = f"{base_path}/engine_state_{asset_id}.pkl"
        os.makedirs(base_path, exist_ok=True)

    # -------------------------------------------------
    # Save full engine state
    # -------------------------------------------------

    def save(self, engine):

        state = {
            # Phase-2 RollingController internals
            "feature_buffer":        getattr(engine.controller, "feature_buffer", []),
            "candle_buffer":         getattr(engine.controller, "candle_buffer", []),
            "atr_buffer":            getattr(engine.controller, "atr_buffer", []),
            "ai_model":              getattr(engine.controller, "ai_model", None),
            "setup_tracker":         getattr(engine.controller, "setup_tracker", None),
            "regime_tracker":        getattr(engine.controller, "regime_tracker", None),
            "pattern_results":       getattr(engine.controller, "pattern_results", {}),
            "pattern_confidence":    getattr(engine.controller, "pattern_confidence", {}),
            # RegimeGuard
            "recent_returns":        getattr(engine.regime_guard, "recent_returns", []),
            "all_returns":           getattr(engine.regime_guard, "all_returns", []),
            # PerformanceMonitor
            "equity":                getattr(engine.monitor, "equity", []),
            "returns":               getattr(engine.monitor, "returns", []),
            # Engine counters
            "trade_counter":         getattr(engine, "trade_counter", 0),
            "last_index":            getattr(engine, "last_index", 0),
        }

        with open(self.path, "wb") as f:
            pickle.dump(state, f)

    # -------------------------------------------------
    # Load full engine state (SAFE MODE)
    # -------------------------------------------------

    def load(self, engine):

        if not os.path.exists(self.path):
            return False

        try:
            with open(self.path, "rb") as f:
                state = pickle.load(f)
        except Exception:
            print("⚠️  State file corrupted or from an old version. Starting fresh.")
            return False

        # Phase-2 RollingController
        engine.controller.feature_buffer     = state.get("feature_buffer", [])
        engine.controller.candle_buffer      = state.get("candle_buffer", [])
        engine.controller.atr_buffer         = state.get("atr_buffer", [])
        engine.controller.pattern_results    = state.get("pattern_results", {})
        engine.controller.pattern_confidence = state.get("pattern_confidence", {})

        saved_ai_model = state.get("ai_model", None)
        if saved_ai_model is not None:
            engine.controller.ai_model = saved_ai_model

        saved_setup_tracker = state.get("setup_tracker", None)
        if saved_setup_tracker is not None:
            engine.controller.setup_tracker = saved_setup_tracker

        saved_regime_tracker = state.get("regime_tracker", None)
        if saved_regime_tracker is not None:
            engine.controller.regime_tracker = saved_regime_tracker

        # RegimeGuard
        engine.regime_guard.recent_returns = state.get("recent_returns", [])
        engine.regime_guard.all_returns    = state.get("all_returns", [])

        # PerformanceMonitor
        engine.monitor.equity  = state.get("equity", [])
        engine.monitor.returns = state.get("returns", [])

        # Engine counters
        engine.trade_counter = state.get("trade_counter", 0)
        engine.last_index    = state.get("last_index", 0)

        print("State loaded successfully.")
        return True
