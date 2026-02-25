# 2026-02-25 | v3.0.1 | Live paper trading runner | Writer: J.Ekrami | Co-writer: Antigravity
"""
live_runner.py

Fully independent live paper trading mode.

- Pulls historical candles from Binance to warm up engine
- Then processes only CLOSED 5m candles
- Uses single-position constraint
- Enforces session window based on asset config
- No CSV dependency
- No replay contamination
"""

import time
import re
import pandas as pd
from datetime import datetime, timedelta, timezone
from engine.core_engine import CoreEngine
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
controller = RollingController(train_window=100)
regime = RegimeGuard()
risk = RiskManager()
feed = BinanceLiveFeed()
position_sizer = PositionSizer()
logger = TelemetryLogger(
    metrics_path="logs/live_metrics.csv",
    regime_path="logs/live_regime_events.csv",
    trades_path="logs/live_trades.csv",
)

paper_equity = 0.0

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
        candle = feed.get_latest_closed_candle()
    except Exception as e:
        print(f"[LIVE] Error fetching latest candle: {e}")
        time.sleep(15)
        continue

    if not candle:
        print("[LIVE] No closed candle available yet. Sleeping...")
        time.sleep(10)
        continue

    if candle["open_time"] != last_processed_time:

        last_processed_time = candle["open_time"]

        print(f"\nNew CLOSED candle @ {candle['open_time']} | Close: {candle['close']}")

        core.add_candle({
            "time": candle["open_time"],
            "open": candle["open"],
            "high": candle["high"],
            "low": candle["low"],
            "close": candle["close"],
        })

        # Resolve open position
        outcome, pos_info = resolver.update(candle)
        if outcome is not None and pos_info is not None:
            # Normalize trade return to ATR units for risk/regime tracking
            stop_d = pos_info.get("stop_dist", 1.0)
            target_d = pos_info.get("target_dist", 2.0)
            # We need ATR for normalization — compute from recent memory
            recent_bars = [c for c in [candle] if c]  # placeholder
            atr_est = stop_d  # fallback: assume stop ≈ 1 ATR
            trade_return = (target_d / atr_est) if outcome == 1 else -(stop_d / atr_est)
            regime.update(trade_return)
            risk.update(trade_return, [paper_equity])

            used_features = pos_info.get("features")
            if used_features is not None:
                controller.update_history(used_features, outcome)
                controller.retrain_if_ready()

            # Paper equity update (scaled by position size)
            size = pos_info.get("size", 1.0)
            equity_before = paper_equity
            paper_equity = paper_equity + trade_return * size
            equity_after = paper_equity

            # Probability snapshot (may be 0 if not trained)
            probability = 0
            if controller.trained:
                probability = controller.model.predict_proba(
                    controller.scaler.transform(
                        pd.DataFrame([used_features])
                    )
                )[0][1]

            logger.log_trade(
                mode="live",
                trade_index=0,  # live mode uses time as primary key
                direction=pos_info.get("direction", "bullish"),
                decision="exit",
                entry_time=pos_info.get("entry_time"),
                entry_price=pos_info.get("entry"),
                exit_time=candle["open_time"],
                exit_price=candle["close"],
                size=size,
                atr=None,
                outcome=outcome,
                equity_before=equity_before,
                equity_after=equity_after,
                probability=probability,
                adaptive_threshold=controller.current_threshold,
                regime_paused=regime.paused,
            )

        if resolver.has_open_position():
            continue

        if not risk.allow_trading():
            print("RiskManager blocked trading.")
            continue

        if not regime.allow_trading():
            print("RegimeGuard blocked trading.")
            continue

        # --- Session Window Enforcement ---
        candle_time = candle.get("open_time") or candle.get("time")
        if candle_time is not None:
            if isinstance(candle_time, (int, float)):
                dt_utc = datetime.fromtimestamp(candle_time / 1000, timezone.utc)
            else:
                dt_utc = candle_time
            if not _is_within_session(dt_utc, ASSET_CONFIG.get("session", "24/7")):
                continue

        print(f"Current Adaptive Threshold: {controller.current_threshold:.2f}")
        
        signal = core.detect_signal()
        if signal == "tight_trading_range" or not signal:
            continue

        feature_pack = core.build_features(signal, asset_config=ASSET_CONFIG)
        if not feature_pack:
            continue

        features, atr = feature_pack

        if not controller.evaluate_trade(features):
            continue

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

        # Compute stop distance for position sizing
        from execution.resolvers import compute_stop_target
        direction = signal.get("direction", "bullish")
        _, _, stop_dist, _ = compute_stop_target(
            entry_price, atr, direction, signal_bar,
            asset_config=ASSET_CONFIG, features=features
        )

        # Position size: risk exactly 1% (or 0.3%) of account
        position_size = position_sizer.size(stop_dist, [paper_equity], tough_mode=tough_mode)

        resolver.open_position(
            entry_price=entry_price,
            atr=atr,
            features=features,
            direction=direction,
            size=position_size,
            entry_time=candle["open_time"],
            asset_config=ASSET_CONFIG,
            signal_bar=signal_bar,
        )
    else:
        print("Waiting for new CLOSED 5m candle...")

    time.sleep(60)
