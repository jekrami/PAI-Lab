# 2026-02-23 | v2.1.0 | Session context manager | Writer: J.Ekrami | Co-writer: Antigravity
"""
session_context.py

Provides session-aware context for assets.
Tracks session open price, first-hour range, prior day high/low,
and whether the current bar is within the first hour of the session.
"""

from datetime import datetime, timedelta

# EST offset (UTC-5 fixed proxy)
EST_OFFSET = timedelta(hours=-5)


class SessionContext:

    def __init__(self, session_str="24/7"):
        self.session_str = session_str
        self.session_open_price = None
        self.first_hour_high = None
        self.first_hour_low = None
        self.prior_day_high = None
        self.prior_day_low = None
        self._current_date = None
        self._first_hour_end = None
        self._day_high = None
        self._day_low = None
        self._prev_day_high = None
        self._prev_day_low = None

    def update(self, candle):
        """Call this for every candle to track session context."""
        dt = self._get_datetime(candle.get("time") or candle.get("open_time"))
        dt_est = dt + EST_OFFSET
        today = dt_est.date()

        # New session day
        if self._current_date is None or today != self._current_date:
            # Save prior day levels
            if self._day_high is not None:
                self._prev_day_high = self._day_high
                self._prev_day_low = self._day_low

            self._current_date = today
            self.session_open_price = candle["open"]
            self._day_high = candle["high"]
            self._day_low = candle["low"]
            self.first_hour_high = candle["high"]
            self.first_hour_low = candle["low"]
            self._first_hour_end = dt_est.replace(hour=dt_est.hour + 1, minute=0, second=0)

            self.prior_day_high = self._prev_day_high
            self.prior_day_low = self._prev_day_low
        else:
            # Update intraday levels
            if candle["high"] > self._day_high:
                self._day_high = candle["high"]
            if candle["low"] < self._day_low:
                self._day_low = candle["low"]

            # First hour tracking
            if self._first_hour_end and dt_est < self._first_hour_end:
                if candle["high"] > self.first_hour_high:
                    self.first_hour_high = candle["high"]
                if candle["low"] < self.first_hour_low:
                    self.first_hour_low = candle["low"]

    def get_features(self, signal_bar, atr):
        """Return session-level features for the ML model."""
        dt = self._get_datetime(signal_bar.get("time") or signal_bar.get("open_time"))
        dt_est = dt + EST_OFFSET

        in_first_hour = False
        if self._first_hour_end:
            in_first_hour = dt_est < self._first_hour_end

        dist_prior_high = 0
        dist_prior_low = 0
        if self.prior_day_high is not None and atr > 0:
            dist_prior_high = (self.prior_day_high - signal_bar["high"]) / atr
            dist_prior_low = (signal_bar["low"] - self.prior_day_low) / atr

        return {
            "in_first_hour": in_first_hour,
            "dist_to_prior_day_high_atr": round(dist_prior_high, 3),
            "dist_to_prior_day_low_atr": round(dist_prior_low, 3),
            "session_open_price": self.session_open_price or 0,
        }

    def _get_datetime(self, t):
        if isinstance(t, (int, float)):
            return datetime.utcfromtimestamp(t / 1000)
        return t
