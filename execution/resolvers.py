# 2026-02-23 | v2.1.0 | Trade resolution layer | Writer: J.Ekrami | Co-writer: Antigravity
"""
resolvers.py

Trade resolution layer.

This module defines how trades are opened and closed.

BacktestResolver:
    - Uses historical lookahead to resolve trade outcome.

LiveResolver:
    - Maintains open position state.
    - Resolves trade using incoming candles.
    - Single-position constraint.
    - Enforces close_before_weekend for session-based assets.
"""

from datetime import datetime, timezone, timedelta
from config import ATR_TARGET, ATR_STOP

# EST offset (UTC-5). During DST it would be UTC-4, but we use a fixed proxy.
EST_OFFSET = timedelta(hours=-5)


# =====================================================
# BACKTEST RESOLVER
# =====================================================

class BacktestResolver:

    def __init__(self, df):
        self.df = df

    def resolve(self, entry_price, atr, idx, direction="bullish", features=None, asset_config=None):
        # Determine Target and Stop dynamically
        target_dist = ATR_TARGET * atr
        stop_dist = ATR_STOP * atr
        
        if asset_config and asset_config.get("target_mode") == "measured_move" and features:
            impulse_raw = features.get("impulse_size_raw", 0)
            if impulse_raw > 0:
                target_dist = impulse_raw

        for j in range(1, 11):

            if idx + j >= len(self.df):
                break

            future = self.df.iloc[idx + j]

            if direction == "bullish":
                if future["high"] - entry_price >= target_dist:
                    return 1
                if entry_price - future["low"] >= stop_dist:
                    return 0
            else:  # bearish
                if entry_price - future["low"] >= target_dist:
                    return 1
                if future["high"] - entry_price >= stop_dist:
                    return 0

        return None


# =====================================================
# LIVE RESOLVER (with trailing, scaling, scratch logic)
# =====================================================

class LiveResolver:

    def __init__(self):
        self.position = None  # single-position model

    def has_open_position(self):
        return self.position is not None

    def open_position(self, entry_price, atr, features, direction, size, entry_time,
                      asset_config=None, context_quality=None):

        target_dist = ATR_TARGET * atr
        stop_dist = ATR_STOP * atr

        if asset_config and asset_config.get("target_mode") == "measured_move" and features:
            impulse_raw = features.get("impulse_size_raw", 0)
            if impulse_raw > 0:
                target_dist = impulse_raw

        # --- Scalp vs Swing Decision (Phase 4) ---
        # context_quality: float 0-1. High → swing (full measured move). Low → scalp (1 ATR).
        if context_quality is not None and context_quality < 0.5:
            target_dist = min(target_dist, ATR_TARGET * atr)   # cap at 1 ATR scalp

        if direction == "bearish":
            stop = entry_price + stop_dist
            target = entry_price - target_dist
        else:
            stop = entry_price - stop_dist
            target = entry_price + target_dist

        self.position = {
            "entry": entry_price,
            "stop": stop,
            "initial_stop": stop,       # remember original stop for trailing
            "target": target,
            "features": features,
            "direction": direction,
            "size": size,
            "remaining_size": size,     # for partial exits
            "entry_time": entry_time,
            "asset_config": asset_config or {},
            "bars_since_entry": 0,
            "partial_taken": False,
            "trail_activated": False,
        }

        print(f"[LIVE] {direction.upper()} position opened @ {entry_price} | Target: {target:.2f} | Stop: {stop:.2f}")

    def update(self, candle):

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
                    dt_utc = datetime.utcfromtimestamp(candle_time / 1000)
                else:
                    dt_utc = candle_time
                dt_est = dt_utc + EST_OFFSET
                if dt_est.weekday() == 4 and dt_est.hour >= 16:
                    print("[LIVE] Weekend close — flattening position")
                    self.position = None
                    close_price = candle.get("close", pos["entry"])
                    if pos["direction"] == "bullish":
                        outcome = 1 if close_price > pos["entry"] else 0
                    else:
                        outcome = 1 if close_price < pos["entry"] else 0
                    return outcome, pos

        # Current distance from entry
        if pos["direction"] == "bullish":
            favorable_dist = candle["high"] - pos["entry"]
            adverse_dist = pos["entry"] - candle["low"]
        else:
            favorable_dist = pos["entry"] - candle["low"]
            adverse_dist = candle["high"] - pos["entry"]

        target_dist = abs(pos["target"] - pos["entry"])

        # --- Scratch Trade (Phase 4) ---
        # If 3+ bars pass with < 0.3 * target_dist movement, exit at breakeven
        if pos["bars_since_entry"] >= 3 and not pos["trail_activated"]:
            if favorable_dist < 0.3 * target_dist:
                print("[LIVE] Scratch — no follow-through, exiting at breakeven")
                self.position = None
                close_price = candle.get("close", pos["entry"])
                if pos["direction"] == "bullish":
                    outcome = 1 if close_price > pos["entry"] else 0
                else:
                    outcome = 1 if close_price < pos["entry"] else 0
                return outcome, pos

        # --- Trailing Stop Logic (Phase 4) ---
        # At 0.5× target: move stop to breakeven
        if favorable_dist >= 0.5 * target_dist and not pos["trail_activated"]:
            pos["stop"] = pos["entry"]
            pos["trail_activated"] = True
            print("[LIVE] Stop moved to breakeven")

        # At 1× target: trail behind each new favorable extreme
        if pos["trail_activated"] and favorable_dist >= target_dist:
            if pos["direction"] == "bullish":
                new_trail = candle["high"] - 0.5 * target_dist
                if new_trail > pos["stop"]:
                    pos["stop"] = new_trail
            else:
                new_trail = candle["low"] + 0.5 * target_dist
                if new_trail < pos["stop"]:
                    pos["stop"] = new_trail

        # --- Partial Exit (Phase 4) ---
        # Take 50% at 1 ATR of profit
        if not pos["partial_taken"] and favorable_dist >= target_dist * 0.5:
            pos["remaining_size"] = pos["size"] * 0.5
            pos["partial_taken"] = True
            print(f"[LIVE] Partial exit — 50% taken, {pos['remaining_size']:.2f} remaining")

        # --- Check Target ---
        if (pos["direction"] == "bullish" and candle["high"] >= pos["target"]) or \
           (pos["direction"] == "bearish" and candle["low"] <= pos["target"]):
            print("[LIVE] Target hit")
            self.position = None
            return 1, pos

        # --- Check Stop ---
        if (pos["direction"] == "bullish" and candle["low"] <= pos["stop"]) or \
           (pos["direction"] == "bearish" and candle["high"] >= pos["stop"]):
            print("[LIVE] Stop hit")
            self.position = None
            return 0, pos

        return None, None



