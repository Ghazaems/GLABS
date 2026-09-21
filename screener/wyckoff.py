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

    FIX: bias sekarang ditentukan dari sinyal paling BARU secara kronologis,
    bukan "sinyal pertama yang ketemu dikunci selamanya". Kalau sinyal awal
    (climax) dan sinyal belakangan (breakout) berlawanan arah, bias ditandai
    "conflicting" daripada diam-diam mempertahankan label lama yang usang.
    """
    ranges = detect_trading_ranges(df)
    if not ranges:
        return {"status": "no_trading_range_found"}

    tr = ranges[-1]
    result = {
        "tr_start": str(tr["start_date"].date()),
        "tr_end": str(tr["end_date"].date()),
        "tr_high": round(tr["tr_high"], 2),
        "tr_low": round(tr["tr_low"], 2),
        "events": [],
    }

    bias_signals = []  # [(tanggal, "accumulation"/"distribution"), ...]

    climax = find_climax(df, tr)
    if climax:
        result["events"].append(climax)
        bias_signals.append((climax["date"], "accumulation" if climax["type"] == "SC" else "distribution"))

        ar = find_automatic_reaction(df, climax, tr)
        if ar:
            result["events"].append(ar)
            st = find_secondary_test(df, climax, ar)
            if st:
                result["events"].append(st)

    spring_ut = detect_spring_or_ut(df, tr)
    if spring_ut:
        result["events"].append(spring_ut)
        bias_signals.append((spring_ut["date"], "accumulation" if spring_ut["type"] == "Spring" else "distribution"))

    breakout = detect_sos_sow(df, tr)
    if breakout:
        result["events"].append(breakout)
        bias_signals.append((breakout["date"], "accumulation" if breakout["type"] == "SOS" else "distribution"))

        lps = detect_lps_lpsy(df, breakout, tr)
        if lps:
            result["events"].append(lps)

    # Tentukan bias final dari sinyal PALING BARU, tandai kalau ada konflik arah.
    if not bias_signals:
        result["bias"] = "unclear"
    else:
        bias_signals.sort(key=lambda x: x[0])
        directions = {b for _, b in bias_signals}
        if len(directions) > 1:
            result["bias"] = "conflicting"
            result["bias_note"] = (
                f"sinyal awal '{bias_signals[0][1]}', tapi sinyal terbaru "
                f"'{bias_signals[-1][1]}' - butuh review manual"
            )
        else:
            result["bias"] = bias_signals[-1][1]

    result["phase"] = _estimate_phase(result["events"], result["bias"])
    return result


def _estimate_phase(events: list[dict], bias: str | None = None) -> str:
    types = {e["type"] for e in events}
    is_distribution = bias == "distribution"

    if "LPS" in types or "LPSY" in types:
        return "D (LPSY muncul - siap markdown)" if is_distribution else "D (LPS muncul - siap markup)"
    if "SOS" in types or "SOW" in types:
        return "D (breakdown terjadi, cek konfirmasi LPSY)" if is_distribution else "D (breakout terjadi, cek konfirmasi LPS)"
    if "Spring" in types or "UT" in types:
        return "C (test supply/demand - titik keluar potensial jika UT)" if is_distribution else "C (test supply/demand - titik entry potensial jika Spring)"
    if "ST" in types:
        return "B (masih membangun cause, tunggu UT/SOW)" if is_distribution else "B (masih membangun cause, tunggu Spring/SOS)"
    if "SC" in types or "BC" in types or "AR" in types:
        return "A (climax terdeteksi, TR baru mulai terbentuk)"
    return "unclear"


# ---------------------------------------------------------------------------
# 4. MULTI-TIMEFRAME WYCKOFF SCREENING
# ---------------------------------------------------------------------------

WYCKOFF_EVENT_TYPES = (
    "SC",
    "BC",
    "Spring",
    "UT",
    "SOS",
    "SOW",
    "LPS",
    "LPSY",
)

# Semua timeframe tetap memakai candle harian. Perbedaannya adalah panjang
# trading range dan jendela konfirmasi. Nilai ini adalah konfigurasi deteksi,
# bukan klaim edge; bobot skor tetap nol sampai lolos validasi statistik.
WYCKOFF_TIMEFRAME_SETTINGS = {
    "daily": {
        "min_bars": 5,
        "max_range_pct": 0.08,
        "range_window": 5,
        "climax_lookback": 10,
        "event_lookback": 7,
        "lps_lookback": 5,
    },
    "weekly": {
        "min_bars": 15,
        "max_range_pct": 0.15,
        "range_window": 15,
        "climax_lookback": 15,
        "event_lookback": 20,
        "lps_lookback": 15,
    },
    "swing": {
        "min_bars": 30,
        "max_range_pct": 0.25,
        "range_window": 30,
        "climax_lookback": 30,
        "event_lookback": 40,
        "lps_lookback": 30,
    },
}


def analyze_latest_trading_range(
    df: pd.DataFrame,
    timeframe: str = "weekly",
) -> dict:
    """Deteksi event Wyckoff terpisah untuk Daily, Weekly, atau Swing."""
    if timeframe not in WYCKOFF_TIMEFRAME_SETTINGS:
        raise ValueError(
            "timeframe harus daily, weekly, atau swing."
        )

    config = WYCKOFF_TIMEFRAME_SETTINGS[timeframe]
    ranges = detect_trading_ranges(
        df,
        min_bars=config["min_bars"],
        max_range_pct=config["max_range_pct"],
        window=config["range_window"],
    )
    if not ranges:
        return {
            "status": "no_trading_range_found",
            "timeframe": timeframe,
            "events": [],
            "current_events": [],
            "bias": "unclear",
            "phase": "unclear",
        }

    tr = ranges[-1]
    result = {
        "status": "ok",
        "timeframe": timeframe,
        "tr_start": str(tr["start_date"].date()),
        "tr_end": str(tr["end_date"].date()),
        "tr_high": round(float(tr["tr_high"]), 2),
        "tr_low": round(float(tr["tr_low"]), 2),
        "events": [],
        "settings": config,
    }
    bias_signals = []

    climax = find_climax(
        df,
        tr,
        lookback=config["climax_lookback"],
    )
    if climax:
        result["events"].append(climax)
        climax_bias = (
            "accumulation"
            if climax["type"] == "SC"
            else "distribution"
        )
        bias_signals.append(
            (climax["date"], climax_bias)
        )
        ar = find_automatic_reaction(
            df,
            climax,
            tr,
        )
        if ar:
            ar["context"] = climax_bias
            result["events"].append(ar)
            st = find_secondary_test(
                df,
                climax,
                ar,
            )
            if st:
                st["context"] = climax_bias
                result["events"].append(st)

    spring_ut = detect_spring_or_ut(
        df,
        tr,
        lookback_after=config["event_lookback"],
    )
    if spring_ut:
        result["events"].append(spring_ut)
        bias_signals.append(
            (
                spring_ut["date"],
                "accumulation"
                if spring_ut["type"] == "Spring"
                else "distribution",
            )
        )

    breakout = detect_sos_sow(
        df,
        tr,
        lookback_after=config["event_lookback"],
    )
    if breakout:
        result["events"].append(breakout)
        breakout_bias = (
            "accumulation"
            if breakout["type"] == "SOS"
            else "distribution"
        )
        bias_signals.append(
            (breakout["date"], breakout_bias)
        )
        lps = detect_lps_lpsy(
            df,
            breakout,
            tr,
            lookback_after=config["lps_lookback"],
        )
        if lps:
            result["events"].append(lps)

    if not bias_signals:
        result["bias"] = "unclear"
    else:
        bias_signals.sort(key=lambda item: item[0])
        directions = {
            direction
            for _, direction in bias_signals
        }
        if len(directions) > 1:
            result["bias"] = "conflicting"
            result["bias_note"] = (
                "Sinyal arah saling bertentangan; "
                "gunakan sebagai konteks visual."
            )
        else:
            result["bias"] = bias_signals[-1][1]

    result["phase"] = _estimate_phase(
        result["events"],
        result["bias"],
    )
    latest_date = pd.Timestamp(df.index[-1]).normalize()
    result["current_events"] = [
        event["type"]
        for event in result["events"]
        if pd.Timestamp(event["date"]).normalize()
        == latest_date
        and event["type"] in WYCKOFF_EVENT_TYPES
    ]
    result["calibration_status"] = (
        "requires_cross_sectional_validation"
    )
    return result


# ---------------------------------------------------------------------------
# 4. COMPARATIVE STRENGTH vs IHSG
# ---------------------------------------------------------------------------

def _as_series(x) -> pd.Series:
    """
    Defensif: kadang df['Close'] balik sebagai DataFrame 1 kolom (bukan
    Series) - misal kalau ada kolom duplikat setelah flatten MultiIndex.
    Ini yang nyebabin crash 'Data must be 1-dimensional' di comparative_strength.
    """
    if isinstance(x, pd.DataFrame):
        return x.iloc[:, 0]
    return x


def comparative_strength(df: pd.DataFrame, market_df: pd.DataFrame, window: int = 20) -> dict:
    aligned = pd.DataFrame({
        "stock": _as_series(df["Close"]),
        "market": _as_series(market_df["Close"]),
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
