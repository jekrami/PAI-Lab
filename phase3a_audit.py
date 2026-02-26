# Phase 3A Event Density Audit
import pandas as pd
import numpy as np
from engine.core_engine import CoreEngine
from config import ASSETS, DEFAULT_ASSET

MAX_BARS = 50

def run_audit():
    print("Loading btc_5m_extended.csv...")
    df = pd.read_csv("btc_5m_extended.csv", parse_dates=["open_time"])
    asset_config = ASSETS.get("BTCUSDT", ASSETS[DEFAULT_ASSET])
    core = CoreEngine()
    
    total_bars = len(df)
    
    setups_found = 0
    resolved_count = 0
    discard_count = 0
    bull_wins = 0
    bear_wins = 0
    
    # Pre-extract data for fast lookup
    highs = df['high'].values
    lows = df['low'].values
    closes = df['close'].values
    
    # To mimic core engine state, we must feed it bar by bar
    print(f"Scanning {total_bars} bars for setups...")
    
    # Store setups as (index, atr, close, is_bullish_setup, is_bearish_setup)
    setup_events = []
    
    for idx in range(total_bars):
        row = df.iloc[idx]
        candle = {
            "time": row["open_time"],
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
        }
        core.add_candle(candle)
        
        signal = core.detect_signal()
        if signal == "tight_trading_range" or not signal:
            continue
            
        feature_pack = core.build_features(signal, asset_config=asset_config)
        if not feature_pack:
            continue
            
        features, atr, _, _ = feature_pack
        if atr <= 0:
            atr = 1.0
            
        direction = signal.get("direction", "bullish")
        setup_events.append({
            'idx': idx,
            'atr': atr,
            'close': candle['close'],
            'direction': direction
        })
    
    setups_found = len(setup_events)
    print(f"Total valid setups detected: {setups_found}")
    
    # Now evaluate event outcomes using the continuous timeframe
    direction_wins = 0
    direction_losses = 0
    whipsaws = 0

    for event in setup_events:
        idx = event['idx']
        close_now = event['close']
        atr = event['atr']
        direction = event['direction']
        
        target_up = close_now + atr
        stop_up = close_now - atr
        
        target_down = close_now - atr
        stop_down = close_now + atr
        
        bull_event = None
        bear_event = None
        
        # Scan forward up to MAX_BARS real 5m candles
        for j in range(1, MAX_BARS + 1):
            if idx + j >= total_bars:
                break
                
            f_high = highs[idx + j]
            f_low = lows[idx + j]
            
            # Check bull event
            if bull_event is None:
                if f_high >= target_up and f_low <= stop_up:
                    bull_event = 0
                elif f_high >= target_up:
                    bull_event = 1
                elif f_low <= stop_up:
                    bull_event = 0
                    
            # Check bear event
            if bear_event is None:
                if f_low <= target_down and f_high >= stop_down:
                    bear_event = 0
                elif f_low <= target_down:
                    bear_event = 1
                elif f_high >= stop_down:
                    bear_event = 0
                    
            if bull_event is not None and bear_event is not None:
                break
                
        if bull_event is None or bear_event is None:
            discard_count += 1
        else:
            resolved_count += 1
            if bull_event == 0 and bear_event == 0:
                whipsaws += 1
                direction_losses += 1
            else:
                if direction == "bullish":
                    if bull_event == 1: direction_wins += 1
                    else: direction_losses += 1
                else: # bearish
                    if bear_event == 1: direction_wins += 1
                    else: direction_losses += 1

    print("\n" + "="*50)
    print("PHASE 3A EVENT DENSITY AUDIT (100k bars)")
    print("="*50)
    print(f"Total valid setups           = {setups_found}")
    print(f"Total resolved ATR events    = {resolved_count}")
    print(f"Total discarded (unresolved) = {discard_count}")
    
    if setups_found > 0:
        print(f"Discard %                    = {discard_count / setups_found * 100:.1f}%")
        
    if resolved_count > 0:
        print(f"Directional Win %            = {direction_wins / resolved_count * 100:.1f}%")
        print(f"Directional Loss %           = {direction_losses / resolved_count * 100:.1f}%")
        print(f"Whipsaw %                    = {whipsaws / resolved_count * 100:.1f}%")
        
    freq = (resolved_count / total_bars) * 10000
    print(f"Event frequency per 10k bars = {freq:.1f}")

if __name__ == "__main__":
    run_audit()
