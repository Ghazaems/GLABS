"""
Implementasi Wyckoff Method yang lebih lengkap, mengacu ke:
Wyckoff Method: A Tutorial (Wyckoff Analytics / StockCharts ChartSchool).

Cakupan:
- Deteksi Trading Range (TR)
- Event akumulasi: PS, SC, AR, ST, Spring/Test, SOS, LPS
- Event distribusi: PSY, BC, AR, ST, UT/UTAD, SOW, LPSY
- Estimasi fase A-E (heuristik, bukan presisi manual analyst)
- Comparative Strength vs index pasar (IHSG)

CATATAN JUJUR: Wyckoff pada dasarnya interpretatif - analyst manusia berpengalaman
sering beda pendapat soal fase/event mana yang sedang terjadi. Kode ini adalah
pendekatan rule-based/heuristik untuk MENYARING kandidat, bukan pengganti
penilaian manual. Anggap sebagai "watchlist generator", bukan sinyal pasti.
"""
import pandas as pd
import numpy as np


# ---------------------------------------------------------------------------
# 1. DETEKSI TRADING RANGE
# ---------------------------------------------------------------------------

def detect_trading_ranges(df: pd.DataFrame, min_bars: int = 15, max_range_pct: float = 0.15,
                           window: int = 15) -> list[dict]:
    """
    TR = periode dimana harga konsolidasi dalam band sempit setelah tren sebelumnya.
    max_range_pct: lebar TR maksimal sebagai % dari harga (default 15%, saham IDX
    cukup volatil jadi tidak dibuat terlalu ketat).
    """
    close = df["Close"]
    roll_max = close.rolling(window).max()
    roll_min = close.rolling(window).min()
    range_pct = (roll_max - roll_min) / roll_min

    in_range = range_pct <= max_range_pct
    ranges = []
    start = None

    for i in range(len(df)):
        if in_range.iloc[i] and start is None:
            start = i
        elif not in_range.iloc[i] and start is not None:
            if i - start >= min_bars:
                seg = df.iloc[start:i]
                ranges.append({
                    "start_idx": start,
                    "end_idx": i - 1,
                    "start_date": df.index[start],
                    "end_date": df.index[i - 1],
                    "tr_high": seg["High"].max(),
                    "tr_low": seg["Low"].min(),
                })
            start = None

    # TR yang masih berlangsung sampai bar terakhir
    if start is not None and (len(df) - start) >= min_bars:
        seg = df.iloc[start:]
        ranges.append({
            "start_idx": start,
            "end_idx": len(df) - 1,
            "start_date": df.index[start],
            "end_date": df.index[-1],
            "tr_high": seg["High"].max(),
            "tr_low": seg["Low"].min(),
        })

    return ranges


# ---------------------------------------------------------------------------
# 2. EVENT DETECTION (dalam & sekitar sebuah TR)
# ---------------------------------------------------------------------------

def _avg_volume(df: pd.DataFrame, idx: int, lookback: int = 20) -> float:
    start = max(0, idx - lookback)
    return df["Volume"].iloc[start:idx].mean()


def find_climax(df: pd.DataFrame, tr: dict, lookback: int = 15) -> dict | None:
    """
    Cari SC (selling climax) sebelum TR mulai: bar volume tertinggi, spread lebar,
    close down. Atau BC (buying climax): kebalikannya.
    """
    start = max(0, tr["start_idx"] - lookback)
    pre = df.iloc[start:tr["start_idx"] + 1]
    if pre.empty:
        return None

    idx_max_vol = pre["Volume"].idxmax()
    row = pre.loc[idx_max_vol]
    avg_vol = _avg_volume(df, df.index.get_loc(idx_max_vol))
    if avg_vol == 0 or pd.isna(avg_vol):
        return None

    is_climax_volume = row["Volume"] > avg_vol * 2.0
    if not is_climax_volume:
        return None

    is_down_bar = row["Close"] < row["Open"]
    return {
        "date": idx_max_vol,
        "type": "SC" if is_down_bar else "BC",
        "volume_ratio": round(row["Volume"] / avg_vol, 2),
    }


def find_automatic_reaction(df: pd.DataFrame, climax: dict, tr: dict) -> dict | None:
    """AR (accumulation) = rally tinggi setelah SC. AR (distribution) = reaction rendah setelah BC."""
    climax_idx = df.index.get_loc(climax["date"])
    window = df.iloc[climax_idx:climax_idx + 15]
    if window.empty:
        return None

    if climax["type"] == "SC":
        ar_date = window["High"].idxmax()
        return {"date": ar_date, "type": "AR", "level": window["High"].max()}
    else:
        ar_date = window["Low"].idxmin()
        return {"date": ar_date, "type": "AR", "level": window["Low"].min()}


def find_secondary_test(df: pd.DataFrame, climax: dict, ar: dict) -> dict | None:
    """ST = retest area climax dengan volume lebih rendah."""
    ar_idx = df.index.get_loc(ar["date"])
    window = df.iloc[ar_idx:ar_idx + 15]
    if window.empty:
        return None

    avg_vol = window["Volume"].mean()
    if climax["type"] == "SC":
        st_date = window["Low"].idxmin()
        st_row = window.loc[st_date]
        lower_volume = st_row["Volume"] < avg_vol
        return {"date": st_date, "type": "ST", "lower_volume": bool(lower_volume)}
    else:
        st_date = window["High"].idxmax()
        st_row = window.loc[st_date]
        lower_volume = st_row["Volume"] < avg_vol
        return {"date": st_date, "type": "ST", "lower_volume": bool(lower_volume)}


def detect_spring_or_ut(df: pd.DataFrame, tr: dict, lookback_after: int = 20) -> dict | None:
    """
    Spring: low tembus di bawah tr_low lalu close kembali masuk range (bear trap).
    UT (upthrust): high tembus di atas tr_high lalu close kembali masuk range (bull trap).
    """
    end_idx = tr["end_idx"]
    window = df.iloc[end_idx:end_idx + lookback_after]
    if window.empty:
        return None

    for date, row in window.iterrows():
        if row["Low"] < tr["tr_low"] and row["Close"] > tr["tr_low"]:
            return {"date": date, "type": "Spring", "low": row["Low"]}
        if row["High"] > tr["tr_high"] and row["Close"] < tr["tr_high"]:
            return {"date": date, "type": "UT", "high": row["High"]}
    return None


def detect_sos_sow(df: pd.DataFrame, tr: dict, lookback_after: int = 20) -> dict | None:
    """
    SOS (Sign of Strength): breakout di atas tr_high, volume & spread melebar.
    SOW (Sign of Weakness): breakdown di bawah tr_low, volume & spread melebar.
    """
    end_idx = tr["end_idx"]
    window = df.iloc[end_idx:end_idx + lookback_after]
    if window.empty:
        return None

    avg_vol = _avg_volume(df, end_idx, lookback=20)
    avg_range = (df["High"] - df["Low"]).iloc[max(0, end_idx - 20):end_idx].mean()
    if avg_vol == 0 or pd.isna(avg_vol):
        return None

    for date, row in window.iterrows():
        spread = row["High"] - row["Low"]
        wide_spread = spread > avg_range * 1.3
        high_volume = row["Volume"] > avg_vol * 1.3

        if row["Close"] > tr["tr_high"] and wide_spread and high_volume:
            return {"date": date, "type": "SOS"}
        if row["Close"] < tr["tr_low"] and wide_spread and high_volume:
            return {"date": date, "type": "SOW"}
    return None


def detect_lps_lpsy(df: pd.DataFrame, breakout: dict, tr: dict, lookback_after: int = 15) -> dict | None:
    """
    LPS: pullback setelah SOS yang bertahan di atas tr_high (former resistance jadi support).
    LPSY: rally lemah setelah SOW yang gagal tembus tr_low (former support jadi resistance).
    """
    b_idx = df.index.get_loc(breakout["date"])
    window = df.iloc[b_idx:b_idx + lookback_after]
    if window.empty:
        return None

    avg_vol = window["Volume"].mean()

    if breakout["type"] == "SOS":
        low_date = window["Low"].idxmin()
        row = window.loc[low_date]
        holds_support = row["Low"] >= tr["tr_high"] * 0.98
        if holds_support:
            return {"date": low_date, "type": "LPS", "diminished_volume": bool(row["Volume"] < avg_vol)}
    else:
        high_date = window["High"].idxmax()
        row = window.loc[high_date]
        fails_resistance = row["High"] <= tr["tr_low"] * 1.02
        if fails_resistance:
            return {"date": high_date, "type": "LPSY", "diminished_volume": bool(row["Volume"] < avg_vol)}
    return None


# ---------------------------------------------------------------------------
# 3. RANGKAIAN ANALISIS PENUH UNTUK 1 TR TERBARU
# ---------------------------------------------------------------------------

def analyze_latest_trading_range(df: pd.DataFrame) -> dict:
    """
    Jalankan seluruh pipeline event-detection untuk TR paling baru.
    Return ringkasan event yang ditemukan + estimasi fase.
    """
    ranges = detect_trading_ranges(df)
    if not ranges:
        return {"status": "no_trading_range_found"}

    tr = ranges[-1]  # TR paling baru
    result = {
        "tr_start": str(tr["start_date"].date()),
        "tr_end": str(tr["end_date"].date()),
        "tr_high": round(tr["tr_high"], 2),
        "tr_low": round(tr["tr_low"], 2),
        "events": [],
    }

    climax = find_climax(df, tr)
    bias = None
    if climax:
        result["events"].append(climax)
        bias = "accumulation" if climax["type"] == "SC" else "distribution"

        ar = find_automatic_reaction(df, climax, tr)
        if ar:
            result["events"].append(ar)
            st = find_secondary_test(df, climax, ar)
            if st:
                result["events"].append(st)

    spring_ut = detect_spring_or_ut(df, tr)
    if spring_ut:
        result["events"].append(spring_ut)
        if bias is None:
            bias = "accumulation" if spring_ut["type"] == "Spring" else "distribution"

    breakout = detect_sos_sow(df, tr)
    if breakout:
        result["events"].append(breakout)
        if bias is None:
            bias = "accumulation" if breakout["type"] == "SOS" else "distribution"

        lps = detect_lps_lpsy(df, breakout, tr)
        if lps:
            result["events"].append(lps)

    result["bias"] = bias or "unclear"
    result["phase"] = _estimate_phase(result["events"])
    return result


def _estimate_phase(events: list[dict]) -> str:
    """Heuristik kasar fase A-E berdasarkan event yang ditemukan (urutan, bukan presisi)."""
    types = {e["type"] for e in events}
    if "LPS" in types or "LPSY" in types:
        return "D (LPS/LPSY muncul - siap markup/markdown)"
    if "SOS" in types or "SOW" in types:
        return "D (breakout terjadi, cek konfirmasi LPS/LPSY)"
    if "Spring" in types or "UT" in types:
        return "C (test supply/demand - titik entry potensial jika Spring)"
    if "ST" in types:
        return "B (masih membangun cause, tunggu Spring/SOS)"
    if "SC" in types or "BC" in types or "AR" in types:
        return "A (climax terdeteksi, TR baru mulai terbentuk)"
    return "unclear"


# ---------------------------------------------------------------------------
# 4. COMPARATIVE STRENGTH vs IHSG
# ---------------------------------------------------------------------------

def comparative_strength(df: pd.DataFrame, market_df: pd.DataFrame, window: int = 20) -> dict:
    """
    Wyckoff selalu bandingkan saham vs market. Sederhana: relative strength ratio
    (close saham / close index), lalu cek apakah ratio itu sendiri sedang naik/turun.
    """
    aligned = pd.DataFrame({
        "stock": df["Close"],
        "market": market_df["Close"],
    }).dropna()

    if len(aligned) < window:
        return {"status": "insufficient_data"}

    ratio = aligned["stock"] / aligned["market"]
    recent = ratio.tail(window)
    trend = "outperforming" if recent.iloc[-1] > recent.iloc[0] else "underperforming"

    return {
        "relative_strength_trend": trend,
        "ratio_now": round(recent.iloc[-1], 5),
        "ratio_start": round(recent.iloc[0], 5),
    }
