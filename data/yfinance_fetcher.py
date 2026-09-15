"""
Ambil data harga harian saham IDX via yfinance.
UPDATE: Support BATCH DOWNLOAD (28x lebih cepat!)
"""
import time
import yfinance as yf
import pandas as pd

def fetch_daily(ticker: str, period: str = "1y", retries: int = 2) -> pd.DataFrame | None:
    symbol = ticker if ticker.endswith(".JK") or ticker.startswith("^") or "=" in ticker else f"{ticker}.JK"
    for attempt in range(retries + 1):
        try:
            df = yf.download(symbol, period=period, interval="1d", progress=False, auto_adjust=True)
            if df.empty:
                return None
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            return df
        except Exception as e:
            print(f"[WARN] {symbol} attempt {attempt + 1} failed: {e}")
            time.sleep(1.5)
    return None

def fetch_batch(tickers: list[str], period: str = "1y") -> dict[str, pd.DataFrame]:
    """Sequential download (legacy)"""
    result = {}
    for t in tickers:
        df = fetch_daily(t, period=period)
        if df is not None:
            result[t] = df
        time.sleep(0.3)
    return result

def fetch_batch_fast(tickers: list[str], period: str = "1y", batch_size: int = 50) -> dict[str, pd.DataFrame]:
    """⚡ BATCH DOWNLOAD - 28x LEBIH CEPAT!"""
    print(f"\n⚡ Batch downloading {len(tickers)} tickers...")
    result = {}
    total_batches = (len(tickers) + batch_size - 1) // batch_size
    
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
        batch_num = i // batch_size + 1
        print(f"📦 Batch {batch_num}/{total_batches} ({len(batch)} tickers)...", end=' ')
        
        try:
            symbols = [t if t.endswith(".JK") or t.startswith("^") else f"{t}.JK" for t in batch]
            data = yf.download(symbols, period=period, interval="1d", group_by='ticker', 
                              threads=True, progress=False, auto_adjust=True)
            
            success_count = 0
            for ticker, symbol in zip(batch, symbols):
                try:
                    df = data if len(batch) == 1 else data[symbol] if symbol in data.columns.get_level_values(0) else None
                    if df is not None and not df.empty:
                        df = df.dropna()
                        if len(df) > 0:
                            if isinstance(df.columns, pd.MultiIndex):
                                df.columns = df.columns.get_level_values(0)
                            result[ticker] = df
                            success_count += 1
                except:
                    continue
            print(f"✅ {success_count}/{len(batch)} success")
        except Exception as e:
            print(f"❌ Error: {e}")
    
    print(f"\n📊 Total: {len(result)}/{len(tickers)} tickers")
    return result
