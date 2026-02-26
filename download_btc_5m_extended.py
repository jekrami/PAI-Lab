# 2026-02-25 | v1.1.0 | BTC 5m data downloader | Writer: J.Ekrami | Co-writer: Antigravity
import requests
import pandas as pd
import time

#BASE_URL = "https://api.binance.com/api/v3/klines"
BASE_URL = "https://data-api.binance.vision/api/v3/klines"
SYMBOL = "BTCUSDT"
INTERVAL = "5m"
LIMIT = 1000  # max per request
TOTAL_BARS = 100000  # change as needed

all_data = []
end_time = None

print("Downloading BTC 5m data...")

while len(all_data) < TOTAL_BARS:

    params = {
        "symbol": SYMBOL,
        "interval": INTERVAL,
        "limit": LIMIT
    }

    if end_time:
        params["endTime"] = end_time

    response = requests.get(BASE_URL, params=params)

    if response.status_code != 200:
        print("HTTP Error:", response.status_code)
        print(response.text)
        break

    data = response.json()

    if not isinstance(data, list):
        print("API Error:", data)
        break

    if not data:
        break

    all_data = data + all_data

    end_time = data[0][0] - 1  # move backward

    print(f"Downloaded {len(all_data)} bars...")
    time.sleep(1)

# Trim to exact amount
all_data = all_data[-TOTAL_BARS:]

df = pd.DataFrame(all_data, columns=[
    "open_time","open","high","low","close","volume",
    "close_time","qav","num_trades","taker_base","taker_quote","ignore"
])

df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)

df = df[["open_time","open","high","low","close","volume"]]

df.to_csv("btc_5m_extended.csv", index=False)

print("Saved btc_5m_extended.csv")
