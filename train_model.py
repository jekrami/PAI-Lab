# 2026-02-27 | Phase 6 v1.1.1 | Offline AI Training | Writer: J.Ekrami | Co-writer: Antigravity
"""
train_model.py

Offline AI model training script for PAI-Lab.

Changes v1.1.1:
  - Added event density audit metrics (win/loss %, frequency per 10k bars, starvation check).
Changes v1.1.0:
  - compute_labels now uses signal-direction-aware entry/stop/target
    that mirrors BacktestResolver's actual trade structure.
  - cont label now reflects the signal's own direction outcome
    (bullish → target above, bearish → target below), not bar color.
  - direction_buffer passed through to compute_labels.
"""
import argparse
import os
import pandas as pd
import numpy as np
from datetime import datetime, timezone

from config import *
from engine.core_engine import CoreEngine
from core.feature_extractor import extract_features
from intelligence.ai_context_model import AIContextModel
from execution.resolvers import BacktestResolver

MAX_BARS = 50


def compute_labels(candle_buffer, atr_buffer, market_indices_buffer, market_buffer, direction_buffer):
    """
    Generates path-dependent outcome labels aligned to how BacktestResolver actually trades.

    Entry:   signal bar high (bullish) / low (bearish)  — same as main.py
    Stop:    signal bar low  (bullish) / high (bearish) with 0.5*ATR floor
    Target:  entry +/- max(1.5 * stop_dist, 1.0 * ATR)

    cont label = 1 if the signal's direction hits target before stop, else 0.
    bias/env labels use generic ±ATR scan (market direction classifier).
    """
    n = len(candle_buffer)
    bias_list = []
    env_list  = []
    cont_list = []

    for i in range(n):
        market_idx = market_indices_buffer[i]
        bar        = candle_buffer[i]
        atr        = atr_buffer[i] if atr_buffer[i] > 0 else 1.0
        direction  = direction_buffer[i]   # "bullish" or "bearish"

        # --- Entry/stop/target: mirror BacktestResolver ---
        if direction == "bullish":
            entry       = bar["high"]
            stop_dist   = max(entry - bar["low"], 0.5 * atr)
            target_dist = max(stop_dist * 1.5, atr)
            target_price = entry + target_dist
            stop_price   = entry - stop_dist
        else:
            entry       = bar["low"]
            stop_dist   = max(bar["high"] - entry, 0.5 * atr)
            target_dist = max(stop_dist * 1.5, atr)
            target_price = entry - target_dist
            stop_price   = entry + stop_dist

        # --- Generic ±ATR reference for bias/env labels ---
        ref_target_up   = bar["close"] + atr
        ref_stop_up     = bar["close"] - atr
        ref_target_down = bar["close"] - atr
        ref_stop_down   = bar["close"] + atr

        bull_event = None
        bear_event = None
        cont_event = None

        for j in range(1, MAX_BARS + 1):
            if market_idx + j >= len(market_buffer):
                break

            fb   = market_buffer[market_idx + j]
            f_hi = fb["high"]
            f_lo = fb["low"]

            # bias/env: generic ±ATR first-touch
            if bull_event is None:
                if f_hi >= ref_target_up and f_lo <= ref_stop_up:
                    bull_event = 0
                elif f_hi >= ref_target_up:
                    bull_event = 1
                elif f_lo <= ref_stop_up:
                    bull_event = 0

            if bear_event is None:
                if f_lo <= ref_target_down and f_hi >= ref_stop_down:
                    bear_event = 0
                elif f_lo <= ref_target_down:
                    bear_event = 1
                elif f_hi >= ref_stop_down:
                    bear_event = 0

            # cont: signal-direction-aware real stop/target
            if cont_event is None:
                if direction == "bullish":
                    if f_hi >= target_price and f_lo <= stop_price:
                        cont_event = 0   # both same bar → conservative: loss
                    elif f_hi >= target_price:
                        cont_event = 1
                    elif f_lo <= stop_price:
                        cont_event = 0
                else:
                    if f_lo <= target_price and f_hi >= stop_price:
                        cont_event = 0
                    elif f_lo <= target_price:
                        cont_event = 1
                    elif f_hi >= stop_price:
                        cont_event = 0

            if bull_event is not None and bear_event is not None and cont_event is not None:
                break

        # --- Map to AI targets ---
        if bull_event is None or bear_event is None or cont_event is None:
            bias_list.append(np.nan)
            env_list.append(np.nan)
            cont_list.append(np.nan)
        else:
            if bull_event == 1 and bear_event == 0:
                bias = 1
            elif bear_event == 1 and bull_event == 0:
                bias = -1
            else:
                bias = 0

            env = 1 if (bull_event == 1 or bear_event == 1) else 0
            bias_list.append(bias)
            env_list.append(env)
            cont_list.append(cont_event)

    return pd.DataFrame({"bias": bias_list, "env": env_list, "cont": cont_list})


def train_offline_model(data_prefix="btcusdt", asset_id=DEFAULT_ASSET):
    asset_config = ASSETS.get(asset_id, ASSETS[DEFAULT_ASSET])

    path_5m = f"{data_prefix}_5m.csv"
    if not os.path.exists(path_5m):
        raise FileNotFoundError(f"Missing {path_5m}")
    print(f"Loading {path_5m}...")
    df_5m = pd.read_csv(path_5m, parse_dates=["open_time"]).set_index("open_time").sort_index()

    core = CoreEngine()

    feature_buffer        = []
    candle_buffer         = []
    atr_buffer            = []
    direction_buffer      = []
    market_indices_buffer = []
    market_buffer         = []

    print("Extracting features and generating signals...")
    for idx, (current_time, row_5m) in enumerate(df_5m.iterrows()):
        candle = {
            "time":  current_time,
            "open":  float(row_5m["open"]),
            "high":  float(row_5m["high"]),
            "low":   float(row_5m["low"]),
            "close": float(row_5m["close"]),
        }

        market_index = len(market_buffer)
        market_buffer.append(candle)
        core.add_candle(candle)

        signal = core.detect_signal()
        if signal == "tight_trading_range" or not signal:
            continue

        feature_pack = core.build_features(signal, asset_config=asset_config)
        if not feature_pack:
            continue

        features, atr, is_suboptimal, env = feature_pack

        direction = signal.get("direction", "bullish") if isinstance(signal, dict) else "bullish"

        feature_buffer.append(features)
        candle_buffer.append(candle)
        atr_buffer.append(atr)
        direction_buffer.append(direction)
        market_indices_buffer.append(market_index)

    print(f"Extracted {len(feature_buffer)} signals. Computing labels...")
    df_labels = compute_labels(
        candle_buffer, atr_buffer, market_indices_buffer, market_buffer, direction_buffer
    )
    df_features = pd.DataFrame(feature_buffer)

    df_combined = pd.concat([df_features, df_labels], axis=1)
    df_clean = df_combined.dropna(subset=["bias", "env", "cont"]).copy()

    total_signals  = len(df_combined)
    resolved_count = len(df_clean)
    discard_count  = total_signals - resolved_count

    print(f"Total signals: {total_signals}, Resolved: {resolved_count}, Discarded: {discard_count}")

    # Event Density Audit Metrics
    if resolved_count > 0:
        wr = df_clean["cont"].mean()
        loss_pct = 1.0 - wr
        print(f"Resolved events Win-rate: {wr:.1%}, Loss-rate: {loss_pct:.1%}")
        
        total_bars = len(df_5m)
        freq_per_10k_bars = resolved_count / (total_bars / 10000.0) if total_bars > 0 else 0
        print(f"Resolved event frequency: {freq_per_10k_bars:.2f} per 10,000 bars")
        
        starvation_status = "WARNING (Starvation)" if resolved_count < 300 else "OK (Adequate)"
        print(f"Starvation Check: {starvation_status}")

    if resolved_count < 100:
        print("Not enough resolved signals to train the model. Exiting.")
        return

    df_features_clean = df_clean[df_features.columns]
    df_labels_clean   = df_clean[["bias", "env", "cont"]]

    print("Training AIContextModel...")
    model   = AIContextModel()
    success = model.train(df_features_clean, df_labels_clean)

    if success:
        os.makedirs("state", exist_ok=True)
        model_path  = f"state/ai_model_{asset_id}.pkl"
        scaler_path = f"state/ai_scaler_{asset_id}.pkl"
        model.save(model_path, scaler_path)
        print(f"Model saved to {model_path} and {scaler_path}")
    else:
        print("Model training failed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PAI-Lab Offline AI Training")
    parser.add_argument("--asset",       default="BTCUSDT", help="Asset ID")
    parser.add_argument("--data_prefix", default="btcusdt",  help="Prefix of the MTF CSV files")
    args = parser.parse_args()

    train_offline_model(args.data_prefix, args.asset)
