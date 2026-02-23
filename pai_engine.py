# 2026-02-24 | v4.0.0 | Price action detection engine | Writer: J.Ekrami | Co-writer: Antigravity
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

        # --- Tail Analysis (Brooks uses tails as weakness indicators) ---
        if range_ > 0:
            if last["close"] > last["open"]:  # bull bar
                upper_tail = (last["high"] - last["close"]) / range_
                lower_tail = (last["open"] - last["low"]) / range_
            else:  # bear or doji
                upper_tail = (last["high"] - last["open"]) / range_
                lower_tail = (last["close"] - last["low"]) / range_
        else:
            upper_tail = 0
            lower_tail = 0

        # --- Bar Overlap (overlap with prior bar weakens signal) ---
        overlap_pct = 0
        if len(recent) >= 2:
            prev = recent[-2]
            overlap_high = min(last["high"], prev["high"])
            overlap_low = max(last["low"], prev["low"])
            if overlap_high > overlap_low and range_ > 0:
                overlap_pct = (overlap_high - overlap_low) / range_
        # --- Inside / Outside Bar Detection ---
        is_inside_bar = False
        is_outside_bar = False
        if len(recent) >= 2:
            prev = recent[-2]
            if last["high"] <= prev["high"] and last["low"] >= prev["low"]:
                is_inside_bar = True
            if last["high"] > prev["high"] and last["low"] < prev["low"]:
                is_outside_bar = True

        return {
            "bar_type": bar_type,
            "strong": strong,
            "sequence": sequence,
            "climactic": climactic,
            "upper_tail": round(upper_tail, 3),
            "lower_tail": round(lower_tail, 3),
            "overlap_pct": round(overlap_pct, 3),
            "is_inside_bar": is_inside_bar,
            "is_outside_bar": is_outside_bar,
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

        # -------------------------------------------------------
        # 🔍 Micro Double Top / Bottom Detection
        # Two bars with extremes within 0.15 ATR — a classic Brooks trap
        # -------------------------------------------------------
        atr_recent = sum(b["high"] - b["low"] for b in mem[-14:]) / 14
        micro_double = False
        if len(mem) >= 3:
            prev2 = mem[-3]
            prev1 = mem[-2]
            if bias == "bullish":
                # Micro double bottom: two bars testing the same low
                if abs(prev1["low"] - prev2["low"]) < 0.15 * atr_recent:
                    micro_double = True
            else:
                # Micro double top: two bars testing the same high
                if abs(prev1["high"] - prev2["high"]) < 0.15 * atr_recent:
                    micro_double = True

        # Relax signal bar body threshold for micro double setups
        min_body_ratio = 0.3 if micro_double else 0.4
        if bias == "bullish":
            if not (close_pos > 0.65 and body_ratio > min_body_ratio):
                return None
            direction = "bullish"
        else:
            if not (close_pos < 0.35 and body_ratio > min_body_ratio):
                return None
            direction = "bearish"

        # -------------------------------------------------------
        # 🔁 H3 / Third-Leg Extension
        # After a valid H2, check if there is a prior H1 making this an H3
        # Gate: only in very strong trends (sequence >= 2 implied by H2 itself)
        # -------------------------------------------------------
        entry_type = "second_entry"
        if i > 0:   # there is still buffer to walk back
            # Attempt a third-leg walk from where the H2 impulse ended
            j = i - 1
            h3_state = "pb_leg3"
            if bias == "bullish":
                while j > 0 and h3_state == "pb_leg3":
                    bar = mem[j]
                    if bar["close"] > bar["open"] and bar["high"] > mem[j-1]["high"]:
                        h3_state = "bounce_h2"
                    j -= 1
                while j > 0 and h3_state == "bounce_h2":
                    bar = mem[j]
                    if bar["close"] < bar["open"] and bar["high"] < mem[j-1]["high"]:
                        entry_type = "third_entry"
                        break
                    j -= 1
            else:
                while j > 0 and h3_state == "pb_leg3":
                    bar = mem[j]
                    if bar["close"] < bar["open"] and bar["low"] < mem[j-1]["low"]:
                        h3_state = "bounce_l2"
                    j -= 1
                while j > 0 and h3_state == "bounce_l2":
                    bar = mem[j]
                    if bar["close"] > bar["open"] and bar["low"] > mem[j-1]["low"]:
                        entry_type = "third_entry"
                        break
                    j -= 1

        return {
            "type": entry_type,
            "direction": direction,
            "time": signal_bar["time"],
            "price": signal_bar["close"],
            "pullback_depth": depth,
            "pullback_bars": pullback_bars,
            "leg1_h1": True,
            "micro_double": micro_double,
        }


class FirstEntryDetector:
    """H1/L1 — single-leg pullback. Only valid in very strong trends (sequence ≥ 3)."""

    @staticmethod
    def detect(memory, bias, pa_info, lookback=20):
        if bias not in ("bullish", "bearish"):
            return None
        if len(memory) < 10:
            return None
        # Only trigger in very strong trends
        if pa_info.get("sequence", 0) < 3:
            return None

        mem = memory[-lookback:]
        signal_bar = mem[-1]

        # Signal bar quality (same as H2 check)
        rng = signal_bar["high"] - signal_bar["low"]
        if rng == 0:
            return None
        body = abs(signal_bar["close"] - signal_bar["open"])
        close_pos = (signal_bar["close"] - signal_bar["low"]) / rng
        body_ratio = body / rng

        if bias == "bullish":
            if not (close_pos > 0.65 and body_ratio > 0.4):
                return None
            # Simple single-leg: find a pullback (≥1 lower low) then bounce
            pb_bars = 0
            for j in range(len(mem) - 2, max(len(mem) - 8, 0), -1):
                if mem[j]["close"] < mem[j]["open"]:
                    pb_bars += 1
                else:
                    break
            if pb_bars < 1:
                return None
            depth = max(b["high"] for b in mem[-pb_bars-2:]) - min(b["low"] for b in mem[-pb_bars-1:])
            return {
                "type": "first_entry",
                "direction": "bullish",
                "time": signal_bar["time"],
                "price": signal_bar["close"],
                "pullback_depth": depth,
                "pullback_bars": pb_bars + 1,
            }
        else:
            if not (close_pos < 0.35 and body_ratio > 0.4):
                return None
            pb_bars = 0
            for j in range(len(mem) - 2, max(len(mem) - 8, 0), -1):
                if mem[j]["close"] > mem[j]["open"]:
                    pb_bars += 1
                else:
                    break
            if pb_bars < 1:
                return None
            depth = max(b["high"] for b in mem[-pb_bars-1:]) - min(b["low"] for b in mem[-pb_bars-2:])
            return {
                "type": "first_entry",
                "direction": "bearish",
                "time": signal_bar["time"],
                "price": signal_bar["close"],
                "pullback_depth": depth,
                "pullback_bars": pb_bars + 1,
            }


class WedgeDetector:
    """3-Push reversal — Brooks' strongest reversal pattern."""

    @staticmethod
    def detect(memory, trend_direction, lookback=30):
        if len(memory) < 15:
            return None

        mem = memory[-lookback:]

        if trend_direction == "bullish":
            # Bearish wedge: 3 pushes to higher highs with decreasing momentum
            pushes = []
            for k in range(5, len(mem)):
                if mem[k]["high"] > max(c["high"] for c in mem[max(0, k-3):k]):
                    push_body = abs(mem[k]["close"] - mem[k]["open"])
                    pushes.append({"idx": k, "high": mem[k]["high"], "body": push_body})

            if len(pushes) >= 3:
                last_3 = pushes[-3:]
                # Each push should make a higher high
                if last_3[0]["high"] < last_3[1]["high"] < last_3[2]["high"]:
                    # Momentum should decrease (smaller bodies)
                    if last_3[2]["body"] < last_3[0]["body"]:
                        signal_bar = mem[-1]
                        rng = signal_bar["high"] - signal_bar["low"]
                        if rng > 0:
                            close_pos = (signal_bar["close"] - signal_bar["low"]) / rng
                            if close_pos < 0.4:  # reversal bar closes low
                                depth = last_3[2]["high"] - min(c["low"] for c in mem[-5:])
                                return {
                                    "type": "wedge_reversal",
                                    "direction": "bearish",
                                    "time": signal_bar["time"],
                                    "price": signal_bar["close"],
                                    "pullback_depth": depth,
                                    "pullback_bars": 3,
                                    "pushes": 3,
                                }

        elif trend_direction == "bearish":
            # Bullish wedge: 3 pushes to lower lows with decreasing momentum
            pushes = []
            for k in range(5, len(mem)):
                if mem[k]["low"] < min(c["low"] for c in mem[max(0, k-3):k]):
                    push_body = abs(mem[k]["close"] - mem[k]["open"])
                    pushes.append({"idx": k, "low": mem[k]["low"], "body": push_body})

            if len(pushes) >= 3:
                last_3 = pushes[-3:]
                if last_3[0]["low"] > last_3[1]["low"] > last_3[2]["low"]:
                    if last_3[2]["body"] < last_3[0]["body"]:
                        signal_bar = mem[-1]
                        rng = signal_bar["high"] - signal_bar["low"]
                        if rng > 0:
                            close_pos = (signal_bar["close"] - signal_bar["low"]) / rng
                            if close_pos > 0.6:  # reversal bar closes high
                                depth = max(c["high"] for c in mem[-5:]) - last_3[2]["low"]
                                return {
                                    "type": "wedge_reversal",
                                    "direction": "bullish",
                                    "time": signal_bar["time"],
                                    "price": signal_bar["close"],
                                    "pullback_depth": depth,
                                    "pullback_bars": 3,
                                    "pushes": 3,
                                }

        return None


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


class InsideBarDetector:
    """
    Inside Bar Setup (Al Brooks: compression before continuation).
    Fires when the current bar is an inside bar after a strong trend bar
    in the direction of the bias. Entry is on break of the mother bar.
    """

    @staticmethod
    def detect(memory, bias, lookback=10):
        if bias not in ("bullish", "bearish"):
            return None
        if len(memory) < 3:
            return None

        mem = memory[-lookback:]
        current = mem[-1]   # candidate inside bar
        mother = mem[-2]    # must be the strong trend bar

        # Check: current bar is inside the mother bar
        if not (current["high"] <= mother["high"] and current["low"] >= mother["low"]):
            return None

        # Mother bar must be a strong trend bar in the bias direction
        m_rng = mother["high"] - mother["low"]
        if m_rng == 0:
            return None
        m_body = abs(mother["close"] - mother["open"])
        m_body_ratio = m_body / m_rng
        m_close_pos = (mother["close"] - mother["low"]) / m_rng

        if bias == "bullish":
            if not (m_close_pos > 0.75 and m_body_ratio > 0.5):
                return None
            direction = "bullish"
        else:
            if not (m_close_pos < 0.25 and m_body_ratio > 0.5):
                return None
            direction = "bearish"

        depth = mother["high"] - mother["low"]  # mother bar range as reference
        return {
            "type": "inside_bar_entry",
            "direction": direction,
            "time": current["time"],
            "price": current["close"],
            "pullback_depth": depth,
            "pullback_bars": 1,
            "mother_bar_high": mother["high"],
            "mother_bar_low": mother["low"],
        }


class SwingPivotTracker:
    """
    Tracks swing highs and swing lows to determine the Always-In direction
    per Al Brooks' definition: based on the last significant swing pivot,
    not a moving average or slope.

    A pivot high: bar whose high is the highest of a 3-bar window.
    A pivot low : bar whose low  is the lowest  of a 3-bar window.
    """

    @staticmethod
    def always_in_direction(memory, lookback=40):
        """Returns 'bullish', 'bearish', or 'neutral'."""
        if len(memory) < 10:
            return "neutral"

        mem = memory[-lookback:]
        pivot_highs = []
        pivot_lows  = []

        for k in range(1, len(mem) - 1):
            if mem[k]["high"] >= mem[k-1]["high"] and mem[k]["high"] >= mem[k+1]["high"]:
                pivot_highs.append((k, mem[k]["high"]))
            if mem[k]["low"] <= mem[k-1]["low"] and mem[k]["low"] <= mem[k+1]["low"]:
                pivot_lows.append((k, mem[k]["low"]))

        if len(pivot_highs) < 2 or len(pivot_lows) < 2:
            return "neutral"  # not enough pivots to judge

        last_ph = pivot_highs[-1][1]
        prev_ph = pivot_highs[-2][1]
        last_pl = pivot_lows[-1][1]
        prev_pl = pivot_lows[-2][1]

        # Higher highs AND higher lows → always-in long
        if last_ph > prev_ph and last_pl > prev_pl:
            return "bullish"
        # Lower highs AND lower lows → always-in short
        if last_ph < prev_ph and last_pl < prev_pl:
            return "bearish"
        # Mixed: two-sided market
        return "neutral"
