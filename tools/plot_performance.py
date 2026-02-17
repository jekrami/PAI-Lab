# 2026-02-17 | v0.1.0 | Performance plotting utility | Writer: J.Ekrami | Co-writer: GPT-5.1
"""
plot_performance.py

Minimal introspection script to visualize backtest performance.

Reads PerformanceMonitor equity series saved by StateManager (if available)
and plots the equity curve using matplotlib.
"""

import os
import pickle

import matplotlib.pyplot as plt


def load_equity_from_state(state_path="state.pkl"):
    """
    Load equity curve from persisted state (if present).
    """
    if not os.path.exists(state_path):
        print(f"No state file found at {state_path}")
        return None

    with open(state_path, "rb") as f:
        state = pickle.load(f)

    monitor_state = state.get("monitor")
    if not monitor_state:
        print("No monitor state found in persisted state.")
        return None

    return monitor_state.get("equity")


def plot_equity(equity):
    """
    Plot simple equity curve.
    """
    if not equity:
        print("Empty equity series, nothing to plot.")
        return

    plt.figure(figsize=(10, 5))
    plt.plot(equity, label="Equity")
    plt.xlabel("Trade #")
    plt.ylabel("Equity (ATR units)")
    plt.title("PAI-Lab Backtest Equity Curve")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    equity = load_equity_from_state()
    if equity is not None:
        plot_equity(equity)

