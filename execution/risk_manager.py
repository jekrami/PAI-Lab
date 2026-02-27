# 2026-02-25 | v2.0.0 | Risk manager | Writer: J.Ekrami | Co-writer: Antigravity
import numpy as np
from datetime import datetime, timedelta


class RiskManager:

    def __init__(
        self,
        max_total_drawdown=-15,      # hard capital stop (ATR units)
        max_daily_loss=-12,          # per session loss limit (relaxed for AI bootstrap)
        max_loss_streak=8,           # max consecutive losses (relaxed for bootstrap)
        volatility_spike_factor=2.5, # abnormal volatility cutoff
        cooldown_seconds=3600        # 1 hour cooldown after hard stop
    ):

        self.max_total_drawdown = max_total_drawdown
        self.max_daily_loss = max_daily_loss
        self.max_loss_streak = max_loss_streak
        self.volatility_spike_factor = volatility_spike_factor
        self.cooldown_seconds = cooldown_seconds

        self.daily_returns = []
        self.total_equity = []
        self.current_loss_streak = 0
        self.hard_stop_triggered = False
        self.hard_stop_time = None

        # Daily reset tracking
        self._session_start = None
        self._session_duration = timedelta(days=1)

    # -------------------------------------------------
    # Update after trade
    # -------------------------------------------------

    def update(self, trade_return, equity_series, current_time=None):

        self._check_session_reset(current_time)

        self.daily_returns.append(trade_return)
        self.total_equity = equity_series

        # Track loss streak
        if trade_return < 0:
            self.current_loss_streak += 1
        else:
            self.current_loss_streak = 0

        self._evaluate(current_time)

    # -------------------------------------------------
    # Reset daily counters each session
    # -------------------------------------------------

    def _check_session_reset(self, current_time):
        if current_time is None:
            return
            
        if self._session_start is None:
            self._session_start = current_time
            return
            
        if current_time - self._session_start >= self._session_duration:
            self.daily_returns = []
            self._session_start = current_time

    # -------------------------------------------------
    # Evaluate capital risk
    # -------------------------------------------------

    def _evaluate(self, current_time=None):

        if not self.total_equity:
            return

        total_drawdown = min(self.total_equity)

        # Hard stop conditions
        if total_drawdown <= self.max_total_drawdown:
            self.hard_stop_triggered = True
            self.hard_stop_time = current_time

        if sum(self.daily_returns) <= self.max_daily_loss:
            self.hard_stop_triggered = True
            self.hard_stop_time = current_time

        if self.current_loss_streak >= self.max_loss_streak:
            self.hard_stop_triggered = True
            self.hard_stop_time = current_time

    # -------------------------------------------------
    # Volatility protection
    # -------------------------------------------------

    def volatility_check(self, recent_returns):

        if len(recent_returns) < 10:
            return True

        recent_vol = np.std(recent_returns[-10:])
        long_vol = np.std(recent_returns)

        if long_vol == 0:
            return True

        if recent_vol > self.volatility_spike_factor * long_vol:
            return False

        return True

    # -------------------------------------------------
    # Allow trading? (with cooldown recovery)
    # -------------------------------------------------

    def allow_trading(self, current_time=None):
        if not self.hard_stop_triggered:
            return True

        if current_time is None:
            return False

        # Allow recovery after cooldown (except total drawdown)
        if self.hard_stop_time is not None:
            elapsed = (current_time - self.hard_stop_time).total_seconds()
            if elapsed >= self.cooldown_seconds:
                # Only recover from streak/daily stops, not total drawdown
                if self.total_equity and min(self.total_equity) > self.max_total_drawdown:
                    self.hard_stop_triggered = False
                    self.current_loss_streak = 0
                    self.daily_returns = []
                    self._session_start = current_time
                    print("[RiskManager] Cooldown elapsed. Trading resumed.")
                    return True

        return False

    # -------------------------------------------------
    # Tough conditions? (reduce risk, don't block)
    # Al Brooks: reduce from 1% to 0.3% risk
    # -------------------------------------------------

    def is_tough_conditions(self, volatility_ratio=None, atr_current=None, atr_lookback_mean=None):
        """
        Returns True if conditions warrant reduced position sizing.
        This does NOT block trading — it only signals the position
        sizer to use RISK_FRACTION_TOUGH instead of RISK_FRACTION_NORMAL.

        Tough triggers:
        - Loss streak >= 3
        - Daily returns negative
        - Volatility spike (short ATR > 1.5× long ATR)
        - Equity drawdown >= 5% from peak  (v5.0)
        - ATR current > 2× ATR lookback mean (v5.0 volatility shock)
        """
        from config import TOUGH_CONDITION_RULES

        # Loss streak check
        if self.current_loss_streak >= TOUGH_CONDITION_RULES["loss_streak_threshold"]:
            return True

        # Explicit v5.0 streak threshold (belt + suspenders)
        if self.current_loss_streak >= 3:
            return True

        # Daily performance check
        if self.daily_returns and sum(self.daily_returns) < 0:
            return True

        # Volatility spike check (caller passes volatility_ratio from features)
        if volatility_ratio is not None:
            if volatility_ratio > TOUGH_CONDITION_RULES["volatility_spike_factor"]:
                return True

        # v5.0: Equity drawdown check (percentage-based from peak)
        if self.total_equity and len(self.total_equity) >= 2:
            peak = max(self.total_equity)
            current = self.total_equity[-1]
            if peak > 0 and (peak - current) / peak >= 0.05:
                return True

        # v5.0: ATR volatility shock (compare current ATR to rolling mean)
        if atr_current is not None and atr_lookback_mean is not None:
            if atr_lookback_mean > 0 and atr_current > 2.0 * atr_lookback_mean:
                return True

        return False

    def is_observation_mode(self):
        """
        V8 Circuit Breaker: If daily drawdown > 2%, enter observation mode.
        While in observation mode, the system shadow-trades (size=0) to
        track simulated expectancy, but risks no live capital.
        """
        if not self.total_equity or not self.daily_returns:
            return False
            
        # Get equity values corresponding to today's session
        # +1 to include the starting equity of the day
        trades_today = len(self.daily_returns)
        if trades_today == 0:
            return False
            
        today_equity_curve = self.total_equity[-(trades_today + 1):]
        if not today_equity_curve:
            return False
            
        peak_today = max(today_equity_curve)
        current = self.total_equity[-1]
        
        if peak_today > 0 and (peak_today - current) / peak_today > 0.02:
            return True
            
        return False

    def restore_risk(self):
        """
        Called when a new equity high is confirmed.
        Resets loss streak so is_tough_conditions() returns False.
        """
        self.current_loss_streak = 0
        self.daily_returns = []
