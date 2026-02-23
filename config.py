"""
Description: Global configuration including Al Brooks Strategy multi-asset support.
Date: 2026-02-23
Writer: J.Ekrami
Co-writer: Antigravity
"""

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

ATR_TARGET = 1.0
ATR_STOP = 1.30
DEPTH_THRESHOLD_ATR = 1.0

PULLBACK_MIN = 2
PULLBACK_MAX = 4

TRAIN_WINDOW = 100
TEST_WINDOW = 20

PROBABILITY_MIN = 0.65
