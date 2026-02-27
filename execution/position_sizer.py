# 2026-02-24 | v1.0.0 | Position sizing engine | Writer: J.Ekrami | Co-writer: Antigravity
"""
position_sizer.py

Al Brooks compliant account-based position sizing.

Risk per trade = fraction of current equity.
    Normal conditions:  1%   of account
    Tough conditions:   0.3% of account

Position size = (equity × risk_fraction) / stop_distance_price

This guarantees that every trade risks exactly the intended percentage
of the account, regardless of volatility or stop distance.
"""

from config import RISK_FRACTION_NORMAL, RISK_FRACTION_TOUGH

# Binary Risk Gate (temporarily uncalibrated AI)
KELLY_BANDS = [
    {"min": 0.0,  "max": 0.60, "risk": 0.000},
    {"min": 0.60, "max": 1.00, "risk": 0.010},
]



class PositionSizer:

    def __init__(self, initial_equity: float = 100.0):
        """
        initial_equity: starting notional equity, used if no equity history yet
        """
        self.initial_equity = initial_equity

    def size(self, stop_distance_price: float, equity_series, tough_mode: bool = False, ai_confidence: float = 0.0, observation_mode: bool = False):
        """
        Compute position size based on account risk percentage.

        Args:
            stop_distance_price: the absolute distance from entry to stop
                                 (in price units, not ATR multiples).
            equity_series:       list of equity values; last element = current equity.
            tough_mode:          True → further penalize risk (e.g., half). False → normal Dynamic Kelly.
            ai_confidence:       AI probability score used to determine baseline risk via Dynamic Kelly Criterion.
            observation_mode:    If True, the system is blocked due to 2% daily drawdown (size = 0).
        """
        if observation_mode or stop_distance_price <= 0:
            return 0.0

        current_equity = self.initial_equity
        if equity_series:
            current_equity = equity_series[-1]

        if current_equity <= 0:
            return 0.0

        # Dynamic Kelly Criterion mapping
        risk_fraction = 0.0
        for band in KELLY_BANDS:
            if band["min"] <= ai_confidence < band["max"] or (band["max"] == 1.0 and ai_confidence >= 1.0):
                risk_fraction = band["risk"]
                break

        # Override if tough conditions map to stricter caps (0.3%)
        if tough_mode:
            risk_fraction = min(risk_fraction, RISK_FRACTION_TOUGH)

        risk_amount = current_equity * risk_fraction
        size = risk_amount / stop_distance_price

        if size <= 0:
            return 0.0

        return size
