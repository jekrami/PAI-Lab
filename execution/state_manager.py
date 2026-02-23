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
            "feature_history": getattr(engine.controller, "feature_history", []),
            "outcome_history": getattr(engine.controller, "outcome_history", []),
            "current_threshold": getattr(engine.controller, "current_threshold", 0),
            "model": getattr(engine.controller, "model", None),
            "scaler": getattr(engine.controller, "scaler", None),
            "trained": getattr(engine.controller, "trained", False),
            "recent_returns": getattr(engine.regime_guard, "recent_returns", []),
            "all_returns": getattr(engine.regime_guard, "all_returns", []),
            "equity": getattr(engine.monitor, "equity", []),
            "returns": getattr(engine.monitor, "returns", []),
            "trade_counter": getattr(engine, "trade_counter", 0),
            "last_index": getattr(engine, "last_index", 0)
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
            print("⚠️  State file corrupted. Starting fresh.")
            return False

        # Safe key loading with defaults
        engine.controller.feature_history = state.get("feature_history", [])
        engine.controller.outcome_history = state.get("outcome_history", [])
        engine.controller.current_threshold = state.get("current_threshold", 0)

        engine.controller.model = state.get("model", engine.controller.model)
        engine.controller.scaler = state.get("scaler", engine.controller.scaler)
        engine.controller.trained = state.get("trained", False)

        engine.regime_guard.recent_returns = state.get("recent_returns", [])
        engine.regime_guard.all_returns = state.get("all_returns", [])

        engine.monitor.equity = state.get("equity", [])
        engine.monitor.returns = state.get("returns", [])

        engine.trade_counter = state.get("trade_counter", 0)
        engine.last_index = state.get("last_index", 0)

        print("State loaded successfully.")
        return True
