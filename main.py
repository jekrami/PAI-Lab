# 2026-02-26 | Phase-1 v6 | Backtest engine runner | Writer: J.Ekrami | Co-writer: Antigravity
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

    def __init__(self, data_path, asset_id=DEFAULT_ASSET, warm_up_bars: int = 40000):
        self.asset_id = asset_id
        self.asset_config = ASSETS.get(asset_id, ASSETS[DEFAULT_ASSET])
        self.warm_up_bars = warm_up_bars
        self.df = pd.read_csv(data_path, parse_dates=["open_time"])
        #self.memory = MarketMemory(maxlen=100)
        self.core = CoreEngine()

        self.controller = RollingController(train_window=300, retrain_every=50)
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

        for idx, row_dict in enumerate(self.df.to_dict(orient="records")):
            if idx < self.last_index: # Skip already processed rows if state was loaded
                continue

            row = pd.Series(row_dict) # Convert dict back to Series for consistent access

            # Mark warmup mode on controller to suppress console print noise
            self.controller._warmup_mode = (idx < self.warm_up_bars)

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

            features, atr, is_suboptimal, env = feature_pack

            # Read v5.0 signal metadata
            regime_probability = signal.get("regime_probability", None)
            force_scalp        = signal.get("force_scalp", False)
            risk_override      = signal.get("risk_override", None)
            pattern_type       = signal.get("type", None)

            is_warmup = (idx < self.warm_up_bars)

            # Survival layer first (capital protection)
            if not is_warmup and not self.risk_manager.allow_trading(current_time=row["open_time"]):
                continue
            # Then regime guard (statistical weakness)
            if not is_warmup and not self.regime_guard.allow_trading():
                continue

            # 🔹 Probability Controller: v6 uses Strategy Selector gate instead of evaluate_trade
            # --- Phase-1 v6: Feed bar into controller for labeling + training ---
            self.controller.add_bar(features, candle, atr)

            # --- Phase-1 v6: Get AI Context ---
            ctx = self.controller.get_context(features)
            ai_bias        = ctx["bias"]
            ai_env         = ctx["environment"]
            ai_cont_prob   = ctx["continuation_prob"]

            # --- Phase-1 v6: Strategy Selector (setup gate) ---
            # Only enforce once AI has completed its first training cycle
            allowed = self.controller.allowed_setups(features)
            ai_trained = self.controller.ai_model.is_trained
            if not is_warmup and ai_trained and allowed is not None and pattern_type not in allowed:
                # Context Logger — record blocked by strategy selector
                self.logger.log_context(
                    bar_time        = candle["time"],
                    ai_bias         = ai_bias,
                    ai_env          = ai_env,
                    ai_cont_prob    = ai_cont_prob,
                    selected_strategy = pattern_type,
                    blocked_by_constraint = True,
                    constraint_reason = "StrategySelector",
                    final_execution = False
                )
                continue

            # --- Phase-1 v6: Scale AI continuation_prob into pattern confidence ---
            confidence_factor = self.controller.pattern_confidence_factor(pattern_type)
            if not is_warmup and confidence_factor < 0.5:
                # Context Logger — blocked by pattern memory
                self.logger.log_context(
                    bar_time        = candle["time"],
                    ai_bias         = ai_bias,
                    ai_env          = ai_env,
                    ai_cont_prob    = ai_cont_prob,
                    selected_strategy = pattern_type,
                    blocked_by_constraint = True,
                    constraint_reason = "PatternMemory",
                    final_execution = False
                )
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

            result = self.resolver.resolve(
                entry_price, atr, idx,
                direction=signal.get("direction", "bullish"),
                features=features,
                asset_config=self.asset_config,
                signal_bar=signal_bar,
                env=env,
                regime_probability=regime_probability
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
            # Pass ATR values for v5.0 volatility shock check
            long_atr_mean = features.get("gap_atr", atr)  # proxy for lookback ATR
            tough_mode = self.risk_manager.is_tough_conditions(
                volatility_ratio=vol_ratio,
                atr_current=atr,
                atr_lookback_mean=long_atr_mean
            )
            if is_suboptimal or force_scalp:
                tough_mode = True  # force reduced risk for suboptimal/volatility-shock context

            # If signal carries specific risk override (volatility shock), apply directly
            position_size = self.position_sizer.size(stop_dist, self.monitor.equity, tough_mode=tough_mode)

            # Performance tracking (ATR-normalized returns), skip during warmup
            if not is_warmup:
                prev_equity_len = len(self.monitor.equity)
                self.monitor.record_trade(trade_return)
                self.regime_guard.update(trade_return)
                self.risk_manager.update(trade_return, self.monitor.equity, current_time=row["open_time"])

                # v5.0: Equity recovery restore
                if len(self.monitor.equity) >= 2:
                    if self.monitor.equity[-1] >= max(self.monitor.equity[:-1]):
                        self.risk_manager.restore_risk()

            # Model update — Pattern failure memory only (model retraining handled by add_bar)
            self.controller.update_pattern_memory(pattern_type, outcome)

            # -------------------------------------------------
            # Telemetry Logging
            # -------------------------------------------------

            if not is_warmup:
                metrics = self.regime_guard.last_metrics

                # v6: use let context from the AI model
                probability = ctx["continuation_prob"]

                equity_after = self.monitor.equity[-1]
                equity_before = (
                    self.monitor.equity[-2] if len(self.monitor.equity) >= 2 else 0
                )

                # --- Context Logger: successful execution ---
                self.logger.log_context(
                    bar_time          = candle["time"],
                    ai_bias           = ai_bias,
                    ai_env            = ai_env,
                    ai_cont_prob      = ai_cont_prob,
                    selected_strategy = pattern_type,
                    blocked_by_constraint = False,
                    constraint_reason = None,
                    final_execution   = True
                )

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
                    adaptive_threshold=0.6,  # v6: fixed AI threshold (context model)
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
                    adaptive_threshold=0.6,  # v6: fixed context threshold
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
