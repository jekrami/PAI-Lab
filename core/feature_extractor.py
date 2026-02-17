def extract_features(mem, signal, atr, long_atr, next_bar, signal_bar):
    depth_atr = signal["pullback_depth"] / atr
    pullback_bars = signal["pullback_bars"]
    volatility_ratio = atr / long_atr

    impulse_high = max(c["high"] for c in mem[-pullback_bars-3:-pullback_bars])
    impulse_low = min(c["low"] for c in mem[-pullback_bars-3:-pullback_bars])
    impulse_size_atr = (impulse_high - impulse_low) / atr

    breakout_strength = (next_bar["high"] - signal_bar["high"]) / atr

    hour = signal_bar["time"].hour

    return {
        "depth_atr": depth_atr,
        "pullback_bars": pullback_bars,
        "volatility_ratio": volatility_ratio,
        "impulse_size_atr": impulse_size_atr,
        "breakout_strength": breakout_strength,
        "hour": hour
    }
