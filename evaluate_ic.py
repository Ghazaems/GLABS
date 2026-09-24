"""Robust cross-sectional validation for rolling VWAP predictors."""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import spearmanr

from analysis_contract import HORIZONS as CONTRACT_HORIZONS


HORIZONS = {
    5: {"style": "Daily", "predictor": "vwap_distance_5d_pct"},
    20: {"style": "Weekly", "predictor": "vwap_distance_20d_pct"},
    60: {"style": "Swing", "predictor": "vwap_distance_60d_pct"},
}
assert tuple(HORIZONS) == CONTRACT_HORIZONS

MIN_TICKERS_PER_DATE = 30
MIN_VALID_DATES = 12
FDR_ALPHA = 0.05


def _load_frame(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("rows", payload) if isinstance(payload, dict) else payload
    return pd.DataFrame(rows)


def _date_column(frame: pd.DataFrame) -> str | None:
    for candidate in ("signal_date", "date"):
        if candidate in frame.columns:
            return candidate
    return None


def _safe_spearman(group: pd.DataFrame, predictor: str, target: str) -> float | None:
    pair = group[[predictor, target]].apply(pd.to_numeric, errors="coerce").dropna()
    if (
        len(pair) < MIN_TICKERS_PER_DATE
        or pair[predictor].nunique() < 5
        or pair[target].nunique() < 5
    ):
        return None
    value, _ = spearmanr(pair[predictor], pair[target])
    return float(value) if np.isfinite(value) else None


def _daily_cross_sectional_ic(
    frame: pd.DataFrame,
    date_column: str,
    predictor: str,
    target: str,
) -> pd.Series:
    observations: dict[pd.Timestamp, float] = {}
    usable = frame.dropna(subset=[date_column])
    for date, group in usable.groupby(date_column):
        value = _safe_spearman(group, predictor, target)
        if value is not None:
            observations[pd.Timestamp(date)] = value
    return pd.Series(observations, dtype=float).sort_index()


def _hac_mean_test(values: pd.Series, horizon: int) -> tuple[float, float, float, int]:
    array = values.to_numpy(dtype=float)
    # Backtest samples every five sessions. Longer horizons therefore overlap.
    max_lags = max(1, math.ceil(horizon / 5) - 1)
    fit = sm.OLS(array, np.ones((len(array), 1))).fit(
        cov_type="HAC",
        cov_kwds={"maxlags": max_lags},
    )
    return (
        float(fit.params[0]),
        float(fit.tvalues[0]),
        float(fit.pvalues[0]),
        max_lags,
    )


def _benjamini_hochberg(p_values: list[float]) -> list[float]:
    if not p_values:
        return []
    values = np.asarray(p_values, dtype=float)
    order = np.argsort(values)
    ranked = values[order]
    adjusted = ranked * len(values) / np.arange(1, len(values) + 1)
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
    adjusted = np.clip(adjusted, 0.0, 1.0)
    result = np.empty_like(adjusted)
    result[order] = adjusted
    return result.tolist()


def _verdict(
    style: str,
    horizon: int,
    mean_ic: float,
    q_value: float,
    positive_months_pct: float,
) -> dict:
    significant = q_value < FDR_ALPHA
    effect = abs(mean_ic)
    effect_text = (
        "sangat kecil" if effect < 0.03
        else "kecil" if effect < 0.06
        else "moderat"
    )

    if significant and mean_ic > 0:
        status = "proven_positive"
        headline = "Hubungan positif terdeteksi"
        conclusion = (
            f"Ranking jarak Rolling VWAP {style} berhubungan positif dengan "
            f"return {horizon}D setelah koreksi FDR. Besar efeknya {effect_text} "
            f"(mean IC {mean_ic:.3f}); ini belum membuktikan profit strategi."
        )
    elif significant and mean_ic < 0:
        status = "reversed"
        headline = "Hubungan negatif terdeteksi"
        conclusion = (
            f"Ranking jarak Rolling VWAP {style} berhubungan negatif dengan "
            f"return {horizon}D setelah koreksi FDR. Besar efeknya {effect_text} "
            f"(mean IC {mean_ic:.3f}); jangan membalik sinyal tanpa forward test."
        )
    else:
        status = "not_proven"
        headline = "Belum terbukti konsisten"
        conclusion = (
            f"Belum ada hubungan yang bertahan setelah koreksi FDR untuk "
            f"Rolling VWAP {style} terhadap return {horizon}D."
        )

    stability = (
        "Mayoritas bulan positif."
        if positive_months_pct > 50
        else "Mayoritas bulan tidak positif."
        if positive_months_pct < 50
        else "Stabilitas bulanan berimbang."
    )
    return {
        "status": status,
        "headline": headline,
        "conclusion": conclusion,
        "stability_summary": stability,
    }


def _horizon_result(frame: pd.DataFrame, date_column: str, horizon: int) -> dict:
    metadata = HORIZONS[horizon]
    style = metadata["style"]
    predictor = metadata["predictor"]
    target = f"return_{horizon}d_pct"
    base = {"horizon": f"{horizon}D", "style": style}

    if predictor not in frame.columns or target not in frame.columns:
        return {
            **base,
            "status": "unavailable",
            "headline": "Hasil belum tersedia",
            "conclusion": (
                f"Backtest baru harus menghasilkan {predictor} dan {target}."
            ),
            "stability_summary": "Menunggu backtest otomatis berikutnya.",
            "statistics": None,
        }

    daily_ic = _daily_cross_sectional_ic(frame, date_column, predictor, target)
    n_dates = int(len(daily_ic))
    if n_dates < MIN_VALID_DATES:
        return {
            **base,
            "status": "insufficient_data",
            "headline": "Data belum cukup",
            "conclusion": (
                f"Hanya {n_dates} tanggal valid; minimum {MIN_VALID_DATES} tanggal "
                f"dengan setidaknya {MIN_TICKERS_PER_DATE} saham diperlukan."
            ),
            "stability_summary": "Menunggu sampel lintas saham bertambah.",
            "statistics": None,
        }

    mean_ic, t_stat, p_value, hac_lags = _hac_mean_test(daily_ic, horizon)
    std_ic = float(daily_ic.std(ddof=1))
    monthly_ic = daily_ic.resample("ME").mean().dropna()
    positive_months_pct = (
        float((monthly_ic > 0).mean() * 100.0) if len(monthly_ic) else 0.0
    )

    return {
        **base,
        "status": "pending_fdr",
        "headline": "Menunggu koreksi pengujian",
        "conclusion": "",
        "stability_summary": "",
        "statistics": {
            "mean_ic": round(mean_ic, 4),
            "std_ic": round(std_ic, 4),
            "t_stat_hac": round(t_stat, 4),
            "p_value_raw": round(p_value, 6),
            "q_value_fdr": None,
            "hac_lags": hac_lags,
            "positive_months_pct": round(positive_months_pct, 2),
            "n_dates": n_dates,
            "n_months": int(len(monthly_ic)),
        },
    }


def evaluate(path: Path) -> dict:
    frame = _load_frame(path)
    if frame.empty:
        raise ValueError("Tidak ada baris backtest.")

    date_column = _date_column(frame)
    if date_column is None:
        raise ValueError("Kolom tanggal harus bernama 'date' atau 'signal_date'.")
    frame[date_column] = pd.to_datetime(frame[date_column], errors="coerce")

    results = {
        str(horizon): _horizon_result(frame, date_column, horizon)
        for horizon in HORIZONS
    }

    test_keys = [
        key for key, result in results.items()
        if result.get("statistics") is not None
    ]
    q_values = _benjamini_hochberg([
        results[key]["statistics"]["p_value_raw"]
        for key in test_keys
    ])

    for key, q_value in zip(test_keys, q_values):
        result = results[key]
        stats = result["statistics"]
        stats["q_value_fdr"] = round(float(q_value), 6)
        verdict = _verdict(
            result["style"],
            int(key),
            stats["mean_ic"],
            q_value,
            stats["positive_months_pct"],
        )
        result.update(verdict)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": str(path),
        "methodology": {
            "type": "cross_sectional_per_date",
            "prediction": "continuous distance from horizon-specific rolling VWAP",
            "realization": "net return from next-session open",
            "minimum_tickers_per_date": MIN_TICKERS_PER_DATE,
            "minimum_valid_dates": MIN_VALID_DATES,
            "inference": "HAC/Newey-West intercept test",
            "multiple_testing": "Benjamini-Hochberg FDR across 5D/20D/60D",
            "monthly_stability": "calendar-month mean of cross-sectional IC",
            "horizons": list(CONTRACT_HORIZONS),
            "no_time_series_per_stock": True,
            "universe_warning": "current static universe; survivorship bias not eliminated",
        },
        "horizon_results": results,
    }


def main() -> None:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("backtest_results.csv")
    output = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("web/ic_data.json")
    report = evaluate(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
