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


class PositionSizer:

    def __init__(self, initial_equity: float = 100.0):
        """
        initial_equity: starting notional equity, used if no equity history yet
        """
        self.initial_equity = initial_equity

    def size(self, stop_distance_price: float, equity_series, tough_mode: bool = False):
        """
        Compute position size based on account risk percentage.

        Args:
            stop_distance_price: the absolute distance from entry to stop
                                 (in price units, not ATR multiples).
            equity_series:       list of equity values; last element = current equity.
            tough_mode:          True → use 0.3% risk. False → use 1% risk.

        Returns:
            Position size in notional units.
        """
        if stop_distance_price <= 0:
            return 1.0

        current_equity = self.initial_equity
        if equity_series:
            current_equity = equity_series[-1]

        if current_equity <= 0:
            return 0.0

        risk_fraction = RISK_FRACTION_TOUGH if tough_mode else RISK_FRACTION_NORMAL
        risk_amount = current_equity * risk_fraction

        size = risk_amount / stop_distance_price

        # Avoid degenerate sizes
        if size <= 0:
            return 0.0

        return size
