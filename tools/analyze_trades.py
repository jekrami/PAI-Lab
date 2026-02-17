# 2026-02-17 | v0.1.0 | Trade log analysis utility | Writer: J.Ekrami | Co-writer: GPT-5.1
"""
analyze_trades.py

Offline analysis of logged trades and regimes.

Loads TelemetryLogger CSV outputs and produces basic slices:
- Overall performance
- By direction (bullish / bearish)
- By hour of day
"""

import pandas as pd
import os


def load_metrics(path: str = "logs/live_metrics.csv") -> pd.DataFrame | None:
    if not os.path.exists(path):
        print(f"No metrics file found at {path}")
        return None
    return pd.read_csv(path, parse_dates=["timestamp"])


def summarize_overall(df: pd.DataFrame):
    print("\n=== Overall Metrics ===")
    print(df.describe(include="all"))


def slice_by_hour(df: pd.DataFrame):
    if "timestamp" not in df.columns:
        print("timestamp column missing; cannot slice by hour.")
        return

    df["hour"] = df["timestamp"].dt.hour
    grouped = df.groupby("hour")["equity"].last().diff().fillna(0)
    print("\n=== Performance by Hour (equity change per hour bucket) ===")
    print(grouped)


def load_trades(path: str = "logs/trades.csv") -> pd.DataFrame | None:
    if not os.path.exists(path):
        print(f"No trades file found at {path}")
        return None
    return pd.read_csv(path, parse_dates=["timestamp", "entry_time", "exit_time"])


def summarize_trades(trades: pd.DataFrame):
    print("\n=== Trade Summary (All Modes) ===")
    print(trades[["direction", "size", "outcome"]].describe(include="all"))

    print("\n=== Buy vs Sell Counts ===")
    print(trades["direction"].value_counts())

    print("\n=== Total Size by Direction ===")
    print(trades.groupby("direction")["size"].sum())


if __name__ == "__main__":
    df = load_metrics()
    if df is not None:
        summarize_overall(df)
        slice_by_hour(df)

    trades = load_trades()
    if trades is not None:
        summarize_trades(trades)
