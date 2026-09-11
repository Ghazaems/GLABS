"""
Ambil data harga harian saham IDX via yfinance.
Catatan: yfinance unofficial - satu ticker gagal tidak boleh menghentikan proses lain.
"""
import time
import yfinance as yf
import pandas as pd


def fetch_daily(ticker: str, period: str = "1y", retries: int = 2) -> pd.DataFrame | None:
    """
    ticker: kode tanpa suffix, misal 'BBCA' -> otomatis jadi 'BBCA.JK'
    Return None kalau gagal setelah retry, JANGAN raise (biar batch tidak berhenti).
    """
    # Indeks Yahoo (mis. ^JKSE), forex, dan ticker yang sudah punya suffix
    # tidak boleh dipaksa menjadi .JK.
    symbol = ticker if ticker.endswith(".JK") or ticker.startswith("^") or "=" in ticker else f"{ticker}.JK"

    for attempt in range(retries + 1):
        try:
            df = yf.download(symbol, period=period, interval="1d",
                              progress=False, auto_adjust=True)
            if df.empty:
                print(f"[WARN] {symbol}: data kosong")
                return None
            # yfinance kadang return MultiIndex kolom kalau multi-ticker; ratakan
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            return df
        except Exception as e:
            print(f"[WARN] {symbol} percobaan {attempt + 1} gagal: {e}")
            time.sleep(1.5)

    print(f"[ERROR] {symbol}: gagal setelah {retries + 1} percobaan")
    return None


def fetch_batch(tickers: list[str], period: str = "1y") -> dict[str, pd.DataFrame]:
    """Ambil banyak ticker, skip yang gagal, return dict {ticker: df}"""
    result = {}
    for t in tickers:
        df = fetch_daily(t, period=period)
        if df is not None:
            result[t] = df
        time.sleep(0.3)  # sopan ke server, hindari rate-limit
    return result
