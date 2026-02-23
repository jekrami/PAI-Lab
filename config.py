"""
Description: Global configuration — Al Brooks Price Action risk management.
Date: 2026-02-24
Writer: J.Ekrami
Co-writer: Antigravity
Version: 3.0.0
"""

# =====================================================
# ASSET PROFILES
# =====================================================

ASSETS = {
    "BTCUSDT": {
        "session": "24/7",
        "target_mode": "measured_move",
        "atr_filter": 1.0,
        "close_before_weekend": False
    },
    "XAUUSD": {
        "session": "08:00-17:00_EST",
        "target_mode": "measured_move",
        "atr_filter": 1.0,
        "close_before_weekend": True
    }
}

DEFAULT_ASSET = "BTCUSDT"

# =====================================================
# AL BROOKS RISK MANAGEMENT
# =====================================================

# Default Reward-to-Risk ratio for scalp trades
# Al Brooks: scalps use ~1.5R, swings use 2R with measured move
RISK_REWARD_RATIO = 1.5

# Swing R:R for high-quality setups (measured move > scalp target)
SWING_RR = 2.0

# Stop placement: signal bar extreme + buffer
# e.g. bullish stop = signal_bar["low"] - STOP_BUFFER_ATR * ATR
STOP_BUFFER_ATR = 0.1

# Account risk per trade
RISK_FRACTION_NORMAL = 0.01    # 1% of account in normal conditions
RISK_FRACTION_TOUGH = 0.003    # 0.3% of account in tough conditions

# Scalp minimum R:R — even the lowest-quality setups must be ≥ 1.5R
SCALP_MIN_RR = 1.5

# =====================================================
# TOUGH CONDITION DETECTION
# =====================================================

TOUGH_CONDITION_RULES = {
    "volatility_spike_factor": 1.5,   # short ATR > 1.5× long ATR → tough
    "loss_streak_threshold": 3,       # 3+ consecutive losses → tough
    "low_winrate_threshold": 0.50,    # rolling WR < 50% → tough
}

# =====================================================
# LEGACY CONSTANTS (backward compat during transition)
# =====================================================

ATR_TARGET = 1.0
ATR_STOP = 1.0

# =====================================================
# SIGNAL FILTERING
# =====================================================

DEPTH_THRESHOLD_ATR = 1.0

PULLBACK_MIN = 2
PULLBACK_MAX = 4

# =====================================================
# AI LAYER
# =====================================================

TRAIN_WINDOW = 100
TEST_WINDOW = 20

PROBABILITY_MIN = 0.65
