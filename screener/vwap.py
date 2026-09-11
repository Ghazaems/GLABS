"""
VWAP mingguan/bulanan dari data harian (bukan intraday - sesuai kebutuhan swing/investing).
Dipakai sebagai referensi 'fair value', bukan sinyal utama.
"""
import pandas as pd


def rolling_vwap(df: pd.DataFrame, window: int = 5) -> pd.Series:
    """
    window=5 -> VWAP mingguan (5 hari bursa)
    window=20 -> VWAP bulanan (~20 hari bursa)
    """
    typical_price = (df["High"] + df["Low"] + df["Close"]) / 3
    pv = typical_price * df["Volume"]
    vwap = pv.rolling(window).sum() / df["Volume"].rolling(window).sum()
    return vwap


def price_vs_vwap(df: pd.DataFrame, window: int = 5) -> dict:
    vwap = rolling_vwap(df, window)
    last_close = df["Close"].iloc[-1]
    last_vwap = vwap.iloc[-1]

    if pd.isna(last_vwap):
        return {"status": "insufficient_data"}

    position = "above" if last_close > last_vwap else "below"
    return {
        "vwap": round(last_vwap, 2),
        "last_close": round(last_close, 2),
        "position": position,
    }
