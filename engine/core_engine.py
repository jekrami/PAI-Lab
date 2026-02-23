# 2026-02-23 | v2.1.0 | Core signal and feature engine | Writer: J.Ekrami | Co-writer: Antigravity
"""
core_engine.py

Core signal and feature generation logic.

This module:
- Detects structural signals (H2/L2, breakouts)
- Suppresses signals during climactic exhaustion
- Supports follow-through confirmation (Phase 2)
- Builds features
- Does NOT resolve trades
- Does NOT simulate exits
- Does NOT connect to live feed

It is shared by:
- Backtest mode
- Live mode
"""

from config import *
from core.feature_extractor import extract_features
from pai_engine import (
    MarketMemory,
    TrendAnalyzer,
    PriceActionAnalyzer,
    SecondEntryDetector,
    FirstEntryDetector,
    WedgeDetector,
    MarketEnvironmentClassifier,
    BreakoutDetector,
)


class CoreEngine:

    def __init__(self):
        self.memory = MarketMemory(maxlen=100)
        self.pending_signal = None  # Phase 2: follow-through confirmation

    # -------------------------------------------------
    # Add new candle to memory
    # -------------------------------------------------

    def add_candle(self, candle):
        self.memory.add(candle)

    # -------------------------------------------------
    # Detect signal
    # -------------------------------------------------

    def detect_signal(self):

        mem = self.memory.data()

        if len(mem) < 50:
            self.pending_signal = None
            return None

        # --- Follow-Through Confirmation (Phase 2) ---
        # If we have a pending signal from the prior bar, check if
        # the current bar (follow-through bar) confirms it.
        if self.pending_signal is not None:
            pending = self.pending_signal
            self.pending_signal = None  # consume it

            ft_bar = mem[-1]  # the follow-through bar
            ft_rng = ft_bar["high"] - ft_bar["low"]
            if ft_rng > 0:
                ft_body = abs(ft_bar["close"] - ft_bar["open"])
                ft_close_pos = (ft_bar["close"] - ft_bar["low"]) / ft_rng
                ft_body_ratio = ft_body / ft_rng

                if pending["direction"] == "bullish":
                    # Bull follow-through: closes above midpoint with decent body
                    if ft_close_pos > 0.5 and ft_body_ratio > 0.3:
                        return pending
                elif pending["direction"] == "bearish":
                    # Bear follow-through: closes below midpoint with decent body
                    if ft_close_pos < 0.5 and ft_body_ratio > 0.3:
                        return pending

            # Follow-through failed — no trade
            return None

        trend = TrendAnalyzer.analyze(mem)
        pa = PriceActionAnalyzer.trend_bar_info(mem)
        env = MarketEnvironmentClassifier.classify(mem, trend, pa)

        if env == "tight_trading_range":
            return "tight_trading_range"

        # --- Climactic Exhaustion Suppression ---
        if pa.get("climactic", False):
            return None

        # --- H2 / L2 Second Entry Detection ---
        signal = SecondEntryDetector.detect(mem, trend["direction"], pa)

        if signal:
            # Bullish H2 in structural bull trend
            if signal["direction"] == "bullish" and env == "structural_bull_trend":
                self.pending_signal = signal  # wait for follow-through
                return None
            # Bearish L2 in structural bear trend
            if signal["direction"] == "bearish" and env == "structural_bear_trend":
                self.pending_signal = signal
                return None

        # --- H1 / L1 First Entry (strong trends only) ---
        h1_signal = FirstEntryDetector.detect(mem, trend["direction"], pa)
        if h1_signal:
            if h1_signal["direction"] == "bullish" and env == "structural_bull_trend":
                self.pending_signal = h1_signal
                return None
            if h1_signal["direction"] == "bearish" and env == "structural_bear_trend":
                self.pending_signal = h1_signal
                return None

        # --- Wedge / 3-Push Reversal (counter-trend) ---
        wedge = WedgeDetector.detect(mem, trend["direction"])
        if wedge:
            # Wedge reversals are counter-trend: bearish wedge in bull trend, etc.
            self.pending_signal = wedge
            return None

        # --- Breakout Detection (alternative entry) ---
        # If no H2/L2 found, check for a breakout.
        # Breakouts are valid even in "trading_range" if they are strong.
        breakout = BreakoutDetector.detect(mem, trend["direction"])

        if breakout == "bull_breakout" and env in ("structural_bull_trend", "trading_range"):
            last = mem[-1]
            rng = last["high"] - last["low"]
            if rng > 0:
                close_pos = (last["close"] - last["low"]) / rng
                body_ratio = abs(last["close"] - last["open"]) / rng
                if close_pos > 0.6 and body_ratio > 0.4:
                    return {
                        "type": "breakout",
                        "direction": "bullish",
                        "time": last["time"],
                        "price": last["close"],
                        "pullback_depth": rng,
                        "pullback_bars": 1,
                    }

        if breakout == "bear_breakout" and env in ("structural_bear_trend", "trading_range"):
            last = mem[-1]
            rng = last["high"] - last["low"]
            if rng > 0:
                close_pos = (last["close"] - last["low"]) / rng
                body_ratio = abs(last["close"] - last["open"]) / rng
                if close_pos < 0.4 and body_ratio > 0.4:
                    return {
                        "type": "breakout",
                        "direction": "bearish",
                        "time": last["time"],
                        "price": last["close"],
                        "pullback_depth": rng,
                        "pullback_bars": 1,
                    }

        return None

    # -------------------------------------------------
    # Build features for probability model
    # -------------------------------------------------

    def build_features(self, signal, asset_config=None):

        mem = self.memory.data()

        ranges = [c["high"] - c["low"] for c in mem[-14:]]
        atr = sum(ranges) / len(ranges)

        # For breakout signals, skip the strict pullback depth/duration filters
        if signal.get("type") == "breakout":
            long_ranges = [c["high"] - c["low"] for c in mem[-50:]]
            long_atr = sum(long_ranges) / len(long_ranges)
            signal_bar = mem[-1]
            features = extract_features(mem, signal, atr, long_atr, signal_bar, signal_bar, asset_config=asset_config)
            return features, atr

        if atr > 0 and signal["pullback_depth"] / atr < DEPTH_THRESHOLD_ATR:
            return None

        pullback_bars = signal["pullback_bars"]
        if not (PULLBACK_MIN <= pullback_bars <= PULLBACK_MAX):
            return None

        long_ranges = [c["high"] - c["low"] for c in mem[-50:]]
        long_atr = sum(long_ranges) / len(long_ranges)

        signal_bar = mem[-1]

        features = extract_features(mem, signal, atr, long_atr, signal_bar, signal_bar, asset_config=asset_config)

        # --- HOD/LOD Hard Filter (Phase 5) ---
        # Suppress bullish entries near session high (buying at resistance)
        # Suppress bearish entries near session low (selling at support)
        if signal.get("direction") == "bullish" and features.get("dist_to_hod_atr", 999) < 0.5:
            return None
        if signal.get("direction") == "bearish" and features.get("dist_to_lod_atr", 999) < 0.5:
            return None

        return features, atr

