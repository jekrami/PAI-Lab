# 2026-02-17 | v0.1.0 | Binance live data feed | Writer: J.Ekrami | Co-writer: GPT-5.1
"""
live_feed.py

Handles live Binance 5m candle retrieval.

Provides:
- Historical warm-up fetch
- Latest closed candle fetch
- Time synchronization
"""

import requests
import time


class BinanceLiveFeed:

    def __init__(self, symbol="BTCUSDT"):
        self.symbol = symbol
        self.base_url = "https://data-api.binance.vision/api/v3/klines"

    # -------------------------------------------------
    # Fetch last N historical closed candles
    # -------------------------------------------------

    def get_historical_candles(self, interval="5m", limit=200):
        params = {
            "symbol": self.symbol,
            "interval": interval,
            "limit": limit,
        }

        try:
            response = requests.get(self.base_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            print(f"[LiveFeed] Historical fetch error: {e}")
            return []

        candles = []

        for k in data:
            candles.append({
                "open_time": k[0],
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4])
            })

        return candles

    # -------------------------------------------------
    # Fetch latest closed candle
    # -------------------------------------------------

    def get_latest_closed_candle(self, interval="5m"):
        params = {
            "symbol": self.symbol,
            "interval": interval,
            "limit": 2,
        }

        try:
            response = requests.get(self.base_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            print(f"[LiveFeed] Latest candle fetch error: {e}")
            return None

        if not data or len(data) < 2:
            return None

        # Second-to-last candle is last CLOSED candle
        k = data[-2]

        candle = {
            "open_time": k[0],
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4])
        }

        return candle
