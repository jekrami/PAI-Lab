# 2026-02-25 | v3.1.0 | Trade resolution layer | Writer: J.Ekrami | Co-writer: Antigravity
"""
resolvers.py

Al Brooks compliant trade resolution layer.

Stop placement:
    - Bullish: signal_bar["low"]  - STOP_BUFFER_ATR × ATR
    - Bearish: signal_bar["high"] + STOP_BUFFER_ATR × ATR

Target placement:
    - target_distance = stop_distance × RISK_REWARD_RATIO  (≥ 2R)
    - If measured_move impulse > 2R distance → use measured_move instead

Trade management (LiveResolver):
    - At 1R profit: move stop to breakeven + take 50% partial
    - At 2R profit: trail stop 1R behind favorable extreme
    - Scratch: if < 0.3R after 3 bars → exit at breakeven
"""

from datetime import datetime, timezone, timedelta
from config import RISK_REWARD_RATIO, STOP_BUFFER_ATR, SCALP_MIN_RR, SWING_RR, ATR_STOP

# EST offset (UTC-5). During DST it would be UTC-4, but we use a fixed proxy.
EST_OFFSET = timedelta(hours=-5)


def compute_stop_target(entry_price, atr, direction, signal_bar,
                        asset_config=None, features=None, context_quality=None,
                        env=None, regime_probability=None):
    """
    Compute stop and target distances using Al Brooks' signal-bar-based placement.

    Returns:
        (stop_price, target_price, stop_dist, target_dist)  OR  None if the
        trade is structurally unacceptable (wide stop or poor R:R).
    """
    # V8 Phase 2: Dynamic Stop Sizing and Measured Move Targets
    if features:
        vol_ratio = features.get("volatility_ratio", 1.0)
        impulse_raw = features.get("impulse_size_raw", 1.0 * atr)

        # "Vickiness" / Expanding Volatility Check
        if vol_ratio > 1.2:
            # Widen stop to prior structural leg (Measured Move basis)
            stop_dist = max(1.0 * atr, impulse_raw)
        else:
            # Native signal bar geometry
            if direction == "bullish":
                stop_dist = entry_price - signal_bar["low"]
            else:
                stop_dist = signal_bar["high"] - entry_price
            stop_dist = max(stop_dist, 0.5 * atr)

        # Target shifted to Measured Move structural basis
        target_dist = impulse_raw

        # Regime Scaling
        prob_scalar = regime_probability if regime_probability is not None else 0.5
        regime_min_target = stop_dist * (1.0 + prob_scalar)  # Scaled 1R to 2R
        target_dist = max(target_dist, regime_min_target)
    else:
        # Fallback if no features provided
        stop_dist = 1.0 * atr
        target_dist = 2.0 * atr

    if direction == "bullish":
        stop_price = entry_price - stop_dist
    else:
        stop_price = entry_price + stop_dist

    if direction == "bullish":
        target_price = entry_price + target_dist
    else:
        target_price = entry_price - target_dist

    return stop_price, target_price, stop_dist, target_dist


# =====================================================
# BACKTEST RESOLVER
# =====================================================

class BacktestResolver:

    def __init__(self, df):
        self.df = df

    def resolve(self, entry_price, atr, current_time, direction="bullish",
                features=None, asset_config=None, signal_bar=None, env=None,
                regime_probability=None):
        """
        Resolve trade outcome using Al Brooks 2R logic.

        Args:
            current_time: The timestamp of the bar to start looking forward from.
            signal_bar: dict with high/low/open/close of the signal bar.
                        If None, falls back to the candle at current_time.
        
        Returns:
            (outcome, stop_dist, target_dist)
                outcome: 1 = win, 0 = loss, None = unresolved or blocked
                stop_dist / target_dist: actual distances used
        """
        # Build signal bar from dataframe if not provided
        if signal_bar is None:
            if current_time in self.df.index:
                row = self.df.loc[current_time]
                signal_bar = {
                    "high": row["high"],
                    "low": row["low"],
                    "open": row["open"],
                    "close": row["close"],
                }
            else:
                return None, 0, 0

        # --- Micro-Entry Refinement (1m H2/L2) ---
        # Scan the next 15 bars (minutes) for an H2/L2 micro-pullback confirmation
        try:
            wait_df = self.df.loc[current_time:].iloc[1:16]
        except KeyError:
            return None, 0, 0
            
        micro_entry_price = None
        h_count, l_count = 0, 0
        prev_high, prev_low = None, None
        
        for _, wait_row in wait_df.iterrows():
            if prev_high is None:
                prev_high = wait_row["high"]
                prev_low = wait_row["low"]
                continue
                
            if direction == "bullish":
                if wait_row["high"] > prev_high:
                    h_count += 1
                    if h_count == 2:  # H2 triggered
                        micro_entry_price = wait_row["high"]
                        break
            else:
                if wait_row["low"] < prev_low:
                    l_count += 1
                    if l_count == 2:  # L2 triggered
                        micro_entry_price = wait_row["low"]
                        break
            
            prev_high = wait_row["high"]
            prev_low = wait_row["low"]
            
        if micro_entry_price is None:
            # Trade scratched, no H2/L2 confirmation within 15 minutes
            return None, 0, 0
            
        # Refined Entry!
        entry_price = micro_entry_price

        result = compute_stop_target(
            entry_price, atr, direction, signal_bar,
            asset_config=asset_config, features=features, env=env,
            regime_probability=regime_probability
        )
        if result is None:
            return None, 0, 0   # stop too wide or R:R too poor

        stop_price, target_price, stop_dist, target_dist = result

        # Get forward slice (e.g., next 150 minutes, since 30 5m bars = 150 minutes)
        # Assuming df is indexed by time and sorted
        try:
            forward_df = self.df.loc[current_time:].iloc[1:151] # Next 150 bars max
        except KeyError:
            return None, stop_dist, target_dist
            
        for _, future in forward_df.iterrows():

            if direction == "bullish":
                if future["high"] - entry_price >= target_dist:
                    return 1, stop_dist, target_dist
                if entry_price - future["low"] >= stop_dist:
                    return 0, stop_dist, target_dist
            else:  # bearish
                if entry_price - future["low"] >= target_dist:
                    return 1, stop_dist, target_dist
                if future["high"] - entry_price >= stop_dist:
                    return 0, stop_dist, target_dist

        return None, stop_dist, target_dist


# =====================================================
# LIVE RESOLVER (with trailing, scaling, scratch logic)
# =====================================================

class LiveResolver:

    def __init__(self):
        self.position = None  # single-position model
        self.pending_entry = None  # tracks pending 1m micro-entries
        
    def has_open_position(self):
        return self.position is not None or self.pending_entry is not None

    def open_position(self, entry_price, atr, features, direction, size, entry_time,
                      asset_config=None, context_quality=None, signal_bar=None, env=None,
                      regime_probability=None):

        self.pending_entry = {
            "entry_price": entry_price,
            "atr": atr,
            "features": features,
            "direction": direction,
            "size": size,
            "entry_time": entry_time,
            "asset_config": asset_config,
            "context_quality": context_quality,
            "signal_bar": signal_bar,
            "env": env,
            "regime_probability": regime_probability,
            "wait_bars": 0,
            "h_count": 0,
            "l_count": 0,
            "prev_high": None,
            "prev_low": None
        }
        print(f"[LIVE] Pending micro-entry scanning started for {direction.upper()}...")

    def _execute_entry(self, entry_price, pe):
        signal_bar = pe["signal_bar"]
        if signal_bar is None:
            signal_bar = {
                "high": entry_price + 0.5 * pe["atr"],
                "low": entry_price - 0.5 * pe["atr"],
                "open": entry_price,
                "close": entry_price,
            }

        result = compute_stop_target(
            entry_price, pe["atr"], pe["direction"], signal_bar,
            asset_config=pe["asset_config"], features=pe["features"],
            context_quality=pe["context_quality"], env=pe["env"],
            regime_probability=pe["regime_probability"]
        )
        if result is None:
            return False   # stop too wide or R:R too poor

        stop_price, target_price, stop_dist, target_dist = result

        self.position = {
            "entry": entry_price,
            "stop": stop_price,
            "initial_stop": stop_price,
            "target": target_price,
            "stop_dist": stop_dist,
            "target_dist": target_dist,
            "features": pe["features"],
            "direction": pe["direction"],
            "size": pe["size"],
            "remaining_size": pe["size"],
            "entry_time": pe["entry_time"],
            "asset_config": pe["asset_config"] or {},
            "bars_since_entry": 0,
            "partial_taken": False,
            "trail_activated": False,
        }

        rr = target_dist / stop_dist if stop_dist > 0 else 0
        print(f"[LIVE] {pe['direction'].upper()} micro-entry filled @ {entry_price} | "
              f"Target: {target_price:.2f} | Stop: {stop_price:.2f} | "
              f"R:R = {rr:.1f}:1 | Size: {pe['size']:.4f}")

    def update(self, candle):
        if self.pending_entry:
            pe = self.pending_entry
            pe["wait_bars"] += 1
            
            if pe["prev_high"] is None:
                pe["prev_high"] = candle["high"]
                pe["prev_low"] = candle["low"]
                return None, None
                
            micro_entry_price = None
            if pe["direction"] == "bullish":
                if candle["high"] > pe["prev_high"]:
                    pe["h_count"] += 1
                    if pe["h_count"] == 2:
                        micro_entry_price = candle["high"]
            else:
                if candle["low"] < pe["prev_low"]:
                    pe["l_count"] += 1
                    if pe["l_count"] == 2:
                        micro_entry_price = candle["low"]
                        
            pe["prev_high"] = candle["high"]
            pe["prev_low"] = candle["low"]
            
            if micro_entry_price is not None:
                self._execute_entry(micro_entry_price, pe)
                self.pending_entry = None
            elif pe["wait_bars"] >= 15:
                print(f"[LIVE] Pending {pe['direction']} entry scratched (No H2/L2 in 15m)")
                self.pending_entry = None
                
            return None, None

        if not self.position:
            return None, None

        pos = self.position
        pos["bars_since_entry"] += 1

        # --- Close Before Weekend Enforcement ---
        asset_cfg = pos.get("asset_config", {})
        if asset_cfg.get("close_before_weekend", False):
            candle_time = candle.get("open_time") or candle.get("time")
            if candle_time is not None:
                if isinstance(candle_time, (int, float)):
                    dt_utc = datetime.fromtimestamp(candle_time / 1000, timezone.utc)
                else:
                    dt_utc = candle_time
                dt_est = dt_utc + EST_OFFSET
                if dt_est.weekday() == 4 and dt_est.hour >= 16:
                    print("[LIVE] Weekend close — flattening position")
                    close_price = candle.get("close", pos["entry"])
                    if pos["direction"] == "bullish":
                        pnl = close_price - pos["entry"]
                    else:
                        pnl = pos["entry"] - close_price
                    outcome = 1 if pnl > 0 else 0
                    self.position = None
                    return outcome, pos

        # Current distance from entry
        if pos["direction"] == "bullish":
            favorable_dist = candle["high"] - pos["entry"]
            adverse_dist = pos["entry"] - candle["low"]
        else:
            favorable_dist = pos["entry"] - candle["low"]
            adverse_dist = candle["high"] - pos["entry"]

        stop_dist = pos["stop_dist"]
        target_dist = pos["target_dist"]

        # --- Scratch Trade (Al Brooks) ---
        # If 3+ bars pass with < 0.3R movement, exit at breakeven
        if pos["bars_since_entry"] >= 3 and not pos["trail_activated"]:
            if favorable_dist < 0.3 * stop_dist:
                print("[LIVE] Scratch — no follow-through, exiting at breakeven")
                close_price = candle.get("close", pos["entry"])
                if pos["direction"] == "bullish":
                    pnl = close_price - pos["entry"]
                else:
                    pnl = pos["entry"] - close_price
                outcome = 1 if pnl > 0 else 0
                self.position = None
                return outcome, pos

        # --- Trailing Stop Logic ---
        # At 1R profit: move stop to breakeven
        if favorable_dist >= stop_dist and not pos["trail_activated"]:
            pos["stop"] = pos["entry"]
            pos["trail_activated"] = True
            print("[LIVE] Stop moved to breakeven (1R reached)")

        # At 2R profit: trail stop 1R behind each new favorable extreme
        if pos["trail_activated"] and favorable_dist >= target_dist:
            if pos["direction"] == "bullish":
                new_trail = candle["high"] - stop_dist
                if new_trail > pos["stop"]:
                    pos["stop"] = new_trail
            else:
                new_trail = candle["low"] + stop_dist
                if new_trail < pos["stop"]:
                    pos["stop"] = new_trail

        # --- Partial Exit at 1R ---
        if not pos["partial_taken"] and favorable_dist >= stop_dist:
            pos["remaining_size"] = pos["size"] * 0.5
            pos["partial_taken"] = True
            print(f"[LIVE] Partial exit at 1R — 50% taken, {pos['remaining_size']:.4f} remaining")

        # --- Check Target (2R+) ---
        if (pos["direction"] == "bullish" and candle["high"] >= pos["target"]) or \
           (pos["direction"] == "bearish" and candle["low"] <= pos["target"]):
            print(f"[LIVE] Target hit ({target_dist/stop_dist:.1f}R)")
            self.position = None
            return 1, pos

        # --- Check Stop ---
        if (pos["direction"] == "bullish" and candle["low"] <= pos["stop"]) or \
           (pos["direction"] == "bearish" and candle["high"] >= pos["stop"]):
            if pos["trail_activated"]:
                print("[LIVE] Trailing stop hit — locking partial gains")
            else:
                print("[LIVE] Stop hit")
            self.position = None
            return 0, pos

        return None, None
