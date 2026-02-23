# 2026-02-24 | v1.0.0 | Risk manager | Writer: J.Ekrami | Co-writer: Antigravity
import numpy as np
import time


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
        self._session_start = time.time()
        self._session_duration = 24 * 3600  # 24 hours

    # -------------------------------------------------
    # Update after trade
    # -------------------------------------------------

    def update(self, trade_return, equity_series):

        self._check_session_reset()

        self.daily_returns.append(trade_return)
        self.total_equity = equity_series

        # Track loss streak
        if trade_return < 0:
            self.current_loss_streak += 1
        else:
            self.current_loss_streak = 0

        self._evaluate()

    # -------------------------------------------------
    # Reset daily counters each session
    # -------------------------------------------------

    def _check_session_reset(self):
        now = time.time()
        if now - self._session_start >= self._session_duration:
            self.daily_returns = []
            self._session_start = now

    # -------------------------------------------------
    # Evaluate capital risk
    # -------------------------------------------------

    def _evaluate(self):

        if not self.total_equity:
            return

        total_drawdown = min(self.total_equity)

        # Hard stop conditions
        if total_drawdown <= self.max_total_drawdown:
            self.hard_stop_triggered = True
            self.hard_stop_time = time.time()

        if sum(self.daily_returns) <= self.max_daily_loss:
            self.hard_stop_triggered = True
            self.hard_stop_time = time.time()

        if self.current_loss_streak >= self.max_loss_streak:
            self.hard_stop_triggered = True
            self.hard_stop_time = time.time()

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

    def allow_trading(self):
        if not self.hard_stop_triggered:
            return True

        # Allow recovery after cooldown (except total drawdown)
        if self.hard_stop_time is not None:
            elapsed = time.time() - self.hard_stop_time
            if elapsed >= self.cooldown_seconds:
                # Only recover from streak/daily stops, not total drawdown
                if self.total_equity and min(self.total_equity) > self.max_total_drawdown:
                    self.hard_stop_triggered = False
                    self.current_loss_streak = 0
                    self.daily_returns = []
                    self._session_start = time.time()
                    print("[RiskManager] Cooldown elapsed. Trading resumed.")
                    return True

        return False

    # -------------------------------------------------
    # Tough conditions? (reduce risk, don't block)
    # Al Brooks: reduce from 1% to 0.3% risk
    # -------------------------------------------------

    def is_tough_conditions(self, volatility_ratio=None):
        """
        Returns True if conditions warrant reduced position sizing.
        This does NOT block trading — it only signals the position
        sizer to use RISK_FRACTION_TOUGH instead of RISK_FRACTION_NORMAL.

        Tough triggers:
        - Loss streak >= threshold (default 3)
        - Daily returns negative
        - Volatility spike (short ATR > 1.5× long ATR)
        """
        from config import TOUGH_CONDITION_RULES

        # Loss streak check
        if self.current_loss_streak >= TOUGH_CONDITION_RULES["loss_streak_threshold"]:
            return True

        # Daily performance check
        if self.daily_returns and sum(self.daily_returns) < 0:
            return True

        # Volatility spike check (caller passes volatility_ratio from features)
        if volatility_ratio is not None:
            if volatility_ratio > TOUGH_CONDITION_RULES["volatility_spike_factor"]:
                return True

        return False

