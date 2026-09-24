"""Robust cross-sectional statistical validation for Wyckoff events."""
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

from analysis_contract import HORIZONS


TIMEFRAMES = {
    "daily": {"label": "Daily", "horizon": HORIZONS[0]},
    "weekly": {"label": "Weekly", "horizon": HORIZONS[1]},
    "swing": {"label": "Swing", "horizon": HORIZONS[2]},
}
EVENT_DIRECTION = {
    "SC": 1,
    "BC": -1,
    "Spring": 1,
    "UT": -1,
    "SOS": 1,
    "SOW": -1,
    "LPS": 1,
    "LPSY": -1,
}
MIN_TICKERS_PER_DATE = 30
MIN_EVENT_TICKERS = 5
MIN_CONTROL_TICKERS = 20
MIN_VALID_DATES = 12
MAX_WYCKOFF_SCORE = 30.0
FDR_ALPHA = 0.05


def _safe_ic(group: pd.DataFrame, signal: str, target: str) -> float | None:
    pair = group[[signal, target]].apply(pd.to_numeric, errors="coerce").dropna()
    event_count = int((pair[signal] > 0).sum())
    control_count = int((pair[signal] <= 0).sum())
    if (
        len(pair) < MIN_TICKERS_PER_DATE
        or event_count < MIN_EVENT_TICKERS
        or control_count < MIN_CONTROL_TICKERS
        or pair[target].nunique() < 5
    ):
        return None
    value, _ = spearmanr(pair[signal], pair[target])
    return float(value) if np.isfinite(value) else None


def _hac_mean_test(values: pd.Series, horizon: int) -> tuple[float, float, float, int]:
    array = values.to_numpy(dtype=float)
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


def _event_result(frame: pd.DataFrame, timeframe: str, event: str) -> dict:
    metadata = TIMEFRAMES[timeframe]
    horizon = metadata["horizon"]
    signal_column = f"wyckoff_{timeframe}_{event.lower()}"
    return_column = f"return_{horizon}d_pct"
    base = {
        "wyckoff_event": event,
        "timeframe": metadata["label"],
        "horizon": f"{horizon}D",
        "expected_direction": EVENT_DIRECTION[event],
    }

    if signal_column not in frame or return_column not in frame:
        return {
            **base,
            "verdict": "unavailable",
            "headline": "Belum tersedia",
            "statistics": None,
            "score_weight": 0.0,
        }

    observations: dict[pd.Timestamp, float] = {}
    for date, group in frame.groupby("date"):
        value = _safe_ic(group, signal_column, return_column)
        if value is not None:
            observations[pd.Timestamp(date)] = value
    daily_ic = pd.Series(observations, dtype=float).sort_index()
    n_dates = int(len(daily_ic))

    if n_dates < MIN_VALID_DATES:
        return {
            **base,
            "verdict": "insufficient_data",
            "headline": "Data event belum cukup",
            "statistics": None,
            "score_weight": 0.0,
        }

    mean_ic, t_stat, p_value, hac_lags = _hac_mean_test(daily_ic, horizon)
    std_ic = float(daily_ic.std(ddof=1))
    monthly_ic = daily_ic.resample("ME").mean().dropna()
    positive_months_pct = (
        float((monthly_ic > 0).mean() * 100.0) if len(monthly_ic) else 0.0
    )

    return {
        **base,
        "verdict": "pending_fdr",
        "headline": "Menunggu koreksi pengujian",
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
        "score_weight": 0.0,
    }


def _apply_fdr(rows: list[dict]) -> None:
    tested = [row for row in rows if row.get("statistics") is not None]
    q_values = _benjamini_hochberg([
        row["statistics"]["p_value_raw"] for row in tested
    ])

    for row, q_value in zip(tested, q_values):
        stats = row["statistics"]
        stats["q_value_fdr"] = round(float(q_value), 6)
        mean_ic = float(stats["mean_ic"])
        expected_direction = int(row["expected_direction"])
        direction_matches = mean_ic * expected_direction > 0

        if q_value < FDR_ALPHA and direction_matches:
            row["verdict"] = "validated"
            row["headline"] = "Lolos HAC dan koreksi FDR"
            row["score_weight"] = round(
                expected_direction * MAX_WYCKOFF_SCORE * abs(mean_ic),
                2,
            )
        elif q_value < FDR_ALPHA:
            row["verdict"] = "reversed"
            row["headline"] = "Arah statistik terbalik setelah FDR"
            row["score_weight"] = 0.0
        else:
            row["verdict"] = "contextual_only"
            row["headline"] = "Konteks visual saja"
            row["score_weight"] = 0.0


def _timeframe_summary(rows: list[dict], timeframe: str) -> dict:
    selected = [
        row for row in rows
        if row["timeframe"] == TIMEFRAMES[timeframe]["label"]
    ]
    validated = [
        row["wyckoff_event"] for row in selected
        if row["verdict"] == "validated"
    ]
    reversed_events = [
        row["wyckoff_event"] for row in selected
        if row["verdict"] == "reversed"
    ]
    contextual = [
        row["wyckoff_event"] for row in selected
        if row["verdict"] in {
            "contextual_only", "insufficient_data", "unavailable"
        }
    ]

    if validated:
        headline = (
            f"{len(validated)} event lolos HAC dan koreksi FDR; "
            "hanya event tersebut yang boleh memengaruhi skor."
        )
    else:
        headline = (
            "Belum ada event yang lolos HAC dan koreksi FDR; "
            "Wyckoff tetap konteks visual."
        )
    if reversed_events:
        headline += f" {len(reversed_events)} event berarah terbalik."

    return {
        "label": TIMEFRAMES[timeframe]["label"],
        "horizon": f"{TIMEFRAMES[timeframe]['horizon']}D",
        "headline": headline,
        "validated_events": validated,
        "contextual_events": contextual,
        "reversed_events": reversed_events,
    }


def evaluate(path: Path) -> dict:
    frame = pd.read_csv(path)
    if "date" not in frame:
        raise ValueError("backtest harus memiliki kolom date.")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame.dropna(subset=["date"])

    rows = [
        _event_result(frame, timeframe, event)
        for timeframe in TIMEFRAMES
        for event in EVENT_DIRECTION
    ]
    _apply_fdr(rows)

    calibration = {
        timeframe: {
            row["wyckoff_event"]: row["score_weight"]
            for row in rows
            if (
                row["timeframe"] == TIMEFRAMES[timeframe]["label"]
                and row["verdict"] == "validated"
                and row["score_weight"] != 0
            )
        }
        for timeframe in TIMEFRAMES
    }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": str(path),
        "methodology": {
            "type": "cross_sectional_per_date_per_event",
            "signal": "binary event presence on signal date",
            "minimum_tickers_per_date": MIN_TICKERS_PER_DATE,
            "minimum_event_tickers": MIN_EVENT_TICKERS,
            "minimum_control_tickers": MIN_CONTROL_TICKERS,
            "minimum_valid_dates": MIN_VALID_DATES,
            "inference": "HAC/Newey-West intercept test",
            "multiple_testing": "Benjamini-Hochberg FDR across all event/timeframe tests",
            "monthly_stability": "calendar-month mean of cross-sectional IC",
            "timeframes": {
                key: value["horizon"] for key, value in TIMEFRAMES.items()
            },
            "ambiguous_events": {"AR": "visual_only", "ST": "visual_only"},
            "universe_warning": "current static universe; survivorship bias not eliminated",
        },
        "results": rows,
        "calibration": calibration,
        "timeframe_summary": {
            timeframe: _timeframe_summary(rows, timeframe)
            for timeframe in TIMEFRAMES
        },
    }


def main() -> None:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("backtest_results.csv")
    output = (
        Path(sys.argv[2])
        if len(sys.argv) > 2
        else Path("web/wyckoff_ic_data.json")
    )
    report = evaluate(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
