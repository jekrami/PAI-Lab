# 2026-02-26 | v3.2.0 | Live paper trading runner | Writer: J.Ekrami | Co-writer: Antigravity
"""
live_runner.py

Fully independent live paper trading mode.

- Pulls historical candles from Binance to warm up engine
- Then processes only CLOSED 5m candles
- Uses single-position constraint
- Enforces session window based on asset config
- No CSV dependency
- No replay contamination
- Phase-2: AI gating via get_context() / get_phase2_gates()
"""

import time
import re
import pandas as pd
from datetime import datetime, timedelta, timezone
from engine.core_engine import CoreEngine
from engine.sandbox import SimulationSandbox
from execution.resolvers import LiveResolver
from intelligence.rolling_controller import RollingController
from execution.regime_guard import RegimeGuard
from execution.risk_manager import RiskManager
from execution.position_sizer import PositionSizer
from execution.telemetry_logger import TelemetryLogger
from config import ASSETS, DEFAULT_ASSET
from data.live_feed import BinanceLiveFeed

# --- Asset Configuration ---
ASSET_ID = DEFAULT_ASSET  # Change to "XAUUSD" for Gold
ASSET_CONFIG = ASSETS.get(ASSET_ID, ASSETS[DEFAULT_ASSET])

# EST offset (UTC-5 fixed proxy)
EST_OFFSET = timedelta(hours=-5)


def _is_within_session(dt_utc, session_str):
    """Check if UTC time falls within the asset's session window."""
    if session_str == "24/7":
        return True
    # Parse "HH:MM-HH:MM_TZ" format
    match = re.match(r"(\d{2}):(\d{2})-(\d{2}):(\d{2})_EST", session_str)
    if not match:
        return True  # Unknown format → allow
    start_h, start_m = int(match.group(1)), int(match.group(2))
    end_h, end_m = int(match.group(3)), int(match.group(4))
    dt_est = dt_utc + EST_OFFSET
    current_minutes = dt_est.hour * 60 + dt_est.minute
    start_minutes = start_h * 60 + start_m
    end_minutes = end_h * 60 + end_m
    return start_minutes <= current_minutes <= end_minutes


core = CoreEngine()
resolver = LiveResolver()
sandbox = SimulationSandbox(n_iterations=1000, max_path_length=50)
controller = RollingController(train_window=300, retrain_every=50)
regime = RegimeGuard()
risk = RiskManager()
feed = BinanceLiveFeed()
position_sizer = PositionSizer()
logger = TelemetryLogger(
    metrics_path="logs/live_metrics.csv",
    regime_path="logs/live_regime_events.csv",
    trades_path="logs/live_trades.csv",
)

paper_equity = 100.0  # Base logic uses 100 for percentage
paper_equity_series = [paper_equity]

print("Initializing from Binance history...")

# 🔹 Warm-up from live source
historical = feed.get_historical_candles(limit=200)
if not historical:
    print("Historical warm-up failed (no data). Retrying in 60 seconds...")
    time.sleep(60)
    historical = feed.get_historical_candles(limit=200)

for c in historical:
    core.add_candle({
        "time": c["open_time"],
        "open": c["open"],
        "high": c["high"],
        "low": c["low"],
        "close": c["close"],
    })

print("Warm-up complete. Starting LIVE PAPER mode...")

last_processed_time = None

while True:

    try:
        candle_1m = feed.get_latest_closed_candle(interval="1m")
    except Exception as e:
        print(f"[LIVE] Error fetching latest 1m candle: {e}")
        time.sleep(15)
        continue

    if not candle_1m:
        print("[LIVE] No closed 1m candle available yet. Sleeping...")
        time.sleep(10)
        continue

    if candle_1m["open_time"] != last_processed_time:
        last_processed_time = candle_1m["open_time"]
        
        # Determine UTC time
        candle_dt = candle_1m.get("open_time")
        dt_utc = datetime.fromtimestamp(candle_dt / 1000, timezone.utc)

        # 1. Provide 1m candle to the Resolver for micro-entry scans and trade management
        outcome, pos_info = resolver.update(candle_1m)



        if outcome is not None and pos_info is not None:
            # Normalize trade return to ATR units for risk/regime tracking
            stop_d = pos_info.get("stop_dist", 1.0)
            target_d = pos_info.get("target_dist", 2.0)
            atr_est = stop_d  # fallback: assume stop ≈ 1 ATR
            trade_return = (target_d / atr_est) if outcome == 1 else -(stop_d / atr_est)
            # Paper equity update (scaled by position size)
            size = pos_info.get("size", 1.0)
            equity_before = paper_equity
            paper_equity = paper_equity + trade_return * size
            paper_equity_series.append(paper_equity)
            equity_after = paper_equity

            regime.update(trade_return)
            risk.update(trade_return, paper_equity_series, current_time=dt_utc)

            used_features = pos_info.get("features")

            # --- Phase-2: Feed trade result into performance trackers ---
            setup_type = pos_info.get("setup_type", "")
            ai_env = pos_info.get("ai_env", "TRANSITION")
            controller.update_trade_trackers(setup_type, ai_env, trade_return)

            # Also update pattern memory (v5 retained)
            if setup_type:
                controller.update_pattern_memory(setup_type, outcome)

            # Phase-2/3 Setup logging handled above

            # --- Phase-2: Get AI context probabilities for logging ---
            ai_context = controller.get_context(used_features) if used_features else {}
            confidence = ai_context.get("confidence", 0.0)
            cont_prob = ai_context.get("continuation_prob", 0.5)

            logger.log_trade(
                mode="live",
                trade_index=0,  # live mode uses time as primary key
                direction=pos_info.get("direction", "bullish"),
                decision="exit",
                entry_time=pos_info.get("entry_time"),
                entry_price=pos_info.get("entry"),
                exit_time=candle_1m["open_time"],
                exit_price=candle_1m["close"],
                size=size,
                atr=None,
                outcome=outcome,
                equity_before=equity_before,
                equity_after=equity_after,
                probability=confidence,
                adaptive_threshold=0.60,   # Phase-2 fixed gate
                regime_paused=regime.paused,
            )

        if resolver.has_open_position():
            continue

        if not risk.allow_trading(current_time=dt_utc):
            print("RiskManager blocked trading (cooldown/drawdown limits).")
            continue

        if not regime.allow_trading():
            print("RegimeGuard blocked trading.")
            continue

        # --- Session Window Enforcement ---
        if not _is_within_session(dt_utc, ASSET_CONFIG.get("session", "24/7")):
            continue

        # 2. Check if a 5-minute boundary was just crossed 
        # (e.g., if the 1m candle that just closed was the 04:00-04:59 minute, closing exactly at 05:00)
        # In Binance, the 1m candle at '04' closes at '05'. So dt_utc.minute % 5 == 4 means the 5m candle just finished.
        if dt_utc.minute % 5 != 4:
            continue
            
        print(f"\n[LIVE] 5-minute interval complete at {dt_utc.strftime('%H:%M')}. Fetching 5m candle...")
        
        # Give Binance API an extra second to index the 5m candle properly
        time.sleep(1.5)
        try:
            candle = feed.get_latest_closed_candle(interval="5m")
            if not candle:
                continue
            # Ensure "time" key exists for Al Brooks detectors
            candle["time"] = candle["open_time"]
        except Exception as e:
            print(f"[LIVE] Error fetching 5m candle: {e}")
            continue
            
        core.add_candle(candle)

        signal = core.detect_signal()
        if signal == "tight_trading_range" or not signal:
            continue

        feature_pack = core.build_features(signal, asset_config=ASSET_CONFIG)
        if not feature_pack:
            continue

        features, atr, is_suboptimal, env = feature_pack

        # --- Phase-2: run controller add_bar for walk-forward retraining ---
        market_index = len(controller.market_buffer) - 1
        controller.add_bar(features, candle, atr, market_index=market_index)

        # --- Phase-2: AI context + gating ---
        ai_context = controller.get_context(features)
        confidence  = ai_context.get("confidence", 0.0)
        cont_prob   = ai_context.get("continuation_prob", 0.5)
        ai_env      = ai_context.get("environment", "TRANSITION")
        setup_type  = signal.get("setup_type", "") if isinstance(signal, dict) else str(signal)

        gate = controller.get_phase2_gates(setup_type, ai_env, confidence, cont_prob)
        if gate["block"]:
            print(f"[Phase-2] Trade blocked: {gate['reason']} "
                  f"(conf={confidence:.2f}, cont={cont_prob:.2f})")
            continue

        print(f"[AI] env={ai_env} conf={confidence:.2f} cont={cont_prob:.2f} | setup={setup_type}")

        entry_price = candle["high"]

        # Build signal bar for stop placement (Al Brooks: stop at signal bar extreme)
        signal_bar = {
            "high": candle["high"],
            "low": candle["low"],
            "open": candle["open"],
            "close": candle["close"],
        }

        # Determine tough conditions for reduced position sizing
        vol_ratio = features.get("volatility_ratio", 1.0)
        tough_mode = risk.is_tough_conditions(volatility_ratio=vol_ratio)
        if is_suboptimal:
            tough_mode = True  # Force reduced position size for context penalty

        # Compute stop distance for position sizing
        from execution.resolvers import compute_stop_target
        direction = signal.get("direction", "bullish") if isinstance(signal, dict) else "bullish"
        _, _, stop_dist, target_dist = compute_stop_target(
            entry_price, atr, direction, signal_bar,
            asset_config=ASSET_CONFIG, features=features, env=env
        )

        # -------------------------------------------------
        # Phase 1: Local Synthetic Backtest (Simulation Sandbox)
        # -------------------------------------------------
        mem_data = core.memory.data()
        if len(mem_data) > 0:
            mem_df = pd.DataFrame(mem_data)
            lsb_result = sandbox.evaluate(
                memory_df=mem_df,
                signal_context=signal,
                entry_price=entry_price,
                stop_dist=stop_dist,
                target_dist=target_dist
            )
            if not lsb_result["approved"]:
                print(f"[Phase-1 LSB] Trade blocked: Pp={lsb_result['pp']:.2f}, EV={lsb_result['ev']:.2f}")
                continue

        # V8 Phase 3: The Governor layer
        observation_mode = risk.is_observation_mode()
        position_size = position_sizer.size(
            stop_dist, 
            paper_equity_series, 
            tough_mode=tough_mode,
            ai_confidence=confidence,
            observation_mode=observation_mode
        )

        # Store ai_env in the position so it can be recovered on trade close
        resolver.open_position(
            entry_price=entry_price,
            atr=atr,
            features=features,
            direction=direction,
            size=position_size,
            entry_time=candle["open_time"],
            asset_config=ASSET_CONFIG,
            signal_bar=signal_bar,
            env=env,
        )
    else:
        print("Waiting for new CLOSED 5m candle...")

    time.sleep(60)
