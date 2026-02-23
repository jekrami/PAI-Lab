# 2026-02-24 | v3.0.0 | Backtest engine runner | Writer: J.Ekrami | Co-writer: Antigravity
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
from config import RISK_REWARD_RATIO
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

    def __init__(self, data_path, asset_id=DEFAULT_ASSET):
        self.asset_id = asset_id
        self.asset_config = ASSETS.get(asset_id, ASSETS[DEFAULT_ASSET])
        self.df = pd.read_csv(data_path, parse_dates=["open_time"])
        #self.memory = MarketMemory(maxlen=100)
        self.core = CoreEngine()

        self.controller = RollingController(train_window=100)
        self.monitor = PerformanceMonitor()
        self.regime_guard = RegimeGuard(window=20)
        self.logger = TelemetryLogger()
        self.state_manager = StateManager(asset_id=self.asset_id)
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
            if signal == "tight_trading_range" or not signal:
                # Core engine blocks signals if market env classifier outputs TTR
                continue

            feature_pack = self.core.build_features(signal, asset_config=self.asset_config)
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
            # Al Brooks: enter on break of signal bar
            #   Bullish → enter at signal bar high (breakout above)
            #   Bearish → enter at signal bar low (breakdown below)
            direction = signal.get("direction", "bullish")
            entry_price = row["high"] if direction == "bullish" else row["low"]

            # Build signal bar for stop placement
            signal_bar = {
                "high": float(row["high"]),
                "low": float(row["low"]),
                "open": float(row["open"]),
                "close": float(row["close"]),
            }

            # Resolve trade with Al Brooks signal-bar-based stops and 2R target
            result = self.resolver.resolve(
                entry_price, atr, idx,
                direction=signal.get("direction", "bullish"),
                features=features,
                asset_config=self.asset_config,
                signal_bar=signal_bar
            )

            outcome, stop_dist, target_dist = result

            if outcome is None:
                continue

            # -------------------------------------------------
            # Trade Executed — Dynamic R:R
            # -------------------------------------------------

            self.trade_counter += 1

            # Actual trade return — normalized to ATR units for risk/regime tracking
            # Win: +target_dist/atr (≥ 2.0 ATR), Loss: -stop_dist/atr (≤ 1.5 ATR)
            stop_atr = stop_dist / atr if atr > 0 else 1.0
            target_atr = target_dist / atr if atr > 0 else 2.0
            trade_return = target_atr if outcome == 1 else -stop_atr

            # Determine tough conditions for position sizing
            vol_ratio = features.get("volatility_ratio", 1.0)
            tough_mode = self.risk_manager.is_tough_conditions(volatility_ratio=vol_ratio)

            # Position size: risk exactly 1% (or 0.3% in tough) of account
            position_size = self.position_sizer.size(stop_dist, self.monitor.equity, tough_mode=tough_mode)

            # Performance tracking (ATR-normalized returns)
            self.monitor.record_trade(trade_return)

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

    engine = PAILabEngine("btc_5m_extended.csv", asset_id="BTCUSDT")
    engine.run()
