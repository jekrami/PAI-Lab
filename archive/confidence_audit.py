# Phase 3C Confidence-Expectancy Analysis
import pandas as pd
import numpy as np
from engine.core_engine import CoreEngine
from config import ASSETS, DEFAULT_ASSET

MAX_BARS = 75  # As specified in Phase 3B

def run_audit():
    print("Loading btc_5m_extended.csv...")
    df = pd.read_csv("btc_5m_extended.csv", parse_dates=["open_time"])
    asset_config = ASSETS.get("BTCUSDT", ASSETS[DEFAULT_ASSET])
    core = CoreEngine()
    
    total_bars = len(df)
    
    # Pre-extract data for fast lookup
    highs = df['high'].values
    lows = df['low'].values
    times = df['open_time']
    
    # We need to map time -> (direction, atr) to get true outcomes
    setup_outcomes = {}
    
    print(f"Scanning {total_bars} bars for setups to compute true outcomes...")
    
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
        
        close_now = candle['close']
        # Stage-1 Pivot: 0.7 ATR target, 1 ATR stop (matches _compute_labels)
        target_up = close_now + 0.7 * atr
        stop_up = close_now - atr
        target_down = close_now - 0.7 * atr
        stop_down = close_now + atr
        
        bull_event = None
        bear_event = None
        
        for j in range(1, MAX_BARS + 1):
            if idx + j >= total_bars:
                break
                
            f_high = highs[idx + j]
            f_low = lows[idx + j]
            
            if bull_event is None:
                if f_high >= target_up and f_low <= stop_up:
                    bull_event = 0
                elif f_high >= target_up:
                    bull_event = 1
                elif f_low <= stop_up:
                    bull_event = 0
                    
            if bear_event is None:
                if f_low <= target_down and f_high >= stop_down:
                    bear_event = 0
                elif f_low <= target_down:
                    bear_event = 1
                elif f_high >= stop_down:
                    bear_event = 0
                    
            if bull_event is not None and bear_event is not None:
                break
                
        # Determine R outcome for the setup's intended direction
        r_outcome = None
        if bull_event is not None and bear_event is not None:
            if direction == "bullish":
                r_outcome = 1.0 if bull_event == 1 else -1.0
            else:
                r_outcome = 1.0 if bear_event == 1 else -1.0
        elif bull_event == 0 and bear_event == 0:
            r_outcome = -1.0 # Whipsawed out either way
            
        setup_outcomes[str(candle["time"])] = r_outcome

    print("Loading AI context predictions...")
    try:
        df_ai = pd.read_csv("logs/ai_context.csv")
    except Exception as e:
        print(f"Error loading logs/ai_context.csv: {e}")
        return

    # Clean the bar_time in ai_context to match format
    # ai_context saves it natively using str(candle["time"]) likely with +00:00
    df_ai['bar_time_str'] = df_ai['bar_time'].astype(str)
    
    # Convert true outcome dict to DataFrame
    df_outcomes = pd.DataFrame(list(setup_outcomes.items()), columns=['bar_time_str', 'true_R'])
    
    # Inner join on time string
    df_merged = pd.merge(df_ai, df_outcomes, on='bar_time_str', how='inner')
    
    print(f"Matched {len(df_merged)} AI predictions with true outcomes.")
    
    if len(df_merged) == 0:
        print("No matches. Check time formats. Here's a sample:")
        print("AI Times:", df_ai['bar_time_str'].head().tolist())
        print("Setup Times:", list(setup_outcomes.keys())[:5])
        return

    # Filter out NaNs (unresolved events)
    df_resolved = df_merged.dropna(subset=['true_R']).copy()
    
    # Create fixed bins (0.4-0.5, 0.5-0.6, 0.6-0.7, 0.7-0.8, 0.8-0.9)
    bins = [0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    labels = ["0.40–0.50", "0.50–0.60", "0.60–0.70", "0.70–0.80", "0.80–0.90", "0.90–1.00"]
    
    df_resolved['conf_bin'] = pd.cut(df_resolved['ai_confidence'], bins=bins, labels=labels, right=False)
    
    # We only care about bins from 0.4 up
    df_analysis = df_resolved[df_resolved['ai_confidence'] >= 0.4].copy()
    
    results = []
    for bin_label in labels:
        subset = df_analysis[df_analysis['conf_bin'] == bin_label]
        count = len(subset)
        if count == 0:
            results.append([bin_label, count, 0.0, 0.0])
            continue
            
        wins = len(subset[subset['true_R'] > 0])
        win_rate = wins / count
        avg_r = subset['true_R'].mean()
        
        results.append([bin_label, count, win_rate, avg_r])
        
    print("\n" + "="*50)
    print("CONFIDENCE-EXPECTANCY ANALYSIS (All unfiltered predictions)")
    print("="*50)
    print(f"| {'Confidence Bin':<15} | {'Count':<6} | {'Win Rate':<8} | {'Avg R':<7} |")
    print("|" + "-"*17 + "|" + "-"*8 + "|" + "-"*10 + "|" + "-"*9 + "|")
    
    for r in results:
        if r[1] > 0:
            print(f"| {r[0]:<15} | {r[1]:<6} | {r[2]*100:>5.1f}%   | {r[3]:>6.2f}R |")
        else:
            print(f"| {r[0]:<15} | {r[1]:<6} | {'-':>6}   | {'-':>7} |")
            

if __name__ == "__main__":
    run_audit()
