import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import pandas as pd
import time
import argparse
import os

BASE_URL = "https://data-api.binance.vision/api/v3/klines"

def get_session():
    session = requests.Session()
    retry = Retry(connect=5, backoff_factor=0.5)
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

def download_data(symbol, interval, total_bars):
    print(f"Downloading {symbol} {interval} data... ({total_bars} bars)")
    all_data = []
    end_time = None
    
    while len(all_data) < total_bars:
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": 1000
        }
        
        if end_time:
            params["endTime"] = end_time
            
        session = get_session()
        response = session.get(BASE_URL, params=params)
        
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
            
        # Prepend to maintain chronological order
        all_data = data + all_data
        
        # Next request goes backward in time
        end_time = data[0][0] - 1  
        
        print(f"[{interval}] Downloaded {len(all_data)} bars...", end="\r")
        time.sleep(0.5)
        
    print() # Newline after loop
    
    # Trim to exact length
    all_data = all_data[-total_bars:]
    
    df = pd.DataFrame(all_data, columns=[
        "open_time","open","high","low","close","volume",
        "close_time","qav","num_trades","taker_base","taker_quote","ignore"
    ])
    
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df = df[["open_time","open","high","low","close","volume"]]
    
    filename = f"{symbol.lower()}_{interval}.csv"
    df.to_csv(filename, index=False)
    print(f"Saved {len(df)} rows to {filename}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download Binance historical klines across multiple timeframes.")
    parser.add_argument("--symbol", type=str, default="BTCUSDT", help="Trading pair symbol (e.g. BTCUSDT)")
    parser.add_argument("--intervals", type=str, nargs="+", default=["1m", "5m", "15m", "1h"], help="List of intervals to download")
    parser.add_argument("--bars", type=int, default=100000, help="Total bars to download per interval")
    
    args = parser.parse_args()
    
    for interval in args.intervals:
        download_data(args.symbol, interval, args.bars)
    
    print("\nDownload complete.")
