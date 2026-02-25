# 2026-02-26 | Phase-1 v6 | Walk-Forward Orchestration Controller | Writer: J.Ekrami | Co-writer: Antigravity
# v6.0.0
"""
RollingController is the training orchestration layer only.
It does NOT contain the model — that lives in intelligence/ai_context_model.py.

Responsibilities:
    - Collect per-bar features and candle prices into a rolling buffer
    - Generate forward-looking labels (Bias, Env, Continuation) with NO lookahead leakage
    - Trigger walk-forward retraining of AIContextModel at configured intervals
    - Expose predict_context() and allowed_setups() for the main engine
"""

import numpy as np
import pandas as pd
from intelligence.ai_context_model import AIContextModel


# ---------------------------------------------------------------------------
# Label generation helpers
# ---------------------------------------------------------------------------

ATR_BIAS_THRESHOLD  = 0.3   # forward 10-bar return must exceed 0.3 ATR for directional bias
ATR_TREND_THRESHOLD = 0.5   # directional move > 0.5 ATR within 10 bars = Trend
CONT_BARS           = 5     # number of forward bars to check for continuation
LABEL_HORIZON       = 10    # bars forward for Bias / Env labels


def _compute_labels(candles: list, atr_series: list) -> pd.DataFrame:
    """
    Generates forward-looking labels for each bar in the buffer.
    The final LABEL_HORIZON bars cannot be labelled (insufficient future data),
    so they are dropped before training.

    Returns DataFrame with columns: ['bias', 'env', 'cont']
    """
    n = len(candles)
    bias_list = []
    env_list  = []
    cont_list = []

    for i in range(n - LABEL_HORIZON):
        close_now = candles[i]['close']
        atr       = atr_series[i] if atr_series[i] > 0 else 1.0

        # Forward closes used for all 3 labels
        future_closes  = [c['close'] for c in candles[i + 1 : i + LABEL_HORIZON + 1]]
        future_highs   = [c['high']  for c in candles[i + 1 : i + LABEL_HORIZON + 1]]
        future_lows    = [c['low']   for c in candles[i + 1 : i + LABEL_HORIZON + 1]]

        forward_return   = future_closes[-1] - close_now
        max_up   = max(future_highs)  - close_now
        max_down = close_now - min(future_lows)

        # --- Bias ---
        threshold = ATR_BIAS_THRESHOLD * atr
        if forward_return > threshold:
            bias = 1
        elif forward_return < -threshold:
            bias = -1
        else:
            bias = 0

        # --- Environment ---
        # Trend if directional move > 1 ATR AND forward return is unidirectional
        directional_move = max(max_up, max_down)
        overlapping_bars = sum(
            1 for j in range(1, min(LABEL_HORIZON, len(future_closes)))
            if (future_closes[j] > future_closes[j - 1]) == (future_closes[0] > close_now)
        )
        env = int(directional_move > ATR_TREND_THRESHOLD * atr and overlapping_bars >= LABEL_HORIZON * 0.6)

        # --- Continuation (5 bars) ---
        cont_closes = future_closes[:CONT_BARS]
        if forward_return > 0:
            cont = int(cont_closes[-1] > close_now)
        elif forward_return < 0:
            cont = int(cont_closes[-1] < close_now)
        else:
            cont = 0

        bias_list.append(bias)
        env_list.append(env)
        cont_list.append(cont)

    return pd.DataFrame({'bias': bias_list, 'env': env_list, 'cont': cont_list})


# ---------------------------------------------------------------------------
# Strategy Selector mapping
# ---------------------------------------------------------------------------

ALLOWED_SETUPS_MAP = {
    # Strong directional + trend → only trend-following setups
    ("BULL",    "TREND"):      ["h2", "h1", "breakout_pullback", "inside_bar"],
    ("BEAR",    "TREND"):      ["l2", "l1", "breakout_pullback", "inside_bar"],

    # Range environment → fade/reversal setups (H2/L2 still valid — failed trend = range boundary)
    ("BULL",    "RANGE"):      ["failed_breakout", "wedge_reversal", "h2", "inside_bar"],
    ("BEAR",    "RANGE"):      ["failed_breakout", "wedge_reversal", "l2", "inside_bar"],

    # NEUTRAL = AI has no strong opinion → let Brooks constraints decide
    # Return empty list means "no override" (see main.py gate: 'allowed is not None')
    ("NEUTRAL", "TREND"):      None,  # pass-through
    ("NEUTRAL", "RANGE"):      None,  # pass-through
    ("NEUTRAL", "TRANSITION"): None,  # pass-through

    # BULL/BEAR in TRANSITION → partial pass-through with directional preference
    ("BULL",    "TRANSITION"): None,  # pass-through
    ("BEAR",    "TRANSITION"): None,  # pass-through
}


# ---------------------------------------------------------------------------
# RollingController (orchestration only)
# ---------------------------------------------------------------------------

class RollingController:

    def __init__(self, train_window: int = 300, retrain_every: int = 50):
        """
        train_window:   Number of bars kept in the rolling feature/price buffer
        retrain_every:  Retrain model after every N new bars
        """
        self.train_window  = train_window
        self.retrain_every = retrain_every

        self.ai_model = AIContextModel()

        # Rolling buffers — one entry per bar (not per trade)
        self.feature_buffer: list[dict] = []   # features at each bar
        self.candle_buffer:  list[dict] = []   # raw candle for forward-label computation
        self.atr_buffer:     list[float] = []  # ATR at each bar

        self._bars_since_retrain = 0

        # Pattern Failure Memory (v5.0 preserved)
        self.pattern_results    = {}
        self.pattern_confidence = {}
        self._warmup_mode       = True

    # -------------------------------------------------------------------
    # Feed a completed bar into the controller
    # -------------------------------------------------------------------

    def add_bar(self, features: dict, candle: dict, atr: float):
        """
        Must be called once per bar with the bar's ML feature dict,
        the raw OHLC candle dict, and the current ATR value.
        """
        self.feature_buffer.append(features)
        self.candle_buffer.append(candle)
        self.atr_buffer.append(atr)

        # Trim to window size
        if len(self.feature_buffer) > self.train_window:
            self.feature_buffer.pop(0)
            self.candle_buffer.pop(0)
            self.atr_buffer.pop(0)

        self._bars_since_retrain += 1
        if self._bars_since_retrain >= self.retrain_every:
            self._retrain()
            self._bars_since_retrain = 0

    # -------------------------------------------------------------------
    # Walk-forward retraining (internal)
    # -------------------------------------------------------------------

    def _retrain(self):
        if len(self.candle_buffer) <= LABEL_HORIZON + 10:
            return  # not enough data yet

        # Build label dataset (future-aware — only uses past candles for current bar)
        df_labels = _compute_labels(self.candle_buffer, self.atr_buffer)

        # Features up to the last labelable bar
        n_labelled = len(df_labels)
        df_features = pd.DataFrame(self.feature_buffer[:n_labelled])

        if df_features.empty or df_labels.empty:
            return

        success = self.ai_model.train(df_features, df_labels)
        if success:
            self._warmup_mode = False

    # -------------------------------------------------------------------
    # Query current context
    # -------------------------------------------------------------------

    def get_context(self, features: dict) -> dict:
        """
        Returns the AI regime context for a given feature dict.
        Safe to call every bar.
        """
        return self.ai_model.predict_context(features)

    def allowed_setups(self, features: dict) -> list:
        """
        Returns the list of setup types permitted under the current AI context.
        This feeds the Strategy Selector gate in core_engine.py / main.py.
        """
        ctx = self.ai_model.last_context
        key = (ctx.get("bias", "NEUTRAL"), ctx.get("environment", "TRANSITION"))
        return ALLOWED_SETUPS_MAP.get(key, [])

    # -------------------------------------------------------------------
    # Pattern Failure Memory (preserved from v5.0)
    # -------------------------------------------------------------------

    def update_pattern_memory(self, pattern_type: str, outcome: int):
        """Call after every trade result with the pattern type and 0/1 outcome."""
        results = self.pattern_results.setdefault(pattern_type, [])
        results.append(outcome)
        if len(results) > 10:
            results.pop(0)

        last2 = results[-2:] if len(results) >= 2 else []
        if last2 == [0, 0]:
            self.pattern_confidence[pattern_type] = 0.5
            if not self._warmup_mode:
                print(f"[PatternMemory] Pattern '{pattern_type}' confidence halved (2x loss).")
        else:
            current = self.pattern_confidence.get(pattern_type, 1.0)
            self.pattern_confidence[pattern_type] = min(1.0, current + 0.1)

    def pattern_confidence_factor(self, pattern_type: str) -> float:
        return self.pattern_confidence.get(pattern_type, 1.0)
