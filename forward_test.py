"""Forward-test evaluator for persisted screening signals."""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr


ROOT = Path(__file__).resolve().parent


def _configured_path(name: str, default: str) -> Path:
    path = Path(os.getenv(name, default))
    return path if path.is_absolute() else ROOT / path


DB_PATH = _configured_path("DB_PATH", "storage/screener.db")
OUT_PATH = _configured_path(
    "FORWARD_REPORT_PATH",
    "web/forward_test_data.json",
)
HORIZONS = (5, 10, 20)
COST_PCT = float(os.getenv("ROUND_TRIP_COST_PCT", "0.50"))
SLIPPAGE_PCT = float(
    os.getenv("ROUND_TRIP_SLIPPAGE_PCT", "0.20")
)
FRICTION_PCT = COST_PCT + SLIPPAGE_PCT
TIMEFRAME_TYPES = {
    "daily": "composite_daily",
    "weekly": "composite",
    "swing": "composite_swing",
}


def _load_signals(conn: sqlite3.Connection) -> pd.DataFrame:
    placeholders = ", ".join("?" for _ in (*TIMEFRAME_TYPES.values(), "vwap_multi"))
    query = f"""
        SELECT
            ticker,
            date,
            signal_type,
            direction AS signal,
            score,
            note,
            comp_trend,
            comp_wyckoff,
            comp_vwap,
            comp_comparative_strength,
            comp_support_resistance
        FROM signals
        WHERE signal_type IN ({placeholders})
        ORDER BY date, ticker, signal_type
    """
    values = (*TIMEFRAME_TYPES.values(), "vwap_multi")
    frame = pd.read_sql_query(query, conn, params=values)
    if frame.empty:
        return frame

    frame["date"] = pd.to_datetime(
        frame["date"],
        errors="coerce",
    )
    return frame.dropna(
        subset=["ticker", "date", "signal_type", "signal"]
    )


def _load_prices(
    conn: sqlite3.Connection,
) -> dict[str, pd.DataFrame]:
    frame = pd.read_sql_query(
        """
        SELECT ticker, date, open, close
        FROM prices
        ORDER BY ticker, date
        """,
        conn,
    )
    if frame.empty:
        return {}

    frame["date"] = pd.to_datetime(
        frame["date"],
        errors="coerce",
    )
    frame["open"] = pd.to_numeric(
        frame["open"],
        errors="coerce",
    )
    frame["close"] = pd.to_numeric(
        frame["close"],
        errors="coerce",
    )
    frame = frame.dropna(
        subset=["ticker", "date", "open", "close"]
    )

    return {
        str(ticker): (
            group
            .drop_duplicates("date", keep="last")
            .set_index("date")
            .sort_index()
        )
        for ticker, group in frame.groupby("ticker")
    }


def _parse_note(value: object) -> dict:
    if not isinstance(value, str) or not value.strip():
        return {}

    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}

    return parsed if isinstance(parsed, dict) else {}


def _future_returns(
    signal: pd.Series,
    prices: pd.DataFrame,
) -> dict:
    result = {
        f"return_{horizon}d": np.nan
        for horizon in HORIZONS
    }
    signal_date = pd.Timestamp(signal["date"])
    location = prices.index.searchsorted(
        signal_date,
        side="right",
    )

    if location >= len(prices):
        return result

    entry_open = float(
        prices.iloc[location]["open"]
    )
    if not np.isfinite(entry_open) or entry_open <= 0:
        return result

    result["entry_date"] = (
        prices.index[location].date().isoformat()
    )
    result["entry_open"] = entry_open

    for horizon in HORIZONS:
        exit_location = location + horizon - 1
        if exit_location >= len(prices):
            continue

        exit_close = float(
            prices.iloc[exit_location]["close"]
        )
        if not np.isfinite(exit_close) or exit_close <= 0:
            continue

        gross = (
            (exit_close / entry_open) - 1.0
        ) * 100.0
        result[f"return_{horizon}d"] = (
            gross - FRICTION_PCT
        )

    return result


def _summary(
    frame: pd.DataFrame,
    group_column: str,
    return_column: str,
) -> list[dict]:
    rows: list[dict] = []

    if (
        frame.empty
        or group_column not in frame
        or return_column not in frame
    ):
        return rows

    for label, group in frame.groupby(
        group_column,
        dropna=False,
    ):
        values = pd.to_numeric(
            group[return_column],
            errors="coerce",
        ).dropna()

        if values.empty:
            continue

        rows.append({
            group_column: str(label),
            "jumlah_sampel": int(len(values)),
            "rata_rata_return_pct": round(
                float(values.mean()),
                4,
            ),
            "median_return_pct": round(
                float(values.median()),
                4,
            ),
            "persen_untung": round(
                float((values > 0).mean() * 100),
                2,
            ),
            "return_terburuk": round(
                float(values.min()),
                4,
            ),
            "return_terbaik": round(
                float(values.max()),
                4,
            ),
        })

    return rows


def _daily_ic(
    frame: pd.DataFrame,
    horizon: int,
) -> dict:
    return_column = f"return_{horizon}d"

    if (
        frame.empty
        or "score" not in frame
        or return_column not in frame
    ):
        return {
            "mean": None,
            "median": None,
            "positive_rate": None,
            "days": 0,
        }

    subset = frame[
        frame["score"].notna()
        & frame[return_column].notna()
    ]
    values: list[float] = []

    for _, group in subset.groupby("date"):
        if (
            len(group) < 5
            or group["score"].nunique() < 2
        ):
            continue

        ic, _ = spearmanr(
            group["score"],
            group[return_column],
        )
        if np.isfinite(ic):
            values.append(float(ic))

    if not values:
        return {
            "mean": None,
            "median": None,
            "positive_rate": None,
            "days": 0,
        }

    array = np.asarray(values)
    return {
        "mean": round(float(array.mean()), 4),
        "median": round(float(np.median(array)), 4),
        "positive_rate": round(
            float((array > 0).mean() * 100),
            2,
        ),
        "days": len(values),
    }


def _detail_rows(
    frame: pd.DataFrame,
) -> list[dict]:
    if frame.empty:
        return []

    rows: list[dict] = []
    ordered = frame.sort_values(
        ["date", "ticker"],
        ascending=[False, True],
    ).head(50)

    for _, row in ordered.iterrows():
        returns = {}
        for horizon in HORIZONS:
            value = row.get(f"return_{horizon}d")
            returns[str(horizon)] = (
                round(float(value), 4)
                if pd.notna(value)
                else None
            )

        detail = {
            "ticker": str(row["ticker"]),
            "date": pd.Timestamp(
                row["date"]
            ).date().isoformat(),
            "signal": str(row["signal"]),
            "entry_price": (
                round(float(row["entry_open"]), 4)
                if pd.notna(row.get("entry_open"))
                else None
            ),
            "score": (
                round(float(row["score"]), 4)
                if pd.notna(row.get("score"))
                else None
            ),
            "returns": returns,
        }

        for component in (
            "trend",
            "wyckoff",
            "vwap",
            "comparative_strength",
            "support_resistance",
        ):
            value = row.get(f"comp_{component}")
            detail[f"comp_{component}"] = (
                round(float(value), 4)
                if pd.notna(value)
                else None
            )

        rows.append(detail)

    return rows


def evaluate_forward() -> dict:
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Database tidak ditemukan: {DB_PATH}"
        )

    with sqlite3.connect(DB_PATH) as conn:
        signals = _load_signals(conn)
        prices = _load_prices(conn)

    evaluated_rows: list[dict] = []

    for _, signal in signals.iterrows():
        ticker_prices = prices.get(
            str(signal["ticker"])
        )
        if ticker_prices is None or ticker_prices.empty:
            continue

        row = signal.to_dict()
        row.update(
            _future_returns(signal, ticker_prices)
        )

        if signal["signal_type"] == "vwap_multi":
            note = _parse_note(signal.get("note"))
            row["vwap_signal"] = (
                signal.get("signal")
                or note.get("signal")
            )
            row["vwap_confidence"] = note.get(
                "confidence"
            )

        evaluated_rows.append(row)

    evaluated = pd.DataFrame(evaluated_rows)
    for horizon in HORIZONS:
        column = f"return_{horizon}d"
        if column not in evaluated:
            evaluated[column] = np.nan

    weekly = evaluated[
        evaluated.get("signal_type")
        == TIMEFRAME_TYPES["weekly"]
    ].copy()
    vwap = evaluated[
        evaluated.get("signal_type")
        == "vwap_multi"
    ].copy()

    by_signal = {
        str(horizon): _summary(
            weekly,
            "signal",
            f"return_{horizon}d",
        )
        for horizon in HORIZONS
    }
    by_vwap_signal = {
        str(horizon): _summary(
            vwap,
            "vwap_signal",
            f"return_{horizon}d",
        )
        for horizon in HORIZONS
    }

    by_timeframe: dict[str, dict] = {}
    ic_by_timeframe: dict[str, dict] = {}

    for timeframe, signal_type in TIMEFRAME_TYPES.items():
        subset = evaluated[
            evaluated.get("signal_type")
            == signal_type
        ].copy()
        by_timeframe[timeframe] = {
            "total_sampel_terdaftar": int(
                len(subset)
            ),
            "total_sampel_matang": int(
                subset["return_5d"].notna().sum()
            ),
            "by_signal": {
                str(horizon): _summary(
                    subset,
                    "signal",
                    f"return_{horizon}d",
                )
                for horizon in HORIZONS
            },
        }
        ic_by_timeframe[timeframe] = {
            f"{horizon}d": _daily_ic(
                subset,
                horizon,
            )
            for horizon in HORIZONS
        }

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "jenis": "forward_test",
        "catatan": (
            "Sinyal diamati pada penutupan sesi dan dieksekusi "
            "pada pembukaan sesi berikutnya. Return sudah dikurangi "
            f"friction {FRICTION_PCT:.2f}%."
        ),
        "execution": "next_session_open",
        "horizons_hari_bursa": list(HORIZONS),
        "costs": {
            "round_trip_cost_pct": COST_PCT,
            "round_trip_slippage_pct": (
                SLIPPAGE_PCT
            ),
            "total_friction_pct": FRICTION_PCT,
        },
        "total_sampel_terdaftar": int(
            len(weekly)
        ),
        "total_sampel_matang": int(
            weekly["return_5d"].notna().sum()
        ),
        "by_signal": by_signal,
        "by_vwap_signal": by_vwap_signal,
        "by_timeframe": by_timeframe,
        "detail_terbaru": _detail_rows(weekly),
        "ic": ic_by_timeframe["weekly"],
        "ic_by_timeframe": ic_by_timeframe,
    }

    OUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    OUT_PATH.write_text(
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        ),
        encoding="utf-8",
    )
    return payload


if __name__ == "__main__":
    print(
        json.dumps(
            evaluate_forward(),
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
    )
