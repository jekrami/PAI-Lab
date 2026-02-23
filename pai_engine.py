# pai_engine.py
import numpy as np
from collections import deque


class MarketMemory:
    def __init__(self, maxlen=50):
        self.buffer = deque(maxlen=maxlen)

    def add(self, candle):
        self.buffer.append(candle)

    def is_ready(self, n=20):
        return len(self.buffer) >= n

    def data(self):
        return list(self.buffer)


class TrendAnalyzer:
    @staticmethod
    def analyze(memory):
        if len(memory) < 20:
            return {
                "bull_strength": 0.0,
                "bear_strength": 0.0,
                "direction": "not_ready",
            }

        closes = np.array([c["close"] for c in memory])
        x = np.arange(len(closes))

        slope = np.polyfit(x, closes, 1)[0]
        slope_strength = abs(slope) / np.mean(closes)

        diffs = np.diff(closes)
        bullish_moves = (diffs > 0).sum() / len(diffs)
        bearish_moves = (diffs < 0).sum() / len(diffs)

        bull = ((slope > 0) * slope_strength + bullish_moves) / 2
        bear = ((slope < 0) * slope_strength + bearish_moves) / 2

        if bull > bear:
            direction = "bullish"
        elif bear > bull:
            direction = "bearish"
        else:
            direction = "neutral"

        return {
            "bull_strength": round(float(bull), 3),
            "bear_strength": round(float(bear), 3),
            "direction": direction,
        }


class VolatilityAnalyzer:
    @staticmethod
    def atr(memory, period=14):
        if len(memory) < period + 1:
            return None

        trs = []
        for i in range(1, len(memory)):
            h = memory[i]["high"]
            l = memory[i]["low"]
            pc = memory[i - 1]["close"]
            trs.append(max(h - l, abs(h - pc), abs(l - pc)))

        return np.mean(trs[-period:])

    @staticmethod
    def regime(memory, atr):
        if atr is None or len(memory) < 50:
            return "not_ready"

        ranges = [c["high"] - c["low"] for c in memory]
        avg_range = np.mean(ranges)

        if atr > avg_range * 1.3:
            return "high_volatility"
        elif atr < avg_range * 0.7:
            return "low_volatility"
        else:
            return "normal"


class BreakoutDetector:
    @staticmethod
    def detect(memory, trend_direction, lookback=20):
        if len(memory) < lookback + 1:
            return "none"

        prev = memory[-lookback-1:-1]
        last = memory[-1]

        recent_high = max(c["high"] for c in prev)
        recent_low = min(c["low"] for c in prev)

        candle_range = last["high"] - last["low"]
        avg_range = np.mean([c["high"] - c["low"] for c in prev])

        if (
            last["close"] > recent_high
            and candle_range > avg_range
            and trend_direction != "bearish"
        ):
            return "bull_breakout"

        if (
            last["close"] < recent_low
            and candle_range > avg_range
            and trend_direction != "bullish"
        ):
            return "bear_breakout"

        return "none"
class PriceActionAnalyzer:
    @staticmethod
    def trend_bar_info(memory, lookback=20):
        """
        Detect strong trend bars and sequences (adaptive).
        """

        if len(memory) < lookback:
            return {
                "bar_type": "unknown",
                "strong": False,
                "sequence": 0,
                "climactic": False,
            }

        recent = memory[-lookback:]
        last = recent[-1]

        # --- body & range ---
        body = abs(last["close"] - last["open"])
        range_ = last["high"] - last["low"]

        bodies = [
            abs(c["close"] - c["open"]) for c in recent[:-1]
        ]
        avg_body = sum(bodies) / len(bodies)

        strong = body > 1.2 * avg_body and range_ > 0

        # --- close location ---
        if range_ == 0:
            close_pos = 0.5
        else:
            close_pos = (last["close"] - last["low"]) / range_

        bar_type = "neutral"

        if strong:
            if close_pos > 0.75:
                bar_type = "strong_bull"
            elif close_pos < 0.25:
                bar_type = "strong_bear"

        # --- sequence count ---
        sequence = 0
        if bar_type in ("strong_bull", "strong_bear"):
            direction = bar_type
            for c in reversed(recent):
                c_body = abs(c["close"] - c["open"])
                c_range = c["high"] - c["low"]
                if c_range == 0:
                    break

                c_close_pos = (c["close"] - c["low"]) / c_range
                c_strong = c_body > 1.2 * avg_body

                if direction == "strong_bull" and c_strong and c_close_pos > 0.75:
                    sequence += 1
                elif direction == "strong_bear" and c_strong and c_close_pos < 0.25:
                    sequence += 1
                else:
                    break

        # --- climactic hint ---
        ranges = [c["high"] - c["low"] for c in recent[:-1]]
        avg_range = sum(ranges) / len(ranges)

        climactic = sequence >= 3 and range_ > 1.3 * avg_range

        return {
            "bar_type": bar_type,
            "strong": strong,
            "sequence": sequence,
            "climactic": climactic,
        }

class SecondEntryDetector:

    @staticmethod
    def detect(memory, bias, pa_info, lookback=30):
        if bias not in ("bullish", "bearish"):
            return None
        if len(memory) < 10:
            return None

        mem = memory[-lookback:]
        signal_bar = mem[-1]

        # -------------------------------------------------
        # 1️⃣ Explicit 2-Legged Pullback Detection (H2/L2)
        # -------------------------------------------------
        # For bullish (H2): PB Leg 2 Down -> Bounce Up (H1) -> PB Leg 1 Down -> Impulse High
        # For bearish (L2): PB Leg 2 Up -> Bounce Down (L1) -> PB Leg 1 Up -> Impulse Low

        i = len(mem) - 2
        state = "pb_leg2"
        pullback = [signal_bar]

        if bias == "bullish":
            # Walk backward to find H1 (Bounce Up)
            while i > 0 and state == "pb_leg2":
                bar = mem[i]
                pullback.append(bar)
                # If current bar is bullish and higher than the prior, we found the bounce
                if bar["close"] > bar["open"] and bar["high"] > mem[i-1]["high"]:
                    state = "bounce_h1"
                i -= 1

            if state != "bounce_h1": return None

            # Walk backward through the bounce to find PB Leg 1
            while i > 0 and state == "bounce_h1":
                bar = mem[i]
                pullback.append(bar)
                # If current bar is bearish, we are back in Leg 1 Down
                if bar["close"] < bar["open"] and bar["high"] < mem[i-1]["high"]:
                    state = "pb_leg1"
                i -= 1

            if state != "pb_leg1": return None

            # Walk backward through PB Leg 1 to find the Impulse High
            while i >= 0 and state == "pb_leg1":
                bar = mem[i]
                pullback.append(bar)
                # If the bar is strong bullish, it's the end of the prior impulse
                if bar["close"] > bar["open"] and bar["high"] > (mem[i-1]["high"] if i>0 else bar["high"] - 1):
                    state = "impulse"
                    break
                i -= 1

            if state != "impulse": return None

            pullback_extreme = min(b["low"] for b in pullback)
            impulse_extreme = max(b["high"] for b in pullback)
            depth = impulse_extreme - pullback_extreme

        else: # bearish L2
            # Walk backward to find L1 (Bounce Down)
            while i > 0 and state == "pb_leg2":
                bar = mem[i]
                pullback.append(bar)
                if bar["close"] < bar["open"] and bar["low"] < mem[i-1]["low"]:
                    state = "bounce_l1"
                i -= 1

            if state != "bounce_l1": return None

            # Walk backward through the bounce to find PB Leg 1 Up
            while i > 0 and state == "bounce_l1":
                bar = mem[i]
                pullback.append(bar)
                if bar["close"] > bar["open"] and bar["low"] > mem[i-1]["low"]:
                    state = "pb_leg1"
                i -= 1

            if state != "pb_leg1": return None

            # Walk backward to find Impulse Low
            while i >= 0 and state == "pb_leg1":
                bar = mem[i]
                pullback.append(bar)
                if bar["close"] < bar["open"] and bar["low"] < (mem[i-1]["low"] if i>0 else bar["low"] + 1):
                    state = "impulse"
                    break
                i -= 1

            if state != "impulse": return None

            pullback_extreme = max(b["high"] for b in pullback)
            impulse_extreme = min(b["low"] for b in pullback)
            depth = pullback_extreme - impulse_extreme

        pullback_bars = len(pullback)

        # -------------------------------------------------
        # 2️⃣ Signal Bar Quality (Reversal confirmation)
        # -------------------------------------------------
        body = abs(signal_bar["close"] - signal_bar["open"])
        rng = signal_bar["high"] - signal_bar["low"]

        if rng == 0:
            return None

        close_pos = (signal_bar["close"] - signal_bar["low"]) / rng
        body_ratio = body / rng

        # Require strong reversal in the direction of bias
        if bias == "bullish":
            if not (close_pos > 0.65 and body_ratio > 0.4): # Slightly relaxed for Gold/Crypto nuances
                return None
            direction = "bullish"
        else:
            if not (close_pos < 0.35 and body_ratio > 0.4):
                return None
            direction = "bearish"

        return {
            "type": "second_entry",
            "direction": direction,
            "time": signal_bar["time"],
            "price": signal_bar["close"],
            "pullback_depth": depth,
            "pullback_bars": pullback_bars,
            "leg1_h1": True # Flag to indicate explicit leg check passed
        }


class MarketEnvironmentClassifier:
    @staticmethod
    def classify(memory, trend_info, pa_info, lookback=20):

        if len(memory) < lookback:
            return "unknown"

        recent = memory[-lookback:]

        # --- Tight Trading Range (TTR) Detection ---
        ttr_lookback = 7
        if len(recent) >= ttr_lookback:
            ttr_bars = recent[-ttr_lookback:]
            overlaps = 0
            for i in range(1, len(ttr_bars)):
                curr_h, curr_l = ttr_bars[i]["high"], ttr_bars[i]["low"]
                prev_h, prev_l = ttr_bars[i-1]["high"], ttr_bars[i-1]["low"]
                # Check if bars overlap
                if min(curr_h, prev_h) > max(curr_l, prev_l):
                    overlaps += 1

            ranges = [max(c["high"] - c["low"], 1e-9) for c in ttr_bars]
            avg_range = sum(ranges) / len(ranges)
            bodies = [abs(c["close"] - c["open"]) for c in ttr_bars]
            avg_body = sum(bodies) / len(bodies)

            if overlaps >= ttr_lookback - 2 and avg_body < avg_range * 0.5:
                return "tight_trading_range"

        # Count strong bars
        strong_bull = 0
        strong_bear = 0

        for c in recent:
            body = abs(c["close"] - c["open"])
            rng = c["high"] - c["low"]
            if rng == 0:
                continue

            close_pos = (c["close"] - c["low"]) / rng

            if close_pos > 0.75:
                strong_bull += 1
            elif close_pos < 0.25:
                strong_bear += 1

        highs = [c["high"] for c in recent]
        lows = [c["low"] for c in recent]

        # Simple structural progression
        mid = lookback // 2

        first_half_high = max(highs[:mid])
        second_half_high = max(highs[mid:])

        first_half_low = min(lows[:mid])
        second_half_low = min(lows[mid:])

        # Bull structure
        if (
            strong_bull >= 2 and
            second_half_high > first_half_high and
            second_half_low > first_half_low
        ):
            return "structural_bull_trend"

        # Bear structure
        if (
            strong_bear >= 2 and
            second_half_low < first_half_low and
            second_half_high < first_half_high
        ):
            return "structural_bear_trend"

        return "trading_range"
