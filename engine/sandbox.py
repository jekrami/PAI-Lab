# 2026-02-27 | v1.1.0 | Pre-flight Monte Carlo simulation sandbox | Writer: J.Ekrami | Co-writer: Antigravity
import numpy as np
import pandas as pd
from config import COMMISSION_RATE, SLIPPAGE_RATE

class SimulationSandbox:
    """
    V8 Operational Intelligence: The Pre-Flight Simulation Engine
    
    Acts as a middleware layer that performs real-time local optimization 
    before capital is committed.
    """

    def __init__(self, n_iterations=1000, max_path_length=150):
        self.n_iterations = n_iterations
        self.max_path_length = max_path_length

    def pull_recent_context(self, memory_df: pd.DataFrame, lookback=500):
        """
        Extracts drift (mean return) and volatility (stdev of returns) 
        from the most recent `lookback` bars to parameterize the Monte Carlo.
        """
        if len(memory_df) < 2:
            return 0.0, 0.001
        
        recent = memory_df.tail(lookback).copy()
        recent['return'] = recent['close'].pct_change()
        drift = recent['return'].mean()
        volatility = recent['return'].std()
        
        if np.isnan(drift): drift = 0.0
        if np.isnan(volatility) or volatility == 0: volatility = 0.001
        
        return drift, volatility

    def run_lsb(self, entry_price: float, stop_dist: float, target_dist: float, drift: float, volatility: float, direction: str = "bullish"):
        """
        Runs a Local Synthetic Backtest (LSB) Monte Carlo simulation.
        Generates thousands of price paths to evaluate Pp and EV.
        """
        if entry_price <= 0 or volatility <= 0:
            return 0.0, -1.0
            
        # Simulate price paths using Geometric Brownian Motion (GBM)
        # S_t = S_0 * exp((mu - sigma^2/2)*t + sigma*W_t)
        
        # We need relative stop and target to apply them on the price paths
        stop_price = entry_price - stop_dist if direction == "bullish" else entry_price + stop_dist
        target_price = entry_price + target_dist if direction == "bullish" else entry_price - target_dist
        
        # Time array
        dt = 1 # 1 bar per step
        
        # Precompute random shocks for all iterations and steps
        # Shape: (n_iterations, max_path_length)
        shocks = np.random.normal(0, 1, size=(self.n_iterations, self.max_path_length))
        
        # Calculate log returns per step
        log_returns = (drift - 0.5 * volatility**2) * dt + volatility * np.sqrt(dt) * shocks
        
        # Calculate cumulative returns over paths
        cumulative_returns = np.cumsum(log_returns, axis=1)
        
        # Compute exact price paths
        price_paths = entry_price * np.exp(cumulative_returns)
        
        wins = 0
        losses = 0
        total_profit = 0.0
        
        fee_impact = entry_price * (COMMISSION_RATE + SLIPPAGE_RATE)
        
        # Vectorized evaluation can be done, but a loop over paths provides exact hit sequencing:
        # We need to know which is hit FIRST: target or stop.
        for i in range(self.n_iterations):
            path = price_paths[i]
            
            if direction == "bullish":
                # Find indices where target and stop are crossed
                target_hits = np.where(path >= target_price)[0]
                stop_hits = np.where(path <= stop_price)[0]
            else:
                target_hits = np.where(path <= target_price)[0]
                stop_hits = np.where(path >= stop_price)[0]
                
            first_target_idx = target_hits[0] if len(target_hits) > 0 else self.max_path_length
            first_stop_idx = stop_hits[0] if len(stop_hits) > 0 else self.max_path_length
            
            if first_target_idx < first_stop_idx:
                wins += 1
                total_profit += (target_dist - fee_impact)
            elif first_stop_idx < first_target_idx:
                losses += 1
                total_profit -= (stop_dist + fee_impact)
            else:
                # If neither is hit within max_path_length, mark as unresolved but calculate terminal PnL
                terminal_price = path[-1]
                if direction == "bullish":
                    pnl = terminal_price - entry_price
                else:
                    pnl = entry_price - terminal_price
                
                # If terminal PnL is positive it's a win, otherwise a loss
                if pnl > 0:
                    wins += 1
                else:
                    losses += 1
                    
                total_profit += (pnl - fee_impact)
                
        # Probability of profit
        pp = wins / self.n_iterations
        
        # EV per trade (unscaled R)
        ev_absolute = total_profit / self.n_iterations
        
        # Convert EV to R-multiple
        r_value = stop_dist
        if r_value == 0: r_value = 1.0 # fallback avoiding division by zero
        ev_r = ev_absolute / r_value
        
        return pp, ev_r

    def evaluate(self, memory_df: pd.DataFrame, signal_context: dict, entry_price: float, stop_dist: float, target_dist: float) -> dict:
        """
        Main interface for the execution layer to gate trades.
        """
        drift, volatility = self.pull_recent_context(memory_df, lookback=500)
        
        pp, ev = self.run_lsb(
            entry_price=entry_price, 
            stop_dist=stop_dist, 
            target_dist=target_dist, 
            drift=drift, 
            volatility=volatility, 
            direction=signal_context.get("direction", "bullish")
        )
        
        # Primary gating condition: bypass GBM EV check for mean-reverting setups
        setup_type = signal_context.get("type", "") if isinstance(signal_context, dict) else str(signal_context)
        is_mean_reverting = setup_type in ["wedge_reversal", "failed_breakout", "second_entry"]
        
        if is_mean_reverting:
            approved = True
        else:
            approved = (pp >= 0.30) and (ev >= -0.5)
        
        return {
            "approved": approved,
            "pp": pp,
            "ev": ev,
            "drift": drift,
            "volatility": volatility
        }
