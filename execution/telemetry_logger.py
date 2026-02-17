# 2026-02-17 | v0.1.0 | Telemetry and trade logger | Writer: J.Ekrami | Co-writer: GPT-5.1
import csv
import os
from datetime import datetime


class TelemetryLogger:

    def __init__(self,
                 metrics_path="logs/live_metrics.csv",
                 regime_path="logs/regime_events.csv",
                 trades_path="logs/trades.csv"):

        self.metrics_path = metrics_path
        self.regime_path = regime_path
        self.trades_path = trades_path

        os.makedirs("logs", exist_ok=True)

        self._init_file(self.metrics_path,
                        ["timestamp", "trade_index", "equity",
                         "rolling_expectancy", "rolling_winrate",
                         "rolling_sum", "rolling_volatility",
                         "adaptive_threshold", "probability",
                         "paused"])

        self._init_file(self.regime_path,
                        ["timestamp", "event",
                         "rolling_expectancy",
                         "rolling_winrate",
                         "rolling_sum"])

        self._init_file(
            self.trades_path,
            [
                "timestamp",
                "mode",
                "trade_index",
                "direction",
                "decision",
                "entry_time",
                "entry_price",
                "exit_time",
                "exit_price",
                "size",
                "atr",
                "outcome",
                "equity_before",
                "equity_after",
                "probability",
                "adaptive_threshold",
                "regime_paused",
            ],
        )

    def _init_file(self, path, headers):
        if not os.path.exists(path):
            with open(path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(headers)

    def log_metrics(self, trade_index, equity,
                    rolling_expectancy,
                    rolling_winrate,
                    rolling_sum,
                    rolling_volatility,
                    adaptive_threshold,
                    probability,
                    paused):

        with open(self.metrics_path, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                datetime.utcnow(),
                trade_index,
                equity,
                rolling_expectancy,
                rolling_winrate,
                rolling_sum,
                rolling_volatility,
                adaptive_threshold,
                probability,
                paused
            ])

    def log_regime_event(self, event,
                         rolling_expectancy,
                         rolling_winrate,
                         rolling_sum):

        with open(self.regime_path, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                datetime.utcnow(),
                event,
                rolling_expectancy,
                rolling_winrate,
                rolling_sum
            ])

    def log_trade(
        self,
        mode,
        trade_index,
        direction,
        decision,
        entry_time,
        entry_price,
        exit_time,
        exit_price,
        size,
        atr,
        outcome,
        equity_before,
        equity_after,
        probability,
        adaptive_threshold,
        regime_paused,
    ):

        with open(self.trades_path, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    datetime.utcnow(),
                    mode,
                    trade_index,
                    direction,
                    decision,
                    entry_time,
                    entry_price,
                    exit_time,
                    exit_price,
                    size,
                    atr,
                    outcome,
                    equity_before,
                    equity_after,
                    probability,
                    adaptive_threshold,
                    regime_paused,
                ]
            )
