"""Forward-test evaluator with next-session execution and explicit trading friction."""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

DB_PATH = Path(os.getenv("DB_PATH", "data/screener.db"))
OUT_PATH = Path(os.getenv("FORWARD_REPORT_PATH", "reports/forward_test_latest.json"))
HORIZONS = (5, 10, 20)
COST_PCT = float(os.getenv("ROUND_TRIP_COST_PCT", "0.50"))
SLIPPAGE_PCT = float(os.getenv("ROUND_TRIP_SLIPPAGE_PCT", "0.20"))
FRICTION_PCT = COST_PCT + SLIPPAGE_PCT


def _load_signals(conn: sqlite3.Connection) -> pd.DataFrame:
    query = """
        SELECT ticker, date, signal_type, score, note
        FROM signals
        WHERE signal_type IN ('composite', 'vwap_multi')
        ORDER BY date, ticker
    """
    frame = pd.read_sql_query(query, conn)
    if frame.empty:
        return frame
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    return frame.dropna(subset=["ticker", "date", "signal_type"])


def _load_prices(conn: sqlite3.Connection) -> dict[str, pd.DataFrame]:
    frame = pd.read_sql_query(
        "SELECT ticker, date, open, close FROM price_history ORDER BY ticker, date", conn
    )
    if frame.empty:
        return {}
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame["open"] = pd.to_numeric(frame["open"], errors="coerce")
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame = frame.dropna(subset=["ticker", "date", "open", "close"])
    return {
        ticker: group.drop_duplicates("date", keep="last").set_index("date").sort_index()
        for ticker, group in frame.groupby("ticker")
    }


def _parse_note(value: object) -> dict:
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _future_returns(signal: pd.Series, prices: pd.DataFrame) -> dict:
    result = {f"return_{h}d": np.nan for h in HORIZONS}
    signal_date = pd.Timestamp(signal["date"])
    location = prices.index.searchsorted(signal_date, side="right")
    if location >= len(prices):
        return result

    entry_open = float(prices.iloc[location]["open"])
    if not np.isfinite(entry_open) or entry_open <= 0:
        return result

    for horizon in HORIZONS:
        exit_location = location + horizon - 1
        if exit_location >= len(prices):
            continue
        exit_close = float(prices.iloc[exit_location]["close"])
        gross = (exit_close / entry_open - 1.0) * 100.0
        result[f"gross_return_{horizon}d"] = gross
        result[f"return_{horizon}d"] = gross - FRICTION_PCT

    result["entry_date"] = prices.index[location].date().isoformat()
    result["entry_open"] = entry_open
    return result


def _group_stats(frame: pd.DataFrame, field: str) -> dict:
    output: dict[str, dict] = {}
    if field not in frame.columns:
        return output
    for label, group in frame.dropna(subset=[field]).groupby(field):
        stats: dict[str, float | int | None] = {"count": int(len(group))}
        for horizon in HORIZONS:
            values = pd.to_numeric(group[f"return_{horizon}d"], errors="coerce").dropna()
            stats[f"mean_{horizon}d"] = round(float(values.mean()), 4) if len(values) else None
            stats[f"median_{horizon}d"] = round(float(values.median()), 4) if len(values) else None
            stats[f"winrate_{horizon}d"] = round(float((values > 0).mean() * 100), 2) if len(values) else None
            stats[f"n_{horizon}d"] = int(len(values))
        output[str(label)] = stats
    return output


def _daily_ic(frame: pd.DataFrame, horizon: int) -> dict:
    subset = frame[
        (frame["signal_type"] == "composite")
        & frame["score"].notna()
        & frame[f"return_{horizon}d"].notna()
    ]
    values = []
    for _, group in subset.groupby("date"):
        if len(group) < 5 or group["score"].nunique() < 2:
            continue
        ic, _ = spearmanr(group["score"], group[f"return_{horizon}d"])
        if np.isfinite(ic):
            values.append(float(ic))
    if not values:
        return {"mean": None, "median": None, "positive_rate": None, "days": 0}
    return {
        "mean": round(float(np.mean(values)), 4),
        "median": round(float(np.median(values)), 4),
        "positive_rate": round(float(np.mean(np.asarray(values) > 0) * 100), 2),
        "days": len(values),
    }


def evaluate_forward() -> dict:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database tidak ditemukan: {DB_PATH}")

    with sqlite3.connect(DB_PATH) as conn:
        signals = _load_signals(conn)
        prices = _load_prices(conn)

    rows = []
    for _, signal in signals.iterrows():
        ticker_prices = prices.get(str(signal["ticker"]))
        if ticker_prices is None or ticker_prices.empty:
            continue
        note = _parse_note(signal.get("note"))
        row = signal.to_dict()
        row.update(_future_returns(signal, ticker_prices))
        row["vwap_signal"] = note.get("signal")
        row["vwap_confidence"] = note.get("confidence")
        rows.append(row)

    evaluated = pd.DataFrame(rows)
    for horizon in HORIZONS:
        column = f"return_{horizon}d"
        if column not in evaluated:
            evaluated[column] = np.nan

    latest = []
    if not evaluated.empty:
        keep = ["ticker", "date", "signal_type", "score", "vwap_signal", "entry_date"]
        keep += [f"return_{h}d" for h in HORIZONS]
        latest = (
            evaluated.sort_values("date", ascending=False)
            .head(50)[keep]
            .replace({np.nan: None})
            .assign(date=lambda x: x["date"].dt.date.astype(str))
            .to_dict("records")
        )

    report = {
        "methodology": {
            "signal_observed": "session close",
            "execution": "next_session_open",
            "round_trip_cost_pct": COST_PCT,
            "round_trip_slippage_pct": SLIPPAGE_PCT,
            "reported_returns": "net of configured friction",
        },
        "sample_count": int(len(evaluated)),
        "by_signal": _group_stats(evaluated[evaluated["signal_type"] == "composite"], "signal_type"),
        "by_vwap_signal": _group_stats(evaluated[evaluated["signal_type"] == "vwap_multi"], "vwap_signal"),
        "ic": {f"{h}d": _daily_ic(evaluated, h) for h in HORIZONS},
        "detail_terbaru": latest,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(evaluate_forward(), indent=2, ensure_ascii=False))
