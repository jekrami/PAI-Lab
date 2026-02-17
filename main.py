# 2026-02-17 | v0.1.1 | Backtest engine runner | Writer: J.Ekrami | Co-writer: GPT-5.1
"""
main.py

Core Sequential Trading Engine.

Responsibilities:
- Candle-by-candle signal detection
- Feature extraction
- AI probability evaluation
- Regime filtering
- Risk control enforcement
- Performance tracking
- State persistence

This file orchestrates all subsystems.

It does NOT:
- Connect to live exchange
- Handle order routing
- Manage deployment
"""

import pandas as pd
import numpy as np

from config import *
from core.feature_extractor import extract_features
from intelligence.rolling_controller import RollingController
from execution.performance_monitor import PerformanceMonitor
from execution.regime_guard import RegimeGuard
from execution.telemetry_logger import TelemetryLogger
from execution.state_manager import StateManager
from execution.risk_manager import RiskManager
from execution.position_sizer import PositionSizer
from execution.resolvers import BacktestResolver

# These come from your existing validated modules

from engine.core_engine import CoreEngine


# =====================================================
# ENGINE RUNNER
# =====================================================

class PAILabEngine:

    def __init__(self, data_path):
        self.df = pd.read_csv(data_path, parse_dates=["open_time"])
        #self.memory = MarketMemory(maxlen=100)
        self.core = CoreEngine()

        self.controller = RollingController(train_window=100)
        self.monitor = PerformanceMonitor()
        self.regime_guard = RegimeGuard(window=20)
        self.logger = TelemetryLogger()
        self.state_manager = StateManager()
        self.last_index = 0
        self.state_manager.load(self)
        self.risk_manager = RiskManager()
        self.resolver = BacktestResolver(self.df)

        # Position sizing
        self.position_sizer = PositionSizer()

        self.trade_counter = 0


    # -------------------------------------------------
    # Structural Signal Detection
    # -------------------------------------------------

    

    # -------------------------------------------------
    # Live Sequential Engine
    # -------------------------------------------------

    def run(self):

        print("Starting live simulation...\n")

        for idx in range(self.last_index, len(self.df)):

            row = self.df.iloc[idx]

            candle = {
                "time": row["open_time"],
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
            }

            self.core.add_candle(candle)

            signal = self.core.detect_signal()
            if not signal:
                continue

            feature_pack = self.core.build_features(signal)
            if not feature_pack:
                continue

            features, atr = feature_pack

            # Survival layer first (capital protection)
            if not self.risk_manager.allow_trading():
                continue
            # Then regime guard (statistical weakness)
            if not self.regime_guard.allow_trading():
                continue

            # 🔹 Probability Controller
            allow_trade = self.controller.evaluate_trade(features)
            if not allow_trade:
                continue

            entry_price = row["high"]

            # Position sizing is currently advisory – outcome logic remains ATR-based.
            position_size = self.position_sizer.size(atr, self.monitor.equity)

            # Backtest resolver still returns directional outcome only.
            outcome = self.resolver.resolve(entry_price, atr, idx)

            if outcome is None:
                continue

            # -------------------------------------------------
            # Trade Executed
            # -------------------------------------------------

            self.trade_counter += 1

            trade_return = ATR_TARGET if outcome == 1 else -ATR_STOP

            # Performance tracking
            self.monitor.record_trade(outcome)

            # Regime tracking
            self.regime_guard.update(trade_return)

            self.risk_manager.update(trade_return, self.monitor.equity)

            # Model update
            self.controller.update_history(features, outcome)
            self.controller.retrain_if_ready()

            # -------------------------------------------------
            # Telemetry Logging
            # -------------------------------------------------

            metrics = self.regime_guard.last_metrics

            probability = 0
            if self.controller.trained:
                probability = self.controller.model.predict_proba(
                    self.controller.scaler.transform(
                        pd.DataFrame([features])
                    )
                )[0][1]

            equity_after = self.monitor.equity[-1]
            equity_before = (
                self.monitor.equity[-2] if len(self.monitor.equity) >= 2 else 0
            )

            self.logger.log_metrics(
                trade_index=self.trade_counter,
                equity=equity_after,
                rolling_expectancy=metrics["expectancy"],
                rolling_winrate=metrics["winrate"],
                rolling_sum=metrics["sum"],
                rolling_volatility=metrics["volatility"],
                adaptive_threshold=self.controller.current_threshold,
                probability=probability,
                paused=self.regime_guard.paused,
            )

            # Trade-level log (buy/sell, size, PnL context)
            direction = signal.get("direction", "bullish")
            decision = "enter_long" if direction == "bullish" else "enter_short"

            self.logger.log_trade(
                mode="backtest",
                trade_index=self.trade_counter,
                direction=direction,
                decision=decision,
                entry_time=signal.get("time"),
                entry_price=entry_price,
                exit_time="",
                exit_price="",
                size=position_size,
                atr=atr,
                outcome=outcome,
                equity_before=equity_before,
                equity_after=equity_after,
                probability=probability,
                adaptive_threshold=self.controller.current_threshold,
                regime_paused=self.regime_guard.paused,
            )

            if self.regime_guard.state_changed():
                event = "PAUSED" if self.regime_guard.paused else "RESUMED"
                self.logger.log_regime_event(
                    event,
                    metrics["expectancy"],
                    metrics["winrate"],
                    metrics["sum"]
                )
            self.last_index = idx
    
        self.state_manager.save(self)    

        print("\nSimulation Complete.\n")

        summary = self.monitor.summary()

        print("Performance Summary:")
        for k, v in summary.items():
            print(f"{k}: {v}")


# =====================================================
# ENTRY POINT
# =====================================================

if __name__ == "__main__":

    engine = PAILabEngine("btc_5m_extended.csv")
    engine.run()
