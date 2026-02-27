# 2026-02-26 | Phase-2 v6 | Walk-Forward Orchestration + Edge Gating | Writer: J.Ekrami | Co-writer: Antigravity
# v6.1.0
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
import os
from collections import deque
from intelligence.ai_context_model import AIContextModel


# ---------------------------------------------------------------------------
# Phase-2.5 Constants
# ---------------------------------------------------------------------------

CONFIDENCE_GATE          = 0.60   # minimum AI model confidence to allow any trade
CONT_PROB_TREND_GATE     = 0.60   # continuation_prob gate for trend-following setups
TREND_SETUPS             = {"h2", "h1", "breakout_pullback", "l2", "l1", "inside_bar"}
SETUP_WINDOW             = 50     # rolling window for setup expectancy
REGIME_WINDOW            = 75     # rolling window for regime expectancy (wider = more stable)
SETUP_MIN_TRADES         = 100    # minimum trades before SetupTracker can disable a setup
REGIME_MIN_TRADES        = 100    # minimum trades before RegimeTracker can block a regime

MAX_BARS                 = 50     # maximum forward scan for event-based label resolution


# ---------------------------------------------------------------------------
# Label generation helpers
# ---------------------------------------------------------------------------

def _compute_labels(candles: list, atr_series: list, market_indices: list, market_buffer: list) -> pd.DataFrame:
    """
    Generates event-based ATR outcome labels using true contiguous market bars.
    Target = close + atr. Stop = close - atr.
    Forward scan max MAX_BARS true 5m bars. First-touch logic (high/low).
    Unresolved signals (neither hit in MAX_BARS) return NaN and are discarded.
    """
    n = len(candles)
    bias_list = []
    env_list  = []
    cont_list = []

    for i in range(n):
        market_idx = market_indices[i]
        
        # If we don't have enough future market bars to guarantee resolution logic, we must discard.
        # But we can also scan up to len(market_buffer). If it hits within available bars, it's valid.
        # If it doesn't hit and we don't have MAX_BARS future bars, we must discard.
        
        close_now = candles[i]['close']
        atr = atr_series[i] if atr_series[i] > 0 else 1.0
        
        # Stage-1 Pivot: Scalp objective — 0.7 ATR target, 1 ATR stop (asymmetric)
        target_up = close_now + 0.7 * atr
        stop_up   = close_now - atr

        target_down = close_now - 0.7 * atr
        stop_down   = close_now + atr
        
        bull_event = None
        bear_event = None
        
        for j in range(1, MAX_BARS + 1):
            if market_idx + j >= len(market_buffer):
                break
                
            future_bar = market_buffer[market_idx + j]
            f_high = future_bar['high']
            f_low  = future_bar['low']
            
            # Check bull event first-touch
            if bull_event is None:
                if f_high >= target_up and f_low <= stop_up:
                    bull_event = 0
                elif f_high >= target_up:
                    bull_event = 1
                elif f_low <= stop_up:
                    bull_event = 0
                    
            # Check bear event first-touch
            if bear_event is None:
                if f_low <= target_down and f_high >= stop_down:
                    bear_event = 0
                elif f_low <= target_down:
                    bear_event = 1
                elif f_high >= stop_down:
                    bear_event = 0
                    
            if bull_event is not None and bear_event is not None:
                break
                
        # --- Mapping to AI targets ---
        if bull_event is None or bear_event is None:
            # Unresolved -> discard
            bias = np.nan
            env = np.nan
            cont = np.nan
        else:
            if bull_event == 1 and bear_event == 0:
                bias = 1
            elif bear_event == 1 and bull_event == 0:
                bias = -1
            else:
                bias = 0  
                
            env = 1 if (bull_event == 1 or bear_event == 1) else 0
            
            is_green = (close_now >= candles[i]['open'])
            if is_green:
                cont = bull_event
            else:
                cont = bear_event
                
        bias_list.append(bias)
        env_list.append(env)
        cont_list.append(cont)

    return pd.DataFrame({'bias': bias_list, 'env': env_list, 'cont': cont_list})


# ---------------------------------------------------------------------------
# Phase-2: Setup-Level Performance Tracker
# ---------------------------------------------------------------------------

class SetupTracker:
    """
    Rolling expectancy tracker per setup type.
    Auto-disables setups whose avg_R over the last SETUP_WINDOW trades < 0.
    Auto-recovers when avg_R turns positive again.
    """

    def __init__(self, window: int = SETUP_WINDOW):
        self.window    = window
        self._data     = {}        # { setup_type: deque of R values }
        self._disabled = set()

    def record(self, setup_type: str, r_value: float):
        if setup_type not in self._data:
            self._data[setup_type] = deque(maxlen=self.window)
        self._data[setup_type].append(r_value)
        vals = self._data[setup_type]
        avg  = sum(vals) / len(vals)
        if avg < 0 and len(vals) >= SETUP_MIN_TRADES:
            self._disabled.add(setup_type)
        else:
            self._disabled.discard(setup_type)

    def is_disabled(self, setup_type: str) -> bool:
        """Only returns True if this setup has enough data AND is in disabled set."""
        if len(self._data.get(setup_type, [])) < SETUP_MIN_TRADES:
            return False
        return setup_type in self._disabled

    def stats(self) -> dict:
        return {
            k: {
                "count":    len(d),
                "avg_R":    round(sum(d) / len(d), 4) if d else 0.0,
                "disabled": k in self._disabled,
            }
            for k, d in self._data.items()
        }


# ---------------------------------------------------------------------------
# Phase-2: Per-Regime Expectancy Tracker
# ---------------------------------------------------------------------------

class RegimeTracker:
    """
    Rolling expectancy tracker per AI Regime (TREND / RANGE / TRANSITION).
    Auto-blocks trading in any consistently-negative regime.
    """

    REGIMES = ("TREND", "RANGE", "TRANSITION")

    def __init__(self, window: int = REGIME_WINDOW):
        self.window   = window
        self._data    = {r: deque(maxlen=window) for r in self.REGIMES}
        self._blocked = set()

    def record(self, regime: str, r_value: float):
        if regime not in self._data:
            return
        self._data[regime].append(r_value)
        vals = self._data[regime]
        avg  = sum(vals) / len(vals)
        if avg < 0 and len(vals) >= REGIME_MIN_TRADES:
            self._blocked.add(regime)
        else:
            self._blocked.discard(regime)

    def is_blocked(self, regime: str) -> bool:
        """Only returns True if this regime has enough data AND is in blocked set."""
        if len(self._data.get(regime, [])) < REGIME_MIN_TRADES:
            return False
        return regime in self._blocked

    def stats(self) -> dict:
        return {
            r: {
                "count":   len(d),
                "avg_R":   round(sum(d) / len(d), 4) if d else 0.0,
                "blocked": r in self._blocked,
            }
            for r, d in self._data.items()
        }


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

        # Try to load existing model
        asset_id = os.environ.get("PAI_ASSET_ID", "BTCUSDT") # Default back to BTC if not found
        model_path = f"state/ai_model_{asset_id}.pkl"
        scaler_path = f"state/ai_scaler_{asset_id}.pkl"
        if os.path.exists(model_path) and os.path.exists(scaler_path):
            try:
                self.ai_model.load(model_path, scaler_path)
                print(f"[RollingController] Loaded pre-trained AI model from {model_path}")
            except Exception as e:
                print(f"[RollingController] Failed to load pre-trained AI model: {e}")

        # Rolling buffers — one entry per setup (not per 5m bar)
        self.feature_buffer: list[dict] = []   # features at each setup
        self.candle_buffer:  list[dict] = []   # raw candle for forward-label computation
        self.atr_buffer:     list[float] = []  # ATR at each setup
        self.market_indices_buffer: list[int] = [] # Index of setup in market_buffer

        self.market_buffer: list[dict] = []    # Raw 5m bar stream (continuous)

        self._bars_since_retrain = 0

        # Phase-2: Performance-based gating trackers
        self.setup_tracker  = SetupTracker(window=SETUP_WINDOW)
        self.regime_tracker = RegimeTracker(window=REGIME_WINDOW)

        # Pattern Failure Memory (v5.0 preserved)
        self.pattern_results    = {}
        self.pattern_confidence = {}
        self._warmup_mode       = not self.ai_model.is_trained

    # -------------------------------------------------------------------
    # Feed the continuous market stream
    # -------------------------------------------------------------------
    
    def add_market_bar(self, candle: dict):
        self.market_buffer.append(candle)

    # -------------------------------------------------------------------
    # Feed a completed setup into the controller
    # -------------------------------------------------------------------

    def add_bar(self, features: dict, candle: dict, atr: float, market_index: int):
        """
        Must be called once per setup with the bar's ML feature dict,
        the raw OHLC candle dict, the current ATR value, and its continuous index.
        """
        self.feature_buffer.append(features)
        self.candle_buffer.append(candle)
        self.atr_buffer.append(atr)
        self.market_indices_buffer.append(market_index)

        # Trim to setup window size
        if len(self.feature_buffer) > self.train_window:
            self.feature_buffer.pop(0)
            self.candle_buffer.pop(0)
            self.atr_buffer.pop(0)
            self.market_indices_buffer.pop(0)

        self._bars_since_retrain += 1
        if self._bars_since_retrain >= self.retrain_every:
            self._retrain()
            self._bars_since_retrain = 0

    # -------------------------------------------------------------------
    # Walk-forward retraining (internal)
    # -------------------------------------------------------------------

    def _retrain(self):
        # We need enough setups AND the most recent setup must have MAX_BARS future contiguous bars to resolve
        if not self.market_indices_buffer:
            return
            
        last_market_index = self.market_indices_buffer[-1]
        bars_available_for_last_setup = len(self.market_buffer) - last_market_index - 1
        
        if len(self.candle_buffer) < 100:
            return  # not enough setup data yet

        df_labels = _compute_labels(
            self.candle_buffer, 
            self.atr_buffer, 
            self.market_indices_buffer, 
            self.market_buffer
        )

        n_labelled = len(df_labels)
        df_features = pd.DataFrame(self.feature_buffer[:n_labelled])

        if df_features.empty or df_labels.empty:
            return

        # --- Phase 2.5 Mandatory Diagnostics ---
        # Combine labels and features to drop NaNs
        df_combined = pd.concat([df_features, df_labels], axis=1)
        
        total_signals = len(df_combined)
        df_clean = df_combined.dropna(subset=['bias', 'env', 'cont']).copy()
        
        resolved_count = len(df_clean)
        discard_count = total_signals - resolved_count
        
        if total_signals > 0 and not df_clean.empty and discard_count > 0:
            print("\n" + "="*60)
            print("PRE-TRAIN EVENT DIAGNOSTICS")
            print("="*60)
            print(f"Total Signals: {total_signals} | Discarded (Unresolved in {MAX_BARS} bars): {discard_count} ({discard_count/total_signals:.1%})")
            
            if resolved_count > 0:
                bull_wins = len(df_clean[df_clean['bias'] == 1])
                bear_wins = len(df_clean[df_clean['bias'] == -1])
                whipsaws = len(df_clean[df_clean['bias'] == 0])
                
                print(f"Resolved: {resolved_count} | Bull Wins: {bull_wins} ({bull_wins/resolved_count:.1%}) | Bear Wins: {bear_wins} ({bear_wins/resolved_count:.1%}) | Whipsaw: {whipsaws} ({whipsaws/resolved_count:.1%})")
                
                # Correlations
                df_clean['bull_event'] = (df_clean['bias'] == 1).astype(int)
                if 'impulse_size_atr' in df_clean.columns:
                    corr_pr = df_clean['impulse_size_atr'].corr(df_clean['bull_event'])
                    print(f"Corr(impulse_size_atr, bull_event) : {corr_pr:.4f}")
                if 'breakout_strength' in df_clean.columns:
                    corr_bo = df_clean['breakout_strength'].corr(df_clean['bull_event'])
                    print(f"Corr(breakout_strength, bull_event): {corr_bo:.4f}")
            print("="*60 + "\n")

        if df_clean.empty or len(df_clean) < 100:
            return

        df_features_clean = df_clean[df_features.columns]
        df_labels_clean = df_clean[['bias', 'env', 'cont']]

        success = self.ai_model.train(df_features_clean, df_labels_clean)
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

    def get_phase2_gates(self, setup_type: str, ai_env: str,
                         confidence: float, cont_prob: float) -> dict:
        """
        Returns a structured Phase-2 gating decision dict.
        Call this AFTER get_context() so last_context is fresh.
        Returned dict keys: block (bool), reason (str or None).
        """
        # Gate 1: Overall AI confidence
        if self.ai_model.is_trained and confidence < CONFIDENCE_GATE:
            return {"block": True, "reason": "LowConfidence"}

        # Gate 2: Continuation probability for trend-following setups
        if self.ai_model.is_trained and setup_type in TREND_SETUPS and cont_prob < CONT_PROB_TREND_GATE:
            return {"block": True, "reason": "LowContinuationProb"}

        # Gate 3: Per-regime expectancy
        if self.regime_tracker.is_blocked(ai_env):
            return {"block": True, "reason": f"RegimeBlocked:{ai_env}"}

        # Gate 4: Per-setup expectancy
        if self.setup_tracker.is_disabled(setup_type):
            return {"block": True, "reason": f"SetupDisabled:{setup_type}"}

        # Gate 5: Strategy Selector (MOO) enforces ALLOWED_SETUPS_MAP
        ctx = self.ai_model.last_context
        if ctx:
            bias = ctx.get("bias", "NEUTRAL")
            env = ctx.get("environment", "TRANSITION")
            allowed = ALLOWED_SETUPS_MAP.get((bias, env))
            # If allowed is a list, and setup_type not in it, block it.
            if allowed is not None and setup_type not in allowed:
                return {"block": True, "reason": f"MOO_Filtered:{setup_type}_in_{bias}_{env}"}

        return {"block": False, "reason": None}

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

    def update_trade_trackers(self, setup_type: str, ai_env: str, r_value: float):
        """
        Phase-2: Feed the trade's realized R-value into both the
        SetupTracker and RegimeTracker after every completed trade.
        """
        if setup_type:
            self.setup_tracker.record(setup_type, r_value)
        self.regime_tracker.record(ai_env, r_value)
