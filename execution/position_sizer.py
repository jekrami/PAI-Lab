# 2026-02-17 | v0.1.0 | Position sizing engine | Writer: J.Ekrami | Co-writer: GPT-5.1
"""
position_sizer.py

Simple volatility-based position sizing.

Uses fixed-fractional risk per trade with ATR-based stop distance.
All returns remain expressed in ATR units for the existing pipeline.
"""

class PositionSizer:
    def __init__(self, risk_fraction: float = 0.01, initial_equity: float = 100.0):
        """
        risk_fraction: fraction of current equity to risk per trade (0.01 = 1%)
        initial_equity: starting notional equity, used if no equity history yet
        """
        self.risk_fraction = risk_fraction
        self.initial_equity = initial_equity

    def size(self, atr: float, equity_series):
        """
        Compute position size in arbitrary units, based on:
        - current equity (last point in equity_series)
        - atr as the stop distance in ATR units

        Returns 1.0 if atr is non-positive or equity history is empty,
        so the existing ATR-based expectancy pipeline keeps working.
        """
        if atr <= 0:
            return 1.0

        current_equity = self.initial_equity
        if equity_series:
            current_equity = equity_series[-1]

        risk_amount = current_equity * self.risk_fraction
        size = risk_amount / atr if atr > 0 else 1.0

        # Avoid degenerate zero or negative sizes
        if size <= 0:
            return 1.0

        return size

