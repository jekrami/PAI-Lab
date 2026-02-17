# 2026-02-17 | v0.1.0 | Core signal and feature engine | Writer: J.Ekrami | Co-writer: GPT-5.1
"""
core_engine.py

Core signal and feature generation logic.

This module:
- Detects structural signals
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
    MarketEnvironmentClassifier,
)


class CoreEngine:

    def __init__(self):
        self.memory = MarketMemory(maxlen=100)

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
            return None

        trend = TrendAnalyzer.analyze(mem)
        pa = PriceActionAnalyzer.trend_bar_info(mem)
        env = MarketEnvironmentClassifier.classify(mem, trend, pa)

        signal = SecondEntryDetector.detect(mem, trend["direction"], pa)

        if not signal:
            return None

        # Bullish H2 in structural bull trend
        if signal["direction"] == "bullish" and env == "structural_bull_trend":
            return signal

        # Bearish L2 symmetry in structural bear trend
        if signal["direction"] == "bearish" and env == "structural_bear_trend":
            return signal

        return None

    # -------------------------------------------------
    # Build features for probability model
    # -------------------------------------------------

    def build_features(self, signal):

        mem = self.memory.data()

        ranges = [c["high"] - c["low"] for c in mem[-14:]]
        atr = sum(ranges) / len(ranges)

        if signal["pullback_depth"] / atr < DEPTH_THRESHOLD_ATR:
            return None

        pullback_bars = signal["pullback_bars"]
        if not (PULLBACK_MIN <= pullback_bars <= PULLBACK_MAX):
            return None

        long_ranges = [c["high"] - c["low"] for c in mem[-50:]]
        long_atr = sum(long_ranges) / len(long_ranges)

        signal_bar = mem[-1]

        features = extract_features(mem, signal, atr, long_atr, signal_bar, signal_bar)

        return features, atr
