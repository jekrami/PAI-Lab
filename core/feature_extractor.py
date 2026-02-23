# 2026-02-23 | v0.2.0 | Feature extractor | Writer: J.Ekrami | Co-writer: Gemini
from datetime import datetime


def extract_features(mem, signal, atr, long_atr, next_bar, signal_bar):
    depth_atr = signal["pullback_depth"] / atr
    pullback_bars = signal["pullback_bars"]
    volatility_ratio = atr / long_atr

    # Guard against empty impulse slice
    impulse_start = max(0, len(mem) - pullback_bars - 3)
    impulse_end = max(impulse_start + 1, len(mem) - pullback_bars)
    impulse_slice = mem[impulse_start:impulse_end]

    impulse_high = max(c["high"] for c in impulse_slice)
    impulse_low = min(c["low"] for c in impulse_slice)
    impulse_size_atr = (impulse_high - impulse_low) / atr

    breakout_strength = (next_bar["high"] - signal_bar["high"]) / atr

    # Handle both datetime objects (backtest) and Unix ms timestamps (live)
    t = signal_bar["time"]
    if isinstance(t, (int, float)):
        hour = datetime.utcfromtimestamp(t / 1000).hour
    else:
        hour = t.hour

    return {
        "depth_atr": depth_atr,
        "pullback_bars": pullback_bars,
        "volatility_ratio": volatility_ratio,
        "impulse_size_atr": impulse_size_atr,
        "breakout_strength": breakout_strength,
        "hour": hour
    }
