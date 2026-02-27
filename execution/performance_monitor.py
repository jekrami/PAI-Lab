# 2026-02-27 | v1.1.0 | Performance tracking and metrics | Writer: J.Ekrami | Co-writer: Antigravity
import numpy as np


class PerformanceMonitor:

    def __init__(self):
        self.returns = []
        self.equity = []

    # -------------------------------------------------
    # Record a trade outcome
    # -------------------------------------------------

    def record_trade(self, trade_return):

        # trade_return: actual PnL of the trade (positive or negative)

        self.returns.append(trade_return)

        if not self.equity:
            self.equity.append(trade_return)
        else:
            self.equity.append(self.equity[-1] + trade_return)

    # -------------------------------------------------
    # Reconstruct full performance metrics
    # -------------------------------------------------

    def summary(self):

        if not self.returns:
            return {
                "total_trades": 0,
                "expectancy": 0,
                "profit_factor": 0,
                "volatility": 0,
                "sharpe_proxy": 0,
                "max_drawdown": 0,
                "winrate": 0,
                "max_win_streak": 0,
                "max_loss_streak": 0
            }

        returns = np.array(self.returns)
        equity = np.array(self.equity)

        expectancy = returns.mean()
        volatility = returns.std()
        sharpe_proxy = expectancy / volatility if volatility > 0 else 0
        
        # Profit Factor
        gross_profit = returns[returns > 0].sum() if len(returns[returns > 0]) > 0 else 0
        gross_loss = abs(returns[returns < 0].sum()) if len(returns[returns < 0]) > 0 else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)

        # Drawdown calculation
        running_max = np.maximum.accumulate(equity)
        drawdowns = equity - running_max
        max_drawdown = drawdowns.min()

        # Winrate
        winrate = (returns > 0).mean() * 100

        # Streak calculation
        max_win_streak = 0
        max_loss_streak = 0
        current_streak = 0

        for r in returns:
            if r > 0:
                if current_streak >= 0:
                    current_streak += 1
                else:
                    current_streak = 1
            else:
                if current_streak <= 0:
                    current_streak -= 1
                else:
                    current_streak = -1

            max_win_streak = max(max_win_streak, current_streak)
            max_loss_streak = min(max_loss_streak, current_streak)

        return {
            "total_trades": len(returns),
            "expectancy": round(expectancy, 4),
            "profit_factor": round(profit_factor, 2),
            "volatility": round(volatility, 4),
            "sharpe_proxy": round(sharpe_proxy, 4),
            "max_drawdown": round(max_drawdown, 2),
            "winrate": round(winrate, 2),
            "max_win_streak": max_win_streak,
            "max_loss_streak": max_loss_streak
        }
