# 2026-02-23 | v0.2.0 | Trade resolution layer | Writer: J.Ekrami | Co-writer: Gemini
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
"""

from config import ATR_TARGET, ATR_STOP


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
# LIVE RESOLVER
# =====================================================

class LiveResolver:

    def __init__(self):
        self.position = None  # single-position model

    def has_open_position(self):
        return self.position is not None

    def open_position(self, entry_price, atr, features, direction, size, entry_time, asset_config=None):

        target_dist = ATR_TARGET * atr
        stop_dist = ATR_STOP * atr

        if asset_config and asset_config.get("target_mode") == "measured_move" and features:
            impulse_raw = features.get("impulse_size_raw", 0)
            if impulse_raw > 0:
                target_dist = impulse_raw

        if direction == "bearish":
            stop = entry_price + stop_dist
            target = entry_price - target_dist
        else:
            stop = entry_price - stop_dist
            target = entry_price + target_dist

        self.position = {
            "entry": entry_price,
            "stop": stop,
            "target": target,
            "features": features,
            "direction": direction,
            "size": size,
            "entry_time": entry_time,
        }

        print(f"[LIVE] {direction.upper()} position opened @ {entry_price} | Target: {target:.2f} | Stop: {stop:.2f}")

    def update(self, candle):

        if not self.position:
            # No open position, nothing to resolve
            return None, None

        pos = self.position

        # Check target
        if (pos["direction"] == "bullish" and candle["high"] >= pos["target"]) or \
           (pos["direction"] == "bearish" and candle["low"] <= pos["target"]):
            print("[LIVE] Target hit")
            self.position = None
            return 1, pos

        # Check stop
        if (pos["direction"] == "bullish" and candle["low"] <= pos["stop"]) or \
           (pos["direction"] == "bearish" and candle["high"] >= pos["stop"]):
            print("[LIVE] Stop hit")
            self.position = None
            return 0, pos

        return None, None

