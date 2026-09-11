"""
Struktur trend (swing high/low) + support-resistance dinamis.
Prioritas #1 untuk swing trading - fondasi sebelum sinyal lain dipakai.
"""
import pandas as pd
import numpy as np


def find_swing_points(df: pd.DataFrame, window: int = 5) -> pd.DataFrame:
    """
    Tandai swing high/low: titik tertinggi/terendah lokal dalam radius `window` hari.
    window=5 -> cocok untuk swing mingguan (bukan noise harian).
    """
    highs = df["High"]
    lows = df["Low"]

    df = df.copy()
    df["swing_high"] = highs[(highs == highs.rolling(window * 2 + 1, center=True).max())]
    df["swing_low"] = lows[(lows == lows.rolling(window * 2 + 1, center=True).min())]
    return df


def trend_structure(df: pd.DataFrame, window: int = 5) -> str:
    """
    Klasifikasi sederhana: uptrend (HH+HL), downtrend (LH+LL), atau sideways.
    """
    df = find_swing_points(df, window)
    swing_highs = df["swing_high"].dropna().tail(3)
    swing_lows = df["swing_low"].dropna().tail(3)

    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return "insufficient_data"

    higher_highs = swing_highs.iloc[-1] > swing_highs.iloc[-2]
    higher_lows = swing_lows.iloc[-1] > swing_lows.iloc[-2]
    lower_highs = swing_highs.iloc[-1] < swing_highs.iloc[-2]
    lower_lows = swing_lows.iloc[-1] < swing_lows.iloc[-2]

    if higher_highs and higher_lows:
        return "uptrend"
    if lower_highs and lower_lows:
        return "downtrend"
    return "sideways"


def support_resistance_levels(df: pd.DataFrame, window: int = 5, lookback: int = 60) -> dict:
    """Level support/resistance terdekat dari swing points beberapa bulan terakhir."""
    recent = find_swing_points(df.tail(lookback), window)
    resistance = recent["swing_high"].dropna()
    support = recent["swing_low"].dropna()

    last_close = df["Close"].iloc[-1]
    return {
        "nearest_resistance": resistance[resistance > last_close].min() if not resistance[resistance > last_close].empty else None,
        "nearest_support": support[support < last_close].max() if not support[support < last_close].empty else None,
        "last_close": last_close,
    }
