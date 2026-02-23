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

    def resolve(self, entry_price, atr, idx, direction="bullish"):

        for j in range(1, 11):

            if idx + j >= len(self.df):
                break

            future = self.df.iloc[idx + j]

            if direction == "bullish":
                if future["high"] - entry_price >= ATR_TARGET * atr:
                    return 1
                if future["low"] - entry_price <= -ATR_STOP * atr:
                    return 0
            else:  # bearish
                if entry_price - future["low"] >= ATR_TARGET * atr:
                    return 1
                if future["high"] - entry_price >= ATR_STOP * atr:
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

    def open_position(self, entry_price, atr, features, direction, size, entry_time):

        if direction == "bearish":
            stop = entry_price + ATR_STOP * atr
            target = entry_price - ATR_TARGET * atr
        else:
            stop = entry_price - ATR_STOP * atr
            target = entry_price + ATR_TARGET * atr

        self.position = {
            "entry": entry_price,
            "stop": stop,
            "target": target,
            "features": features,
            "direction": direction,
            "size": size,
            "entry_time": entry_time,
        }

        print(f"[LIVE] {direction.upper()} position opened @ {entry_price}")

    def update(self, candle):

        if not self.position:
            # No open position, nothing to resolve
            return None, None

        pos = self.position

        # Check target
        if candle["high"] >= self.position["target"]:
            print("[LIVE] Target hit")
            features = pos.get("features")
            self.position = None
            return 1, pos

        # Check stop
        if candle["low"] <= self.position["stop"]:
            print("[LIVE] Stop hit")
            features = pos.get("features")
            self.position = None
            return 0, pos

        return None, None
