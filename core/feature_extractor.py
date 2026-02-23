# 2026-02-23 | v0.2.1 | Feature extractor | Writer: J.Ekrami | Co-writer: Antigravity
from datetime import datetime

def _get_datetime(t):
    if isinstance(t, (int, float)):
        return datetime.utcfromtimestamp(t / 1000)
    return t

def extract_features(mem, signal, atr, long_atr, next_bar, signal_bar, asset_config=None):
    depth_atr = signal["pullback_depth"] / atr if atr > 0 else 0
    pullback_bars = signal["pullback_bars"]
    volatility_ratio = atr / long_atr if long_atr > 0 else 1

    # Guard against empty impulse slice
    impulse_start = max(0, len(mem) - pullback_bars - 3)
    impulse_end = max(impulse_start + 1, len(mem) - pullback_bars)
    impulse_slice = mem[impulse_start:impulse_end]

    impulse_high = max(c["high"] for c in impulse_slice) if impulse_slice else signal_bar["high"]
    impulse_low = min(c["low"] for c in impulse_slice) if impulse_slice else signal_bar["low"]
    
    # Measured Move Basis: Distance from impulse start to extreme
    impulse_size_raw = impulse_high - impulse_low
    impulse_size_atr = impulse_size_raw / atr if atr > 0 else 0

    breakout_strength = (next_bar["high"] - signal_bar["high"]) / atr if atr > 0 else 0

    # Session Context
    dt_signal = _get_datetime(signal_bar["time"])
    hour = dt_signal.hour
    
    # HOD / LOD Calculation for the current UTC day (as proxy for session)
    session_bars = [c for c in mem if _get_datetime(c["time"]).date() == dt_signal.date()]
    if session_bars:
        session_high = max(c["high"] for c in session_bars)
        session_low = min(c["low"] for c in session_bars)
        dist_to_hod_atr = (session_high - signal_bar["high"]) / atr if atr > 0 else 0
        dist_to_lod_atr = (signal_bar["low"] - session_low) / atr if atr > 0 else 0
    else:
        dist_to_hod_atr = 0
        dist_to_lod_atr = 0

    # Opening Gap (vs prior day close)
    prior_session_bars = [c for c in mem if _get_datetime(c["time"]).date() < dt_signal.date()]
    gap_atr = 0
    if prior_session_bars and session_bars:
        prior_close = prior_session_bars[-1]["close"]
        session_open = session_bars[0]["open"]
        gap_atr = (session_open - prior_close) / atr if atr > 0 else 0

    return {
        "depth_atr": depth_atr,
        "pullback_bars": pullback_bars,
        "volatility_ratio": volatility_ratio,
        "impulse_size_atr": impulse_size_atr,
        "breakout_strength": breakout_strength,
        "hour": hour,
        "dist_to_hod_atr": dist_to_hod_atr,
        "dist_to_lod_atr": dist_to_lod_atr,
        "gap_atr": gap_atr,
        "impulse_size_raw": impulse_size_raw
    }
