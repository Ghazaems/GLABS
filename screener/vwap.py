"""
Analisis VWAP multi-horizon untuk data harian IDX.

VWAP 5:
    Trigger cepat untuk reclaim/breakdown.

VWAP 20:
    Konfirmasi tren menengah.

VWAP 60:
    Penentu regime swing utama.

Output:
    BUY, HOLD, WAIT, REDUCE, EXIT, atau AVOID.

Catatan:
    BUY dieksekusi pada pembukaan sesi berikutnya, bukan close
    yang dipakai untuk menghitung sinyal.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


REQUIRED_COLUMNS = {
    "High",
    "Low",
    "Close",
    "Volume",
}

VWAP_SETTINGS = {
    "fast_window": 5,
    "medium_window": 20,
    "slow_window": 60,
    "slope_lookback": 3,
    "volume_window": 20,
    "minimum_rvol": 1.2,
    "atr_window": 14,
    "maximum_atr_distance": 2.0,
    "exit_confirmation_bars": 2,
}


def _prepare_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Validasi dan bersihkan OHLCV tanpa mengisi data yang hilang."""
    if not isinstance(df, pd.DataFrame):
        raise TypeError("df harus berupa pandas DataFrame.")

    missing = REQUIRED_COLUMNS.difference(df.columns)
    if missing:
        raise ValueError(
            f"Kolom wajib tidak tersedia: {sorted(missing)}"
        )

    frame = df.sort_index().copy()

    numeric_columns = [
        "High",
        "Low",
        "Close",
        "Volume",
    ]

    frame[numeric_columns] = frame[numeric_columns].apply(
        pd.to_numeric,
        errors="coerce",
    )

    finite_price = (
        np.isfinite(frame["High"])
        & np.isfinite(frame["Low"])
        & np.isfinite(frame["Close"])
    )

    positive_price = (
        (frame["High"] > 0)
        & (frame["Low"] > 0)
        & (frame["Close"] > 0)
    )

    valid_volume = (
        np.isfinite(frame["Volume"])
        & (frame["Volume"] > 0)
    )

    frame["_valid_vwap_row"] = (
        finite_price
        & positive_price
        & valid_volume
    )

    return frame


def rolling_vwap(
    df: pd.DataFrame,
    window: int = 5,
) -> pd.Series:
    """
    Hitung rolling VWAP berbasis HLC3.

    Harga dan volume harus valid secara bersamaan. Volume dari candle
    dengan harga NaN tidak boleh masuk denominator.
    """
    if window <= 0:
        raise ValueError("window harus lebih besar dari nol.")

    frame = _prepare_frame(df)

    typical_price = (
        frame["High"]
        + frame["Low"]
        + frame["Close"]
    ) / 3.0

    valid = frame["_valid_vwap_row"]

    clean_price = typical_price.where(valid)
    clean_volume = frame["Volume"].where(valid)

    numerator = (
        clean_price
        .mul(clean_volume)
        .rolling(window, min_periods=window)
        .sum()
    )

    denominator = (
        clean_volume
        .rolling(window, min_periods=window)
        .sum()
        .where(lambda value: value > 0)
    )

    result = numerator / denominator
    result.name = f"vwap_{window}"

    return result


def vwap_slope_pct(
    vwap: pd.Series,
    lookback: int = 3,
) -> pd.Series:
    """Slope VWAP dalam persen agar dapat dibandingkan antarharga."""
    if lookback <= 0:
        raise ValueError("lookback harus lebih besar dari nol.")

    return (
        vwap.pct_change(
            periods=lookback,
            fill_method=None,
        )
        * 100.0
    )


def average_true_range(
    df: pd.DataFrame,
    window: int = 14,
) -> pd.Series:
    """ATR sederhana untuk mengukur jarak dan invalidasi risiko."""
    if window <= 0:
        raise ValueError("window harus lebih besar dari nol.")

    frame = _prepare_frame(df)

    previous_close = frame["Close"].shift(1)

    true_range = pd.concat(
        [
            frame["High"] - frame["Low"],
            (frame["High"] - previous_close).abs(),
            (frame["Low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    true_range = true_range.where(
        frame["_valid_vwap_row"]
    )

    result = true_range.rolling(
        window,
        min_periods=window,
    ).mean()

    result.name = f"atr_{window}"
    return result


def relative_volume(
    df: pd.DataFrame,
    window: int = 20,
) -> pd.Series:
    """
    Volume hari ini dibanding median volume sebelumnya.

    Candle saat ini tidak masuk baseline sehingga lonjakan volume
    tidak memperbesar pembaginya sendiri.
    """
    if window <= 0:
        raise ValueError("window harus lebih besar dari nol.")

    frame = _prepare_frame(df)

    volume = frame["Volume"].where(
        frame["_valid_vwap_row"]
    )

    historical_median = (
        volume
        .rolling(window, min_periods=window)
        .median()
        .shift(1)
        .where(lambda value: value > 0)
    )

    result = volume / historical_median
    result.name = f"rvol_{window}"

    return result


def _number(
    value: Any,
    digits: int = 4,
) -> float | None:
    """Ubah nilai numerik menjadi JSON-safe float."""
    if value is None or pd.isna(value):
        return None

    numeric = float(value)

    if not np.isfinite(numeric):
        return None

    return round(numeric, digits)


def _position(
    close: float,
    vwap_value: float,
) -> str:
    if close > vwap_value:
        return "above"

    if close < vwap_value:
        return "below"

    return "at_vwap"


def price_vs_vwap(
    df: pd.DataFrame,
    window: int = 5,
) -> dict:
    """
    Fungsi kompatibilitas untuk scoring lama GLABS.

    Sekarang menambahkan slope dan jarak, tetapi key lama tetap ada.
    """
    frame = _prepare_frame(df)
    vwap = rolling_vwap(frame, window)
    slope = vwap_slope_pct(vwap)

    last_close = frame["Close"].iloc[-1]
    last_vwap = vwap.iloc[-1]
    last_slope = slope.iloc[-1]

    if (
        pd.isna(last_close)
        or pd.isna(last_vwap)
    ):
        return {
            "status": "insufficient_data",
            "window": window,
        }

    distance_pct = (
        (last_close / last_vwap) - 1.0
    ) * 100.0

    return {
        "status": "ok",
        "window": window,
        "vwap": _number(last_vwap, 2),
        "last_close": _number(last_close, 2),
        "position": _position(
            float(last_close),
            float(last_vwap),
        ),
        "slope_pct": _number(last_slope),
        "distance_pct": _number(distance_pct),
    }


def analyze_vwap_signals(
    df: pd.DataFrame,
    settings: dict | None = None,
) -> dict:
    """
    Hasilkan keputusan VWAP multi-horizon.

    Sinyal tidak mengetahui apakah pengguna memiliki posisi.
    Karena itu:
        BUY/WAIT/AVOID digunakan untuk posisi baru.
        HOLD/REDUCE/EXIT digunakan bila saham sudah dimiliki.
    """
    config = {
        **VWAP_SETTINGS,
        **(settings or {}),
    }

    frame = _prepare_frame(df)

    fast_window = int(config["fast_window"])
    medium_window = int(config["medium_window"])
    slow_window = int(config["slow_window"])
    slope_lookback = int(config["slope_lookback"])
    volume_window = int(config["volume_window"])
    atr_window = int(config["atr_window"])
    exit_bars = int(
        config["exit_confirmation_bars"]
    )

    minimum_rows = max(
        slow_window + slope_lookback,
        volume_window + 1,
        atr_window + 1,
    )

    if len(frame) < minimum_rows:
        return {
            "status": "insufficient_data",
            "required_rows": minimum_rows,
            "available_rows": len(frame),
            "signal": "WAIT",
        }

    fast = rolling_vwap(frame, fast_window)
    medium = rolling_vwap(frame, medium_window)
    slow = rolling_vwap(frame, slow_window)

    fast_slope = vwap_slope_pct(
        fast,
        slope_lookback,
    )

    medium_slope = vwap_slope_pct(
        medium,
        slope_lookback,
    )

    slow_slope = vwap_slope_pct(
        slow,
        slope_lookback,
    )

    atr = average_true_range(
        frame,
        atr_window,
    )

    rvol = relative_volume(
        frame,
        volume_window,
    )

    close = frame["Close"]
    last_close = close.iloc[-1]
    previous_close = close.iloc[-2]

    last_fast = fast.iloc[-1]
    previous_fast = fast.iloc[-2]
    last_medium = medium.iloc[-1]
    last_slow = slow.iloc[-1]
    previous_slow = slow.iloc[-2]

    last_fast_slope = fast_slope.iloc[-1]
    last_medium_slope = medium_slope.iloc[-1]
    last_slow_slope = slow_slope.iloc[-1]

    last_atr = atr.iloc[-1]
    last_rvol = rvol.iloc[-1]

    required_values = [
        last_close,
        previous_close,
        last_fast,
        previous_fast,
        last_medium,
        last_slow,
        previous_slow,
        last_medium_slope,
        last_slow_slope,
        last_atr,
        last_rvol,
    ]

    if any(pd.isna(value) for value in required_values):
        return {
            "status": "insufficient_data",
            "required_rows": minimum_rows,
            "available_rows": len(frame),
            "signal": "WAIT",
            "reason": (
                "Indikator terakhir tidak valid. "
                "Periksa harga, volume, atau corporate action."
            ),
        }

    bullish_swing = bool(
        last_close > last_slow
        and last_slow_slope > 0
    )

    bullish_medium = bool(
        last_close > last_medium
        and last_medium_slope > 0
    )

    bearish_swing = bool(
        last_close < last_slow
        and last_slow_slope < 0
    )

    bearish_medium = bool(
        last_close < last_medium
        and last_medium_slope < 0
    )

    reclaim_fast = bool(
        previous_close <= previous_fast
        and last_close > last_fast
    )

    breakdown_fast = bool(
        previous_close >= previous_fast
        and last_close < last_fast
    )

    sufficient_volume = bool(
        last_rvol >= float(config["minimum_rvol"])
    )

    distance_atr = (
        (last_close - last_fast) / last_atr
        if last_atr > 0
        else np.nan
    )

    not_overextended = bool(
        np.isfinite(distance_atr)
        and distance_atr
        <= float(config["maximum_atr_distance"])
    )

    below_medium = (
        close < medium
    ).tail(exit_bars)

    medium_exit_confirmed = bool(
        len(below_medium) == exit_bars
        and below_medium.fillna(False).all()
    )

    slow_breakdown = bool(
        previous_close >= previous_slow
        and last_close < last_slow
    )

    buy_condition = bool(
        bullish_swing
        and bullish_medium
        and reclaim_fast
        and sufficient_volume
        and not_overextended
    )

    hold_condition = bool(
        bullish_swing
        and bullish_medium
        and last_close > last_fast
    )

    reduce_condition = bool(
        breakdown_fast
        or last_close < last_medium
        or last_medium_slope <= 0
    )

    avoid_condition = bool(
        bearish_swing
        and bearish_medium
    )

    # EXIT adalah kejadian transisi/breakdown baru. Kondisi bearish
    # yang sudah berlangsung diklasifikasikan AVOID agar dua status
    # tidak saling menelan dan AVOID benar-benar dapat dicapai.
    exit_condition = bool(
        slow_breakdown
        or (
            medium_exit_confirmed
            and not avoid_condition
        )
    )

    reasons: list[str] = []

    if exit_condition:
        signal = "EXIT"

        if medium_exit_confirmed:
            reasons.append(
                f"{exit_bars} close berturut-turut "
                "di bawah VWAP menengah."
            )

        if slow_breakdown:
            reasons.append(
                "Harga baru breakdown VWAP swing."
            )

    elif buy_condition:
        signal = "BUY"
        reasons.extend(
            [
                "Regime swing bullish.",
                "Tren menengah bullish.",
                "Harga melakukan reclaim VWAP cepat.",
                (
                    f"RVOL {last_rvol:.2f} memenuhi "
                    f"minimum {config['minimum_rvol']:.2f}."
                ),
                "Harga belum terlalu jauh dari VWAP.",
            ]
        )

    elif avoid_condition:
        signal = "AVOID"
        reasons.extend(
            [
                "Harga berada di bawah VWAP menengah dan swing.",
                "Slope VWAP menengah dan swing negatif.",
            ]
        )

    elif reduce_condition:
        signal = "REDUCE"

        if breakdown_fast:
            reasons.append(
                "Harga breakdown VWAP cepat."
            )

        if last_close < last_medium:
            reasons.append(
                "Close berada di bawah VWAP menengah."
            )

        if last_medium_slope <= 0:
            reasons.append(
                "Slope VWAP menengah tidak lagi positif."
            )

    elif hold_condition:
        signal = "HOLD"
        reasons.extend(
            [
                "Regime swing dan menengah masih bullish.",
                "Harga bertahan di atas VWAP cepat.",
            ]
        )

        if not sufficient_volume:
            reasons.append(
                "Volume belum cukup untuk entry baru."
            )

        if not not_overextended:
            reasons.append(
                "Harga terlalu jauh untuk entry baru."
            )

    else:
        signal = "WAIT"
        reasons.append(
            "Belum ada konfirmasi lengkap untuk entry atau exit."
        )

        if bullish_swing and not reclaim_fast:
            reasons.append(
                "Regime bullish, tetapi belum ada reclaim VWAP cepat."
            )

        if reclaim_fast and not sufficient_volume:
            reasons.append(
                "Reclaim terjadi tanpa konfirmasi RVOL."
            )

    protective_stop = None

    if last_atr > 0:
        atr_stop = last_close - (2.0 * last_atr)

        structural_candidates = [
            value
            for value in [
                atr_stop,
                last_medium,
            ]
            if value < last_close
        ]

        if structural_candidates:
            protective_stop = max(
                structural_candidates
            )

    return {
        "status": "ok",
        "signal": signal,
        "execution": (
            "next_session_open"
            if signal == "BUY"
            else "not_applicable"
        ),
        "regime": (
            "bullish"
            if bullish_swing
            else "bearish"
            if bearish_swing
            else "neutral"
        ),
        "last_close": _number(last_close, 2),
        "vwap_fast": {
            "window": fast_window,
            "value": _number(last_fast, 2),
            "slope_pct": _number(last_fast_slope),
            "position": _position(
                float(last_close),
                float(last_fast),
            ),
        },
        "vwap_medium": {
            "window": medium_window,
            "value": _number(last_medium, 2),
            "slope_pct": _number(last_medium_slope),
            "position": _position(
                float(last_close),
                float(last_medium),
            ),
        },
        "vwap_swing": {
            "window": slow_window,
            "value": _number(last_slow, 2),
            "slope_pct": _number(last_slow_slope),
            "position": _position(
                float(last_close),
                float(last_slow),
            ),
        },
        "rvol": _number(last_rvol),
        "atr": _number(last_atr, 2),
        "distance_from_fast_atr": _number(
            distance_atr
        ),
        "reclaim_fast": reclaim_fast,
        "breakdown_fast": breakdown_fast,
        "protective_stop": _number(
            protective_stop,
            2,
        ),
        "reasons": reasons,
        "settings": config,
        "confidence": None,
        "confidence_status": (
            "requires_out_of_sample_calibration"
        ),
    }
