# 2026-02-24 | v3.0.0 | Trade resolution layer | Writer: J.Ekrami | Co-writer: Antigravity
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
                        asset_config=None, features=None, context_quality=None):
    """
    Compute stop and target distances using Al Brooks' signal-bar-based placement.

    Returns:
        (stop_price, target_price, stop_dist, target_dist)
    """
    # Stop distance: ATR-based (proven reliable on BTC 5m)
    # Uses ATR_STOP as the primary stop distance, with the signal bar
    # as a minimum floor (never set a stop inside the signal bar range).
    atr_stop_dist = ATR_STOP * atr

    if direction == "bullish":
        signal_bar_stop = entry_price - signal_bar["low"]
        stop_dist = max(atr_stop_dist, signal_bar_stop + STOP_BUFFER_ATR * atr)
        stop_price = entry_price - stop_dist
    else:
        signal_bar_stop = signal_bar["high"] - entry_price
        stop_dist = max(atr_stop_dist, signal_bar_stop + STOP_BUFFER_ATR * atr)
        stop_price = entry_price + stop_dist

    # Cap: stop must not exceed 1.5 ATR (keeps targets reachable)
    if stop_dist > 1.5 * atr:
        stop_dist = 1.5 * atr
        if direction == "bullish":
            stop_price = entry_price - stop_dist
        else:
            stop_price = entry_price + stop_dist

    # Target: default R:R (scalp)
    target_dist = stop_dist * RISK_REWARD_RATIO

    # Measured move override: if impulse > default, use it (swing territory)
    if asset_config and asset_config.get("target_mode") == "measured_move" and features:
        impulse_raw = features.get("impulse_size_raw", 0)
        if impulse_raw > target_dist:
            # Cap swing target at SWING_RR × stop_dist
            target_dist = min(impulse_raw, stop_dist * SWING_RR)

    # Scalp cap: context_quality < 0.5 → reduce target, but never below SCALP_MIN_RR
    if context_quality is not None and context_quality < 0.5:
        scalp_target = stop_dist * SCALP_MIN_RR
        target_dist = min(target_dist, scalp_target)

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

    def resolve(self, entry_price, atr, idx, direction="bullish",
                features=None, asset_config=None, signal_bar=None):
        """
        Resolve trade outcome using Al Brooks 2R logic.

        Args:
            signal_bar: dict with high/low/open/close of the signal bar.
                       If None, falls back to the candle at idx.
        
        Returns:
            (outcome, stop_dist, target_dist)
                outcome: 1 = win, 0 = loss, None = unresolved
                stop_dist / target_dist: actual distances used
        """
        # Build signal bar from dataframe if not provided
        if signal_bar is None:
            row = self.df.iloc[idx]
            signal_bar = {
                "high": row["high"],
                "low": row["low"],
                "open": row["open"],
                "close": row["close"],
            }

        stop_price, target_price, stop_dist, target_dist = compute_stop_target(
            entry_price, atr, direction, signal_bar,
            asset_config=asset_config, features=features
        )

        for j in range(1, 31):

            if idx + j >= len(self.df):
                break

            future = self.df.iloc[idx + j]

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

    def has_open_position(self):
        return self.position is not None

    def open_position(self, entry_price, atr, features, direction, size, entry_time,
                      asset_config=None, context_quality=None, signal_bar=None):

        # Build a pseudo signal bar if not provided
        if signal_bar is None:
            signal_bar = {
                "high": entry_price + 0.5 * atr,
                "low": entry_price - 0.5 * atr,
                "open": entry_price,
                "close": entry_price,
            }

        stop_price, target_price, stop_dist, target_dist = compute_stop_target(
            entry_price, atr, direction, signal_bar,
            asset_config=asset_config, features=features,
            context_quality=context_quality
        )

        self.position = {
            "entry": entry_price,
            "stop": stop_price,
            "initial_stop": stop_price,       # remember original stop for trailing
            "target": target_price,
            "stop_dist": stop_dist,
            "target_dist": target_dist,
            "features": features,
            "direction": direction,
            "size": size,
            "remaining_size": size,            # for partial exits
            "entry_time": entry_time,
            "asset_config": asset_config or {},
            "bars_since_entry": 0,
            "partial_taken": False,
            "trail_activated": False,
        }

        rr = target_dist / stop_dist if stop_dist > 0 else 0
        print(f"[LIVE] {direction.upper()} position opened @ {entry_price} | "
              f"Target: {target_price:.2f} | Stop: {stop_price:.2f} | "
              f"R:R = {rr:.1f}:1 | Size: {size:.4f}")

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
