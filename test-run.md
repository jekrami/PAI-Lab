# PAI-Lab Execution Guide

## Starting Fresh
If you want to start a brand new run from scratch (discarding all previous ML training, engine state, and logs):

```bash
# 1. Activate the environment
cd /path/to/PAI-Lab
source .venv/bin/activate  # Or .venv\Scripts\activate on Windows

# 2. Delete the state files to reset the machine learning context
rm state/engine_state_*.pkl

# 3. Delete the old trade logs to reset PnL
rm logs/trades.csv
```

## Running the Live Engine in `screen`

Since the AI needs to process live market data 24/7, you should run it inside a `screen` session so it doesn't shut down when you close your terminal.

```bash
# Start a new screen session named "pailab"
screen -S pailab

# Inside the screen, activate the environment and run the engine
source .venv/bin/activate
python live_runner.py
```

### Screen Commands:
- **To detach** (leave it running in the background): Press `Ctrl+A`, then press `D`.
- **To reattach** (return to the running session): `screen -r pailab`
- **To see all running screen sessions:** `screen -ls`

---

## Machine Learning "Warm-up" Phase (Backtesting vs Live)
*Note on the AI Model:* The `RollingController` requires at least 100 historical trades of training data before it becomes statistically accurate. 
- In **Backtesting** (`main.py`), the engine is now configured to automatically "warm up" on the first 40,000 candles (it will take trades blindly to gather data without recording imaginary PnL).
- In **Live Trading** (`live_runner.py`), the engine loads the exact same `state/engine_state_BTCUSDT.pkl` file. Therefore, you should **Run `main.py` first** to quickly train the AI over the past 3-4 months of data, let it save the trained `state.pkl` file, and *then* run `live_runner.py`.
