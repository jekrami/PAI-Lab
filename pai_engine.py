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

        # Support both bullish H2 and bearish L2 symmetry
        if bias not in ("bullish", "bearish"):
            return None

        if len(memory) < 10:
            return None

        mem = memory[-lookback:]

        # -------------------------------------------------
        # 1️⃣ Find impulse extreme
        # -------------------------------------------------

        pullback = []

        if bias == "bullish":
            impulse_extreme = mem[-1]["high"]
        else:
            impulse_extreme = mem[-1]["low"]

        i = len(mem) - 2

        while i >= 0:

            bar = mem[i]

            # For bullish bias: bearish or neutral bars are pullback.
            # For bearish bias: bullish or neutral bars are pullback.
            if bias == "bullish":
                is_pullback = bar["close"] <= bar["open"]
            else:
                is_pullback = bar["close"] >= bar["open"]

            if is_pullback:
                pullback.insert(0, bar)
                i -= 1
            else:
                break

        if len(pullback) == 0:
            return None

        pullback_bars = len(pullback)

        # -------------------------------------------------
        # 3️⃣ Measure pullback depth
        # -------------------------------------------------

        if bias == "bullish":
            pullback_extreme = min(b["low"] for b in pullback)
            depth = impulse_extreme - pullback_extreme
        else:
            pullback_extreme = max(b["high"] for b in pullback)
            depth = pullback_extreme - impulse_extreme

        # -------------------------------------------------
        # 4️⃣ Reversal confirmation (signal bar)
        # -------------------------------------------------

        signal_bar = mem[-1]

        body = abs(signal_bar["close"] - signal_bar["open"])
        rng = signal_bar["high"] - signal_bar["low"]

        if rng == 0:
            return None

        close_pos = (signal_bar["close"] - signal_bar["low"]) / rng
        body_ratio = body / rng

        # Require strong reversal in the direction of bias
        if bias == "bullish":
            if not (close_pos > 0.7 and body_ratio > 0.5):
                return None
            direction = "bullish"
        else:
            if not (close_pos < 0.3 and body_ratio > 0.5):
                return None
            direction = "bearish"

        return {
            "type": "second_entry",
            "direction": direction,
            "time": signal_bar["time"],
            "price": signal_bar["close"],
            "pullback_depth": depth,
            "pullback_bars": pullback_bars,
        }


class MarketEnvironmentClassifier:
    @staticmethod
    def classify(memory, trend_info, pa_info, lookback=20):

        if len(memory) < lookback:
            return "unknown"

        recent = memory[-lookback:]

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
