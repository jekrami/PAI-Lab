import numpy as np


class RegimeGuard:

    def __init__(self, window=30, baseline_window=100):
        self.window = window
        self.baseline_window = baseline_window

        self.recent_returns = []
        self.all_returns = []

        self.paused = False
        self.previous_state = False

        self.last_metrics = {
            "expectancy": 0,
            "winrate": 0,
            "sum": 0,
            "volatility": 0,
            "z_score": 0
        }

    # -------------------------------------------------
    # Update with latest trade return
    # -------------------------------------------------

    def update(self, trade_return):

        self.recent_returns.append(trade_return)
        self.all_returns.append(trade_return)

        if len(self.recent_returns) > self.window:
            self.recent_returns.pop(0)

        if len(self.all_returns) > self.baseline_window:
            self.all_returns.pop(0)

        self._evaluate_regime()

    # -------------------------------------------------
    # Statistical regime evaluation
    # -------------------------------------------------

    def _evaluate_regime(self):

        # Require a 50-trade burn-in before allowing statistically significant shutdowns
        if len(self.recent_returns) < self.window or len(self.all_returns) < 50:
            self.paused = False
            return

        recent = np.array(self.recent_returns)

        recent_expectancy = recent.mean()
        recent_volatility = recent.std()
        recent_sum = recent.sum()
        recent_winrate = (recent > 0).mean()

        baseline = np.array(self.all_returns)

        baseline_mean = baseline.mean()
        baseline_std = baseline.std() if baseline.std() > 0 else 1

        # Z-score: how far recent edge deviates from baseline
        z_score = (recent_expectancy - baseline_mean) / baseline_std

        self.last_metrics = {
            "expectancy": recent_expectancy,
            "winrate": recent_winrate,
            "sum": recent_sum,
            "volatility": recent_volatility,
            "z_score": z_score
        }

        # Pause if statistically weak
        # Example: more than 1.0 std below baseline
        if z_score < -1.0:
            self.paused = True
        else:
            self.paused = False

    # -------------------------------------------------
    # Check if trading allowed
    # -------------------------------------------------

    def allow_trading(self):
        return not self.paused

    # -------------------------------------------------
    # Detect state change
    # -------------------------------------------------

    def state_changed(self):
        if self.paused != self.previous_state:
            self.previous_state = self.paused
            return True
        return False
