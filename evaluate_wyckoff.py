"""Cross-sectional statistical validation for Wyckoff events."""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr, t as student_t

TIMEFRAMES = {
    "daily": {"label": "Daily", "horizon": 5},
    "weekly": {"label": "Weekly", "horizon": 20},
    "swing": {"label": "Swing", "horizon": 60},
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
MIN_TICKERS_PER_DATE = 5
MAX_WYCKOFF_SCORE = 30.0


def _safe_ic(group: pd.DataFrame, signal: str, target: str) -> float | None:
    pair = group[[signal, target]].apply(pd.to_numeric, errors="coerce").dropna()
    if (
        len(pair) < MIN_TICKERS_PER_DATE
        or pair[signal].nunique() < 2
        or pair[target].nunique() < 2
    ):
        return None
    value, _ = spearmanr(pair[signal], pair[target])
    return float(value) if np.isfinite(value) else None


def _event_result(
    frame: pd.DataFrame,
    timeframe: str,
    event: str,
) -> dict:
    metadata = TIMEFRAMES[timeframe]
    horizon = metadata["horizon"]
    signal_column = f"wyckoff_{timeframe}_{event.lower()}"
    return_column = f"return_{horizon}d_pct"
    base = {
        "wyckoff_event": event,
        "timeframe": metadata["label"],
        "horizon": f"{horizon}D",
    }
    if signal_column not in frame or return_column not in frame:
        return {
            **base,
            "verdict": "unavailable",
            "headline": "Belum tersedia",
            "statistics": None,
            "score_weight": 0.0,
        }

    observations = {}
    for date, group in frame.groupby("date"):
        value = _safe_ic(group, signal_column, return_column)
        if value is not None:
            observations[pd.Timestamp(date)] = value
    daily_ic = pd.Series(observations, dtype=float).sort_index()
    n_dates = int(len(daily_ic))
    if n_dates < 2:
        return {
            **base,
            "verdict": "insufficient_data",
            "headline": "Data event belum cukup",
            "statistics": None,
            "score_weight": 0.0,
        }

    mean_ic = float(daily_ic.mean())
    std_ic = float(daily_ic.std(ddof=1))
    if std_ic > 0 and np.isfinite(std_ic):
        t_stat = mean_ic / (std_ic / math.sqrt(n_dates))
        p_value = float(2.0 * student_t.sf(abs(t_stat), df=n_dates - 1))
    else:
        t_stat = None
        p_value = 0.0 if mean_ic != 0 else 1.0

    monthly_ic = daily_ic.resample("ME").mean().dropna()
    positive_months_pct = (
        float((monthly_ic > 0).mean() * 100.0)
        if len(monthly_ic)
        else 0.0
    )
    expected_direction = EVENT_DIRECTION[event]
    direction_matches = mean_ic * expected_direction > 0
    significant = p_value < 0.05

    if significant and direction_matches:
        verdict = "validated"
        headline = "Terbukti sesuai arah"
        score_weight = round(
            expected_direction
            * MAX_WYCKOFF_SCORE
            * abs(mean_ic),
            2,
        )
    elif significant:
        verdict = "reversed"
        headline = "Arah statistik terbalik"
        score_weight = 0.0
    else:
        verdict = "contextual_only"
        headline = "Konteks visual saja"
        score_weight = 0.0

    return {
        **base,
        "verdict": verdict,
        "headline": headline,
        "statistics": {
            "mean_ic": round(mean_ic, 4),
            "std_ic": round(std_ic, 4),
            "t_stat": (
                round(float(t_stat), 4)
                if t_stat is not None
                else None
            ),
            "p_value": round(p_value, 4),
            "positive_months_pct": round(
                positive_months_pct,
                2,
            ),
            "n_dates": n_dates,
            "n_months": int(len(monthly_ic)),
        },
        "score_weight": score_weight,
    }


def _timeframe_summary(rows: list[dict], timeframe: str) -> dict:
    selected = [
        row
        for row in rows
        if row["timeframe"]
        == TIMEFRAMES[timeframe]["label"]
    ]
    validated = [
        row["wyckoff_event"]
        for row in selected
        if row["verdict"] == "validated"
    ]
    reversed_events = [
        row["wyckoff_event"]
        for row in selected
        if row["verdict"] == "reversed"
    ]
    contextual = [
        row["wyckoff_event"]
        for row in selected
        if row["verdict"]
        in {
            "contextual_only",
            "insufficient_data",
            "unavailable",
        }
    ]

    if validated:
        headline = (
            f"{len(validated)} event lolos validasi; "
            "hanya event tersebut yang boleh memengaruhi skor."
        )
    else:
        headline = (
            "Belum ada event yang boleh memengaruhi skor; "
            "Wyckoff tetap konteks visual."
        )
    if reversed_events:
        headline += (
            f" {len(reversed_events)} event menunjukkan arah terbalik."
        )

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
    frame["date"] = pd.to_datetime(
        frame["date"],
        errors="coerce",
    )
    frame = frame.dropna(subset=["date"])

    rows = [
        _event_result(frame, timeframe, event)
        for timeframe in TIMEFRAMES
        for event in EVENT_DIRECTION
    ]
    calibration = {
        timeframe: {
            row["wyckoff_event"]: row["score_weight"]
            for row in rows
            if row["timeframe"]
            == TIMEFRAMES[timeframe]["label"]
            and row["verdict"] == "validated"
            and row["score_weight"] != 0
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
            "monthly_stability": "calendar-month mean of daily IC",
            "timeframes": {
                key: value["horizon"]
                for key, value in TIMEFRAMES.items()
            },
            "ambiguous_events": {
                "AR": "visual_only",
                "ST": "visual_only",
            },
        },
        "results": rows,
        "calibration": calibration,
        "timeframe_summary": {
            timeframe: _timeframe_summary(
                rows,
                timeframe,
            )
            for timeframe in TIMEFRAMES
        },
    }


def main() -> None:
    source = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else Path("backtest_results.csv")
    )
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
