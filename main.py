# 2026-02-26 | v6.1.1 | Backtest engine runner | Writer: J.Ekrami | Co-writer: Antigravity
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

import argparse
import glob
import os
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
from engine.sandbox import SimulationSandbox


# =====================================================
# ENGINE RUNNER
# =====================================================

class PAILabEngine:

    def __init__(self, data_path_prefix, asset_id=DEFAULT_ASSET, warm_up_bars: int = 40000):
        self.asset_id = asset_id
        self.asset_config = ASSETS.get(asset_id, ASSETS[DEFAULT_ASSET])
        self.warm_up_bars = warm_up_bars
        
        # Load multiple timeframes
        print("Loading multi-timeframe datasets...")
        self.dfs = {}
        for interval in ["1m", "5m", "15m", "1h"]:
            path = f"{data_path_prefix}_{interval}.csv"
            if os.path.exists(path):
                self.dfs[interval] = pd.read_csv(path, parse_dates=["open_time"]).set_index("open_time").sort_index()
                print(f" Loaded {interval}: {len(self.dfs[interval])} bars")
            else:
                raise FileNotFoundError(f"Missing required timeframe data: {path}")
                
        # Find intersecting time bounds
        start_time = max(df.index.min() for df in self.dfs.values())
        end_time = min(df.index.max() for df in self.dfs.values())
        print(f"Aligning timeframes from {start_time} to {end_time}")
        
        # Trim all to intersection bounds
        for interval in self.dfs:
            self.dfs[interval] = self.dfs[interval].loc[start_time:end_time]

        self.core = CoreEngine()

        self.controller = RollingController(train_window=300, retrain_every=50)
        self.monitor = PerformanceMonitor()
        self.regime_guard = RegimeGuard(window=20)
        self.logger = TelemetryLogger()
        self.state_manager = StateManager(asset_id=self.asset_id)
        self.last_index = 0
        self.state_manager.load(self)
        self.risk_manager = RiskManager()
        self.resolver = BacktestResolver(self.dfs["1m"])
        self.sandbox = SimulationSandbox(n_iterations=1000, max_path_length=50)

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

        print("Starting MTF live simulation...\n")

        # Master Iterator is the 1m chart (highest temporal resolution)
        df_1m = self.dfs["1m"]
        
        # Keep track of the last processed indices for higher timeframes
        last_5m_idx = 0
        df_5m = self.dfs["5m"]
        df_5m_times = df_5m.index.values

        for idx, (current_time, row_1m) in enumerate(df_1m.iterrows()):
            if idx < self.last_index: # Skip already processed rows if state was loaded
                continue

            # Mark warmup mode on controller to suppress console print noise
            self.controller._warmup_mode = (idx < self.warm_up_bars)
            is_warmup = (idx < self.warm_up_bars)

            # --- MTF Synchronization Step ---
            # Wait for the next 5m bar to close.
            # A 5m bar that opens at 00:00 closes at 00:04:59.
            # So it becomes fully formed/closed at 00:05.
            # Thus, we process the 5m bar opening at 00:00 when the 1m loop hits 00:05.
            
            # Find if there is a 5m bar that just closed exactly at `current_time`
            time_val = current_time.to_numpy()
            
            # Since Pandas indexes are arrays, we check if current_time corresponds to a 5m closing boundary
            # The 5m candle that "closed" at current_time is the one that opened 5 minutes ago
            candle_open_time = current_time - pd.Timedelta(minutes=5)
            
            # For simplicity in this backtest step, we process signals precisely when the 5m candle closes.
            # Meaning we only run the heavy feature generation on the 5m boundary.
            if current_time.minute % 5 != 0:
                continue

            # Ensure the 5m candle actually exists in our dataset
            if candle_open_time not in df_5m.index:
                continue

            row_5m = df_5m.loc[candle_open_time]

            candle = {
                "time": candle_open_time,
                "open": float(row_5m["open"]),
                "high": float(row_5m["high"]),
                "low": float(row_5m["low"]),
                "close": float(row_5m["close"]),
            }

            self.core.add_candle(candle)
            self.controller.add_market_bar(candle)

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

            # v6.1: Disable underperforming setup types
            if pattern_type in ("breakout", "third_entry"):
                continue

            is_warmup = (idx < self.warm_up_bars)
            if not is_warmup:
                print(f"[{candle_open_time}] Signal: {pattern_type}")

            # Survival layer first (capital protection)
            if not is_warmup and not self.risk_manager.allow_trading(current_time=candle_open_time):
                #print("RiskManager blocked")
                continue
            # Then regime guard (statistical weakness)
            if not is_warmup and not self.regime_guard.allow_trading():
                #print("RegimeGuard blocked")
                continue

            # 🔹 Probability Controller: v6 uses Strategy Selector gate instead of evaluate_trade
            # --- Phase-1 v6: Feed bar into controller for labeling + training ---
            market_index = len(self.controller.market_buffer) - 1
            self.controller.add_bar(features, candle, atr, market_index=market_index)

            # --- Phase-2 v6: Get AI Context ---
            ctx = self.controller.get_context(features)
            ai_bias        = ctx["bias"]
            ai_env         = ctx["environment"]
            ai_cont_prob   = ctx["continuation_prob"]
            ai_confidence  = ctx.get("confidence", 0.5)

            # --- Phase-2 v6: ALL gating (confidence + continuation + regime + setup + pattern) ---
            gate = self.controller.get_phase2_gates(
                setup_type = pattern_type,
                ai_env     = ai_env,
                confidence = ai_confidence,
                cont_prob  = ai_cont_prob
            )
            # Also apply pattern memory as an additional gate layer
            confidence_factor = self.controller.pattern_confidence_factor(pattern_type)
            if not gate["block"] and not is_warmup and confidence_factor < 0.5:
                gate = {"block": True, "reason": "PatternMemory"}

            if not is_warmup and gate["block"]:
                self.logger.log_context(
                    bar_time              = candle["time"],
                    ai_bias               = ai_bias,
                    ai_env                = ai_env,
                    ai_cont_prob          = ai_cont_prob,
                    ai_confidence         = ai_confidence,
                    selected_strategy     = pattern_type,
                    blocked_by_constraint = True,
                    constraint_reason     = gate["reason"],
                    final_execution       = False
                )
                continue

            # Al Brooks: enter on break of signal bar
            #   Bullish → enter at signal bar high (breakout above)
            #   Bearish → enter at signal bar low (breakdown below)
            direction = signal.get("direction", "bullish")
            entry_price = float(row_5m["high"]) if direction == "bullish" else float(row_5m["low"])

            # Build signal bar for stop placement
            signal_bar = {
                "high": float(row_5m["high"]),
                "low": float(row_5m["low"]),
                "open": float(row_5m["open"]),
                "close": float(row_5m["close"]),
            }

            result = self.resolver.resolve(
                entry_price, atr, current_time,
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
            # Phase 1: Local Synthetic Backtest (Simulation Sandbox)
            # -------------------------------------------------
            if not is_warmup:
                # Get the last 500 bars context (or as much as available)
                memory_data = self.core.memory.data()
                if len(memory_data) > 0:
                    mem_df = pd.DataFrame(memory_data)
                    lsb_result = self.sandbox.evaluate(
                        memory_df=mem_df,
                        signal_context=signal,
                        entry_price=entry_price,
                        stop_dist=stop_dist,
                        target_dist=target_dist
                    )
                    if not lsb_result["approved"]:
                        self.logger.log_context(
                            bar_time              = candle["time"],
                            ai_bias               = ai_bias,
                            ai_env                = ai_env,
                            ai_cont_prob          = ai_cont_prob,
                            ai_confidence         = ai_confidence,
                            selected_strategy     = pattern_type,
                            blocked_by_constraint = True,
                            constraint_reason     = f"LSB Failed (Pp={lsb_result['pp']:.2f}, EV={lsb_result['ev']:.2f})",
                            final_execution       = False
                        )
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

            # V8 Phase 3: The Governor layer
            observation_mode = self.risk_manager.is_observation_mode()
            
            # If signal carries specific risk override (volatility shock), apply directly
            position_size = self.position_sizer.size(
                stop_dist, 
                self.monitor.equity, 
                tough_mode=tough_mode,
                ai_confidence=ai_confidence,
                observation_mode=observation_mode
            )

            # Performance tracking (ATR-normalized returns), skip during warmup
            if not is_warmup:
                prev_equity_len = len(self.monitor.equity)
                self.monitor.record_trade(trade_return)
                self.regime_guard.update(trade_return)
                self.risk_manager.update(trade_return, self.monitor.equity, current_time=candle_open_time)

                # v5.0: Equity recovery restore
                if len(self.monitor.equity) >= 2:
                    if self.monitor.equity[-1] >= max(self.monitor.equity[:-1]):
                        self.risk_manager.restore_risk()

            if not is_warmup:
                # Phase-2: Feed realized R into Setup and Regime trackers (live only)
                self.controller.update_trade_trackers(pattern_type, ai_env, trade_return)
                # Pattern failure memory (live only)
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
                    ai_confidence     = ai_confidence,
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

        # Phase-2: Post-run analysis reports
        from intelligence.analysis_tools import (
            calibration_test, feature_importance_report, setup_regime_report
        )
        print()
        setup_regime_report(self.controller)
        feature_importance_report(self.controller)
        calibration_test()

# =====================================================
# ENTRY POINT
# =====================================================

def _do_refresh(asset_id: str = "BTCUSDT"):
    """
    --refresh: wipe all persisted state and generated log files.
    Keeps raw data CSVs (btc_5m_extended.csv, truth_dataset.csv).
    """
    removed = []

    # 1. Engine state pickle(s)
    for f in glob.glob(f"state/engine_state_*.pkl"):
        os.remove(f)
        removed.append(f)

    # 2. Generated log CSVs (metrics, trades, regime events, ai context)
    log_patterns = [
        "logs/metrics*.csv",
        "logs/trades*.csv",
        "logs/regime_events*.csv",
        "logs/ai_context*.csv",
        "logs/live_*.csv",
    ]
    for pattern in log_patterns:
        for f in glob.glob(pattern):
            os.remove(f)
            removed.append(f)

    if removed:
        print("[Refresh] Removed:")
        for f in removed:
            print(f"   {f}")
    else:
        print("[Refresh] Nothing to remove (already clean).")
    print()


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="PAI-Lab backtest engine")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Delete all saved state (.pkl) and generated log CSVs before running."
    )
    parser.add_argument(
        "--asset",
        default="BTCUSDT",
        help="Asset ID to run (default: BTCUSDT)"
    )
    parser.add_argument(
        "--data_prefix",
        default="btcusdt",
        help="Prefix of the CSVs downloaded by MTF script (default: btcusdt)"
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=30000,
        help="Number of bars to use for context building without trading (default: 30000)"
    )
    args = parser.parse_args()

    if args.refresh:
        _do_refresh(asset_id=args.asset)

    engine = PAILabEngine(args.data_prefix, asset_id=args.asset, warm_up_bars=args.warmup)
    engine.run()
