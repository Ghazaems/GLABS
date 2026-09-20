"""
Backtest no-lookahead untuk sistem GLABS.

Prinsip:
- Sinyal hanya memakai data sampai penutupan hari t.
- Entry terjadi pada Open hari bursa berikutnya (t+1).
- Benchmark disejajarkan berdasarkan tanggal, bukan nomor baris.
- Return utama sudah dikurangi biaya dan slippage eksplisit.
- Mean, median, win rate, dan tail outcome dilaporkan bersama.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from data.yfinance_fetcher import fetch_batch, fetch_daily
from main import DEFAULT_WATCHLIST
from screener.scoring import classify_signal, compute_score
from screener.trend import (
    support_resistance_levels,
    trend_structure,
)
from screener.vwap import (
    analyze_vwap_signals,
    price_vs_vwap,
)
from screener.wyckoff import (
    analyze_latest_trading_range,
    comparative_strength,
)


PERIOD = "3y"
WARMUP_BARS = 120
HORIZONS = [5, 10, 20]
STRIDE = 5

ROUND_TRIP_COST_PCT = float(
    os.getenv("ROUND_TRIP_COST_PCT", "0.50")
)
ROUND_TRIP_SLIPPAGE_PCT = float(
    os.getenv("ROUND_TRIP_SLIPPAGE_PCT", "0.20")
)
TOTAL_FRICTION_PCT = (
    ROUND_TRIP_COST_PCT
    + ROUND_TRIP_SLIPPAGE_PCT
)


def _aligned_benchmark(
    benchmark: pd.DataFrame | None,
    cutoff,
) -> pd.DataFrame | None:
    if benchmark is None or benchmark.empty:
        return None

    aligned = benchmark.loc[
        benchmark.index <= cutoff
    ]

    return aligned if not aligned.empty else None


def _safe_float(value) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None

    return result if np.isfinite(result) else None


def _summary(
    frame: pd.DataFrame,
    group_column: str,
    return_column: str,
) -> list[dict]:
    rows = []

    for label, group in frame.groupby(
        group_column,
        dropna=False,
    ):
        values = group[return_column].dropna()

        if values.empty:
            continue

        rows.append(
            {
                group_column: str(label),
                "jumlah_sampel": int(len(values)),
                "rata_rata_return_pct": round(
                    float(values.mean()),
                    3,
                ),
                "median_return_pct": round(
                    float(values.median()),
                    3,
                ),
                "persen_untung": round(
                    float((values > 0).mean() * 100),
                    2,
                ),
                "return_terburuk": round(
                    float(values.min()),
                    3,
                ),
                "return_terbaik": round(
                    float(values.max()),
                    3,
                ),
            }
        )

    return rows


def run_backtest() -> pd.DataFrame:
    print(
        f"Mengambil data {PERIOD} untuk "
        f"{len(DEFAULT_WATCHLIST)} saham..."
    )

    price_data = fetch_batch(
        DEFAULT_WATCHLIST,
        period=PERIOD,
    )
    ihsg = fetch_daily("^JKSE", period=PERIOD)

    rows: list[dict] = []
    maximum_horizon = max(HORIZONS)

    for ticker, dataframe in price_data.items():
        dataframe = dataframe.sort_index()
        total_rows = len(dataframe)
        minimum_needed = (
            WARMUP_BARS
            + maximum_horizon
            + 2
        )

        if total_rows < minimum_needed:
            continue

        print(
            f"Memproses {ticker} "
            f"({total_rows} hari data)..."
        )

        stop = total_rows - maximum_horizon - 1

        for signal_index in range(
            WARMUP_BARS,
            stop,
            STRIDE,
        ):
            history = dataframe.iloc[
                :signal_index + 1
            ]
            signal_date = history.index[-1]
            entry_index = signal_index + 1
            entry_date = dataframe.index[entry_index]

            entry_price = _safe_float(
                dataframe["Open"].iloc[entry_index]
            )

            if entry_price is None or entry_price <= 0:
                continue

            benchmark_history = _aligned_benchmark(
                ihsg,
                signal_date,
            )

            trend = trend_structure(history)
            support_resistance = (
                support_resistance_levels(history)
            )
            wyckoff = (
                analyze_latest_trading_range(history)
            )
            vwap_medium = price_vs_vwap(
                history,
                window=20,
            )
            vwap_analysis = analyze_vwap_signals(
                history
            )

            if benchmark_history is None:
                comparative = {
                    "status": "no_ihsg_data",
                }
            else:
                comparative = comparative_strength(
                    history,
                    benchmark_history,
                )

            scored = compute_score(
                trend,
                wyckoff,
                vwap_medium,
                comparative,
                support_resistance,
            )
            composite_signal = classify_signal(
                scored
            )

            row = {
                "ticker": ticker,
                "date": signal_date.strftime(
                    "%Y-%m-%d"
                ),
                "entry_date": entry_date.strftime(
                    "%Y-%m-%d"
                ),
                "entry_price": round(
                    entry_price,
                    4,
                ),
                "execution": "next_session_open",
                "score": scored["score"],
                "signal": composite_signal,
                "vwap_signal": vwap_analysis.get(
                    "signal",
                    "WAIT",
                ),
                "vwap_regime": vwap_analysis.get(
                    "regime",
                    "unknown",
                ),
                "vwap_rvol": vwap_analysis.get(
                    "rvol"
                ),
            }

            for name, component_score in (
                scored["breakdown"].items()
            ):
                row[f"comp_{name}"] = (
                    component_score
                )

            for horizon in HORIZONS:
                exit_index = (
                    entry_index + horizon
                )
                exit_price = _safe_float(
                    dataframe["Close"].iloc[
                        exit_index
                    ]
                )

                if (
                    exit_price is None
                    or exit_price <= 0
                ):
                    gross_return = np.nan
                    net_return = np.nan
                else:
                    gross_return = (
                        (
                            exit_price
                            / entry_price
                        )
                        - 1.0
                    ) * 100.0
                    net_return = (
                        gross_return
                        - TOTAL_FRICTION_PCT
                    )

                row[
                    f"gross_return_{horizon}d_pct"
                ] = round(gross_return, 4)
                row[
                    f"return_{horizon}d_pct"
                ] = round(net_return, 4)

            rows.append(row)

    if not rows:
        raise RuntimeError(
            "Tidak ada sampel backtest yang valid."
        )

    result = pd.DataFrame(rows)
    result.to_csv(
        "backtest_results.csv",
        index=False,
    )

    print_report(result)
    export_dashboard_json(result)

    return result


def print_report(frame: pd.DataFrame) -> None:
    print("\n" + "=" * 72)
    print("BACKTEST NEXT-OPEN, SETELAH BIAYA")
    print("=" * 72)
    print(f"Total sampel: {len(frame)}")
    print(
        "Friction round-trip: "
        f"{TOTAL_FRICTION_PCT:.2f}%"
    )

    for horizon in HORIZONS:
        column = f"return_{horizon}d_pct"

        print(
            f"\nVWAP signal — horizon "
            f"{horizon} hari:"
        )
        print(
            pd.DataFrame(
                _summary(
                    frame,
                    "vwap_signal",
                    column,
                )
            ).to_string(index=False)
        )

        print(
            f"\nComposite lama — horizon "
            f"{horizon} hari:"
        )
        print(
            pd.DataFrame(
                _summary(
                    frame,
                    "signal",
                    column,
                )
            ).to_string(index=False)
        )


def export_dashboard_json(
    frame: pd.DataFrame,
) -> None:
    by_signal: dict[str, list[dict]] = {}
    by_vwap_signal: dict[str, list[dict]] = {}
    by_score_quartile: dict[
        str,
        list[dict],
    ] = {}

    scored = frame.copy()
    scored["kelompok_skor"] = pd.qcut(
        scored["score"],
        q=4,
        duplicates="drop",
    )

    for horizon in HORIZONS:
        key = str(horizon)
        return_column = (
            f"return_{horizon}d_pct"
        )

        by_signal[key] = _summary(
            scored,
            "signal",
            return_column,
        )
        by_vwap_signal[key] = _summary(
            scored,
            "vwap_signal",
            return_column,
        )
        by_score_quartile[key] = _summary(
            scored.assign(
                kelompok_skor=scored[
                    "kelompok_skor"
                ].astype(str)
            ),
            "kelompok_skor",
            return_column,
        )

    extreme_count = int(
        sum(
            (
                frame[
                    f"gross_return_{horizon}d_pct"
                ].abs()
                > 100
            ).sum()
            for horizon in HORIZONS
        )
    )

    payload = {
        "generated_at": datetime.now().isoformat(),
        "period": PERIOD,
        "execution": "next_session_open",
        "price_adjustment": "auto_adjust_true",
        "warmup_bars": WARMUP_BARS,
        "stride": STRIDE,
        "horizons_hari_bursa": HORIZONS,
        "costs": {
            "round_trip_cost_pct": (
                ROUND_TRIP_COST_PCT
            ),
            "round_trip_slippage_pct": (
                ROUND_TRIP_SLIPPAGE_PCT
            ),
            "total_friction_pct": (
                TOTAL_FRICTION_PCT
            ),
        },
        "total_sampel": int(len(frame)),
        "extreme_gross_return_count": (
            extreme_count
        ),
        "by_signal": by_signal,
        "by_vwap_signal": by_vwap_signal,
        "by_score_quartile": (
            by_score_quartile
        ),
        "catatan": (
            "Return utama memakai entry Open sesi berikutnya "
            "dan sudah dikurangi friction. Mean harus dibaca "
            "bersama median dan tail outcome."
        ),
    }

    output = (
        Path(__file__).resolve().parent
        / "web"
        / "backtest_data.json"
    )
    output.parent.mkdir(exist_ok=True)

    with open(
        output,
        "w",
        encoding="utf-8",
    ) as destination:
        json.dump(
            payload,
            destination,
            indent=2,
            ensure_ascii=False,
            default=str,
        )

    print(
        f"\nHasil tersimpan ke {output}"
    )


if __name__ == "__main__":
    run_backtest()
