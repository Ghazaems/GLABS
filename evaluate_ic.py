"""Cross-sectional VWAP IC evaluation for Daily, Weekly, and Swing horizons.

The evaluator ranks stocks within each signal date, never across time for one
stock. Raw statistics are exported for audit; user-facing verdicts are exported
separately so the dashboard can show the conclusion instead of the calculation.
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr, t as student_t

HORIZONS = {
    5: {"style": "Daily", "predictor": "vwap_rank_5d"},
    20: {"style": "Weekly", "predictor": "vwap_rank_20d"},
    60: {"style": "Swing", "predictor": "vwap_rank_60d"},
}
MIN_TICKERS_PER_DATE = 5


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
        or pair[predictor].nunique() < 2
        or pair[target].nunique() < 2
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


def _human_verdict(
    style: str,
    horizon: int,
    mean_ic: float,
    p_value: float,
    positive_months_pct: float,
) -> dict:
    significant = p_value < 0.05
    if significant and mean_ic > 0:
        status = "proven_positive"
        headline = "Terbukti punya daya urut"
        conclusion = (
            f"VWAP {style} terbukti membantu mengurutkan saham untuk hasil "
            f"{horizon} hari berikutnya; saham dengan sinyal lebih bullish "
            "cenderung memberi hasil lebih baik."
        )
    elif significant and mean_ic < 0:
        status = "reversed"
        headline = "Arah sinyal terbalik"
        conclusion = (
            f"VWAP {style} menunjukkan hubungan yang konsisten tetapi berlawanan "
            f"dengan hasil {horizon} hari. Logika arah sinyal perlu diperiksa "
            "sebelum dipakai sebagai dasar keputusan."
        )
    else:
        status = "not_proven"
        headline = "Belum terbukti konsisten"
        conclusion = (
            f"Belum ada bukti statistik bahwa VWAP {style} mampu mengurutkan "
            f"hasil saham pada horizon {horizon} hari secara konsisten."
        )

    if positive_months_pct > 50:
        stability = "Mayoritas bulan menunjukkan hubungan positif."
    elif positive_months_pct < 50:
        stability = "Mayoritas bulan tidak menunjukkan hubungan positif."
    else:
        stability = "Stabilitas bulanan berimbang."

    return {
        "status": status,
        "headline": headline,
        "conclusion": conclusion,
        "stability_summary": stability,
    }


def _horizon_result(frame: pd.DataFrame, date_column: str, horizon: int) -> dict:
    style = HORIZONS[horizon]["style"]
    predictor = HORIZONS[horizon]["predictor"]
    target = f"return_{horizon}d_pct"

    if predictor not in frame.columns or target not in frame.columns:
        return {
            "horizon": f"{horizon}D",
            "style": style,
            "status": "unavailable",
            "headline": "Hasil belum tersedia",
            "conclusion": (
                f"Validasi VWAP {style} belum memiliki pasangan sinyal dan "
                f"return {horizon} hari yang lengkap."
            ),
            "stability_summary": "Menunggu backtest otomatis berikutnya.",
            "statistics": None,
        }

    daily_ic = _daily_cross_sectional_ic(
        frame,
        date_column,
        predictor,
        target,
    )
    n_dates = int(len(daily_ic))
    if n_dates < 2:
        return {
            "horizon": f"{horizon}D",
            "style": style,
            "status": "insufficient_data",
            "headline": "Data belum cukup",
            "conclusion": (
                f"Belum cukup tanggal dengan minimal {MIN_TICKERS_PER_DATE} "
                f"saham untuk menilai VWAP {style}."
            ),
            "stability_summary": "Menunggu sampel lintas saham bertambah.",
            "statistics": None,
        }

    mean_ic = float(daily_ic.mean())
    std_ic = float(daily_ic.std(ddof=1))
    if std_ic > 0 and np.isfinite(std_ic):
        t_stat = mean_ic / (std_ic / math.sqrt(n_dates))
        p_value = float(2.0 * student_t.sf(abs(t_stat), df=n_dates - 1))
    else:
        # Standard error is zero only in a degenerate sample. Keep JSON valid
        # instead of exporting Infinity.
        t_stat = None
        p_value = 0.0 if mean_ic != 0 else 1.0

    monthly_ic = daily_ic.resample("ME").mean().dropna()
    n_months = int(len(monthly_ic))
    positive_months_pct = (
        float((monthly_ic > 0).mean() * 100.0)
        if n_months
        else 0.0
    )
    verdict = _human_verdict(
        style,
        horizon,
        mean_ic,
        p_value,
        positive_months_pct,
    )

    return {
        "horizon": f"{horizon}D",
        "style": style,
        **verdict,
        "statistics": {
            "mean_ic": round(mean_ic, 4),
            "std_ic": round(std_ic, 4),
            "t_stat": round(float(t_stat), 4) if t_stat is not None else None,
            "p_value": round(p_value, 4),
            "positive_months_pct": round(positive_months_pct, 2),
            "n_dates": n_dates,
            "n_months": n_months,
        },
    }


def evaluate(path: Path) -> dict:
    frame = _load_frame(path)
    if frame.empty:
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "error": "Tidak ada baris backtest.",
            "source": str(path),
            "horizon_results": {},
        }

    date_column = _date_column(frame)
    if date_column is None:
        raise ValueError("Kolom tanggal harus bernama 'date' atau 'signal_date'.")

    frame[date_column] = pd.to_datetime(frame[date_column], errors="coerce")
    results = {
        str(horizon): _horizon_result(frame, date_column, horizon)
        for horizon in HORIZONS
    }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": str(path),
        "methodology": {
            "type": "cross_sectional_per_date",
            "prediction": "horizon-specific VWAP position rank",
            "realization": "net return from next-session open",
            "minimum_tickers_per_date": MIN_TICKERS_PER_DATE,
            "monthly_stability": "calendar-month mean of daily IC",
            "horizons": [5, 20, 60],
            "no_time_series_per_stock": True,
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
