"""
Pipeline screening otomatis untuk 500 emiten IDX.

Dijalankan terjadwal oleh GitHub Actions setelah penutupan pasar.
Menghasilkan sinyal VWAP BUY/HOLD/WAIT/REDUCE/EXIT/AVOID tanpa
mengubah kontrak data dashboard yang sudah ada.
"""

import json
import os
from datetime import datetime
from pathlib import Path

import pandas as pd

from data.yfinance_fetcher import fetch_batch, fetch_daily
from idx_tickers_500 import IDX_TICKERS_500
from screener.scoring import classify_signal, compute_score
from screener.trend import (
    find_swing_points,
    support_resistance_levels,
    trend_structure,
)
from screener.volatility import forecast_volatility_batch
from screener.vwap import (
    analyze_vwap_signals,
    price_vs_vwap,
    rolling_vwap,
)
from screener.wyckoff import (
    analyze_latest_trading_range,
    comparative_strength,
)
from storage.db import (
    add_to_watchlist,
    init_db,
    save_signal,
    upsert_prices,
)


EXPECTED_TICKER_COUNT = 500
MINIMUM_ANALYSIS_ROWS = 65
MINIMUM_GARCH_ROWS = 120
DEFAULT_WATCHLIST = IDX_TICKERS_500


def load_wyckoff_calibration(
    path: Path = Path("web/wyckoff_ic_data.json"),
) -> dict[str, dict[str, float]]:
    """Muat hanya bobot event yang sudah lolos validasi statistik."""
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8")
        )
    except (
        FileNotFoundError,
        json.JSONDecodeError,
        OSError,
    ):
        return {
            "daily": {},
            "weekly": {},
            "swing": {},
        }

    calibration = payload.get("calibration", {})
    return {
        timeframe: {
            event: float(weight)
            for event, weight in calibration.get(
                timeframe,
                {},
            ).items()
            if isinstance(weight, (int, float))
        }
        for timeframe in (
            "daily",
            "weekly",
            "swing",
        )
    }


def clean_number(value):
    """Ubah nilai numerik menjadi float dua desimal."""
    if value is None or pd.isna(value):
        return None

    return round(float(value), 2)


def validate_ticker_universe(
    tickers: list[str],
) -> None:
    """Pastikan universe berisi tepat 500 ticker unik."""
    if len(tickers) != EXPECTED_TICKER_COUNT:
        raise RuntimeError(
            f"Universe harus berisi "
            f"{EXPECTED_TICKER_COUNT} ticker, "
            f"tetapi ditemukan {len(tickers)}."
        )

    if len(set(tickers)) != len(tickers):
        raise RuntimeError(
            "Universe mengandung ticker duplikat."
        )


def build_price_history(
    dataframe: pd.DataFrame,
) -> list[dict]:
    """Buat data harga untuk chart dashboard."""
    visual = find_swing_points(
        dataframe.tail(180).copy()
    )

    visual["vwap_5"] = rolling_vwap(
        visual,
        window=5,
    )
    visual["vwap_20"] = rolling_vwap(
        visual,
        window=20,
    )
    visual["vwap_60"] = rolling_vwap(
        visual,
        window=60,
    )

    history = []

    for index, row in visual.iterrows():
        volume = row.get("Volume")

        history.append({
            "date": index.strftime("%Y-%m-%d"),
            "open": clean_number(row.get("Open")),
            "high": clean_number(row.get("High")),
            "low": clean_number(row.get("Low")),
            "close": clean_number(row.get("Close")),
            "volume": (
                int(volume)
                if volume is not None
                and not pd.isna(volume)
                else 0
            ),
            # Key "vwap" dipertahankan agar HTML lama tetap kompatibel.
            "vwap": clean_number(
                row.get("vwap_5")
            ),
            "vwap_20": clean_number(
                row.get("vwap_20")
            ),
            "vwap_60": clean_number(
                row.get("vwap_60")
            ),
            "swing_high": clean_number(
                row.get("swing_high")
            ),
            "swing_low": clean_number(
                row.get("swing_low")
            ),
        })

    return history


def safe_comparative_strength(
    stock_data: pd.DataFrame,
    benchmark: pd.DataFrame | None,
    window: int | None = None,
    missing_status: str = "no_benchmark_data",
) -> dict:
    """Hitung comparative strength dengan aman."""
    if benchmark is None or benchmark.empty:
        return {"status": missing_status}

    try:
        if window is None:
            return comparative_strength(
                stock_data,
                benchmark,
            )

        return comparative_strength(
            stock_data,
            benchmark,
            window=window,
        )

    except Exception as error:
        return {
            "status": "calculation_failed",
            "error": (
                f"{type(error).__name__}: "
                f"{error}"
            ),
        }


def process_ticker(
    ticker: str,
    dataframe: pd.DataFrame,
    ihsg: pd.DataFrame | None,
    lq45: pd.DataFrame | None,
    volatility_results: dict[str, dict],
    wyckoff_calibration: dict[str, dict[str, float]],
) -> dict:
    """Analisis satu ticker dan susun hasil dashboard."""
    upsert_prices(ticker, dataframe)

    date_string = dataframe.index[
        -1
    ].strftime("%Y-%m-%d")

    # Daily memakai struktur harga 2 hari dan VWAP 5D. Ini dihitung
    # terpisah agar toggle Daily tidak pernah memakai ulang hasil Weekly.
    trend_daily = trend_structure(
        dataframe,
        window=2,
    )

    trend = trend_structure(
        dataframe,
        window=5,
    )

    trend_swing = trend_structure(
        dataframe,
        window=20,
    )

    support_resistance_daily = (
        support_resistance_levels(
            dataframe,
            window=2,
            lookback=20,
        )
    )

    support_resistance = (
        support_resistance_levels(
            dataframe,
            window=5,
            lookback=60,
        )
    )

    support_resistance_swing = (
        support_resistance_levels(
            dataframe,
            window=20,
            lookback=180,
        )
    )

    vwap_fast = price_vs_vwap(
        dataframe,
        window=5,
    )
    vwap_medium = price_vs_vwap(
        dataframe,
        window=20,
    )
    vwap_swing = price_vs_vwap(
        dataframe,
        window=60,
    )
    vwap_analysis = analyze_vwap_signals(
        dataframe
    )

    wyckoff_daily = analyze_latest_trading_range(
        dataframe,
        timeframe="daily",
    )
    wyckoff = analyze_latest_trading_range(
        dataframe,
        timeframe="weekly",
    )
    wyckoff_swing = analyze_latest_trading_range(
        dataframe,
        timeframe="swing",
    )

    cs_ihsg_daily = safe_comparative_strength(
        dataframe,
        ihsg,
        window=5,
        missing_status="no_ihsg_data",
    )

    cs_ihsg = safe_comparative_strength(
        dataframe,
        ihsg,
        missing_status="no_ihsg_data",
    )

    cs_ihsg_swing = safe_comparative_strength(
        dataframe,
        ihsg,
        window=60,
        missing_status="no_ihsg_data",
    )

    cs_lq45_daily = safe_comparative_strength(
        dataframe,
        lq45,
        window=5,
        missing_status="no_lq45_data",
    )

    cs_lq45 = safe_comparative_strength(
        dataframe,
        lq45,
        missing_status="no_lq45_data",
    )

    cs_lq45_swing = safe_comparative_strength(
        dataframe,
        lq45,
        window=60,
        missing_status="no_lq45_data",
    )

    scored_daily = compute_score(
        trend_daily,
        wyckoff_daily,
        vwap_fast,
        cs_ihsg_daily,
        support_resistance_daily,
        wyckoff_weights=wyckoff_calibration.get(
            "daily",
            {},
        ),
    )

    scored = compute_score(
        trend,
        wyckoff,
        vwap_medium,
        cs_ihsg,
        support_resistance,
        wyckoff_weights=wyckoff_calibration.get(
            "weekly",
            {},
        ),
    )

    scored_swing = compute_score(
        trend_swing,
        wyckoff,
        vwap_swing,
        cs_ihsg_swing,
        support_resistance_swing,
        wyckoff_weights=wyckoff_calibration.get(
            "swing",
            {},
        ),
    )

    signal_daily = classify_signal(
        scored_daily
    )
    signal = classify_signal(scored)
    signal_swing = classify_signal(
        scored_swing
    )

    save_signal(
        ticker,
        date_string,
        "trend",
        trend,
    )

    if (
        wyckoff.get("bias")
        and wyckoff.get("bias") != "unclear"
    ):
        events = ", ".join(
            event.get("type", "")
            for event in wyckoff.get(
                "events",
                [],
            )
        )

        save_signal(
            ticker,
            date_string,
            "wyckoff",
            wyckoff["bias"],
            note=(
                f"phase={wyckoff.get('phase')}, "
                f"events={events}"
            ),
        )

    save_signal(
        ticker,
        date_string,
        "composite_daily",
        signal_daily,
        note=f"score={scored_daily['score']}",
        score=scored_daily["score"],
        breakdown=scored_daily["breakdown"],
    )

    save_signal(
        ticker,
        date_string,
        "composite",
        signal,
        note=f"score={scored['score']}",
        score=scored["score"],
        breakdown=scored["breakdown"],
    )

    save_signal(
        ticker,
        date_string,
        "vwap_multi",
        vwap_analysis.get("signal", "WAIT"),
        note=json.dumps(
            {
                "regime": vwap_analysis.get("regime"),
                "reasons": vwap_analysis.get("reasons", []),
                "execution": vwap_analysis.get("execution"),
                "protective_stop": vwap_analysis.get("protective_stop"),
            },
            ensure_ascii=False,
        ),
    )

    volatility = volatility_results.get(
        ticker,
        {
            "status": "skipped",
            "error": (
                "Data historis tidak cukup "
                "untuk perhitungan GARCH."
            ),
        },
    )

    return {
        "ticker": ticker,
        "last_close": clean_number(
            dataframe["Close"].iloc[-1]
        ),
        "trend_daily": trend_daily,
        "support_daily": (
            support_resistance_daily.get(
                "nearest_support"
            )
        ),
        "resistance_daily": (
            support_resistance_daily.get(
                "nearest_resistance"
            )
        ),
        "wyckoff_daily": wyckoff_daily,
        "comparative_strength_daily": (
            cs_ihsg_daily
        ),
        "comparative_strength_lq45_daily": (
            cs_lq45_daily
        ),
        "score_daily": scored_daily["score"],
        "score_breakdown_daily": (
            scored_daily["breakdown"]
        ),
        "signal_daily": signal_daily,
        "trend": trend,
        "support": support_resistance.get(
            "nearest_support"
        ),
        "resistance": support_resistance.get(
            "nearest_resistance"
        ),
        "wyckoff": wyckoff,
        # Key lama tetap menunjuk VWAP cepat untuk kompatibilitas HTML.
        "vwap": vwap_fast,
        "vwap_medium": vwap_medium,
        "vwap_swing": vwap_swing,
        "vwap_analysis": vwap_analysis,
        "vwap_signal": vwap_analysis.get(
            "signal",
            "WAIT",
        ),
        "comparative_strength": cs_ihsg,
        "comparative_strength_lq45": cs_lq45,
        "score": scored["score"],
        "score_breakdown": (
            scored["breakdown"]
        ),
        "volatility": volatility,
        "signal": signal,
        "score_swing": (
            scored_swing["score"]
        ),
        "score_breakdown_swing": (
            scored_swing["breakdown"]
        ),
        "signal_swing": signal_swing,
        "trend_swing": trend_swing,
        "wyckoff_swing": wyckoff_swing,
        "support_swing": (
            support_resistance_swing.get(
                "nearest_support"
            )
        ),
        "resistance_swing": (
            support_resistance_swing.get(
                "nearest_resistance"
            )
        ),
        "comparative_strength_swing": (
            cs_ihsg_swing
        ),
        "comparative_strength_lq45_swing": (
            cs_lq45_swing
        ),
        "price_history": build_price_history(
            dataframe
        ),
    }


def export_dashboard_json(
    results: list[dict],
    coverage: dict,
) -> None:
    """Ekspor hasil screening ke dashboard."""
    sorted_results = sorted(
        results,
        key=lambda item: item["score"],
        reverse=True,
    )

    scores = [
        item["score"]
        for item in results
    ]

    signal_counts = {
        "beli": 0,
        "pantau": 0,
        "jual": 0,
    }
    vwap_signal_counts = {
        "BUY": 0,
        "HOLD": 0,
        "WAIT": 0,
        "REDUCE": 0,
        "EXIT": 0,
        "AVOID": 0,
    }

    for item in results:
        signal = item.get("signal")
        vwap_signal = item.get("vwap_signal")

        if signal in signal_counts:
            signal_counts[signal] += 1

        if vwap_signal in vwap_signal_counts:
            vwap_signal_counts[vwap_signal] += 1

    trend_healthy = sum(
        1
        for item in results
        if item.get("trend")
        in ("uptrend", "sideways")
    )

    accumulation = [
        item
        for item in results
        if item.get(
            "wyckoff",
            {},
        ).get("bias") == "accumulation"
    ]

    strongest_accumulation = (
        max(
            accumulation,
            key=lambda item: item["score"],
        )
        if accumulation
        else None
    )

    payload = {
        "generated_at": datetime.now().isoformat(),
        "universe_size": EXPECTED_TICKER_COUNT,
        "watchlist": sorted_results,
        "summary": {
            "signal_counts": signal_counts,
            "vwap_signal_counts": vwap_signal_counts,
            "trend_healthy": (
                f"{trend_healthy}/"
                f"{len(results)}"
            ),
            "score_min": (
                round(min(scores), 1)
                if scores
                else None
            ),
            "score_max": (
                round(max(scores), 1)
                if scores
                else None
            ),
            "score_avg": (
                round(
                    sum(scores) / len(scores),
                    1,
                )
                if scores
                else None
            ),
            "top_pick": (
                sorted_results[0]
                if sorted_results
                else None
            ),
            "strongest_accumulation": (
                strongest_accumulation
            ),
            "data_coverage": coverage,
        },
    }

    os.makedirs(
        "web",
        exist_ok=True,
    )

    with open(
        "web/dashboard_data.json",
        "w",
        encoding="utf-8",
    ) as output_file:
        json.dump(
            payload,
            output_file,
            indent=2,
            ensure_ascii=False,
            default=str,
        )


def run_screening() -> None:
    """Jalankan screening 500 emiten."""
    init_db()

    tickers = list(DEFAULT_WATCHLIST)

    validate_ticker_universe(tickers)
    add_to_watchlist(tickers)

    print(
        f"Mengambil data untuk "
        f"{len(tickers)} emiten IDX..."
    )

    price_data = fetch_batch(
        tickers,
        period="1y",
    )

    failed_fetch = [
        ticker
        for ticker in tickers
        if ticker not in price_data
    ]

    print(
        f"Coverage fetch: "
        f"{len(price_data)}/{len(tickers)} "
        f"berhasil; "
        f"{len(failed_fetch)} gagal."
    )

    print("Mengambil data IHSG...")
    ihsg = fetch_daily(
        "^JKSE",
        period="1y",
    )

    print("Mengambil data LQ45...")
    lq45 = fetch_daily(
        "^JKLQ45",
        period="1y",
    )

    volatility_items = [
        (ticker, dataframe)
        for ticker, dataframe
        in price_data.items()
        if len(dataframe)
        >= MINIMUM_GARCH_ROWS
    ]

    print(
        f"Menghitung GARCH untuk "
        f"{len(volatility_items)} ticker..."
    )

    volatility_results = (
        forecast_volatility_batch(
            volatility_items
        )
    )

    volatility_success = sum(
        1
        for value
        in volatility_results.values()
        if value.get("status") == "ok"
    )

    volatility_failed = sum(
        1
        for value
        in volatility_results.values()
        if value.get("status") != "ok"
    )

    wyckoff_calibration = (
        load_wyckoff_calibration()
    )
    results = []
    insufficient_data = []
    analysis_failed = []

    for ticker in tickers:
        dataframe = price_data.get(ticker)

        if dataframe is None:
            continue

        if len(dataframe) < MINIMUM_ANALYSIS_ROWS:
            insufficient_data.append(ticker)

            print(
                f"[SKIP] {ticker}: "
                f"hanya {len(dataframe)} baris."
            )

            continue

        try:
            result = process_ticker(
                ticker,
                dataframe,
                ihsg,
                lq45,
                volatility_results,
                wyckoff_calibration,
            )

            results.append(result)

            print(
                f"[OK] {ticker}: "
                f"score={result['score']}, "
                f"signal={result['signal']}, "
                f"vwap={result['vwap_signal']}, "
                f"volatility="
                f"{result['volatility'].get('status')}"
            )

        except Exception as error:
            analysis_failed.append({
                "ticker": ticker,
                "error": (
                    f"{type(error).__name__}: "
                    f"{error}"
                ),
            })

            print(
                f"[ERROR] {ticker}: "
                f"{type(error).__name__}: "
                f"{error}"
            )

    coverage = {
        "requested": len(tickers),
        "fetched": len(price_data),
        "success": len(results),
        "failed_fetch": failed_fetch,
        "insufficient_data": insufficient_data,
        "analysis_failed": analysis_failed,
        "volatility_success": (
            volatility_success
        ),
        "volatility_failed": (
            volatility_failed
        ),
    }

    export_dashboard_json(
        results,
        coverage,
    )

    print(
        f"Screening selesai: "
        f"{len(results)}/{len(tickers)} "
        f"ticker berhasil."
    )

    print(
        f"Gagal fetch: "
        f"{len(failed_fetch)}."
    )

    print(
        f"Data kurang: "
        f"{len(insufficient_data)}."
    )

    print(
        f"Gagal analisis: "
        f"{len(analysis_failed)}."
    )

    print(
        f"Volatilitas berhasil: "
        f"{volatility_success}."
    )

    print(
        "Data disimpan ke "
        "web/dashboard_data.json."
    )


if __name__ == "__main__":
    run_screening()
