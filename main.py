"""
Pipeline screening harian untuk 500 emiten IDX.

Jalankan secara manual:
    python main.py

Pipeline otomatis dijalankan melalui GitHub Actions setiap
Senin sampai Jumat setelah perdagangan BEI berakhir.
"""

import json
import os
from datetime import datetime

import pandas as pd

from data.yfinance_fetcher import fetch_batch, fetch_daily
from idx_tickers_500 import IDX_TICKERS_500
from screener.scoring import compute_score, classify_signal
from screener.trend import (
    find_swing_points,
    support_resistance_levels,
    trend_structure,
)
from screener.volatility import forecast_volatility_batch
from screener.vwap import price_vs_vwap, rolling_vwap
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
DEFAULT_WATCHLIST = IDX_TICKERS_500


def clean_number(value):
    """
    Ubah nilai numerik menjadi float dua desimal.

    Nilai kosong atau NaN diubah menjadi None agar aman diekspor
    ke JSON.
    """
    if value is None or pd.isna(value):
        return None

    return round(float(value), 2)


def validate_ticker_universe(tickers: list[str]) -> None:
    """
    Pastikan universe berisi tepat 500 ticker unik.
    """
    if len(tickers) != EXPECTED_TICKER_COUNT:
        raise RuntimeError(
            f"Universe harus berisi tepat "
            f"{EXPECTED_TICKER_COUNT} ticker, "
            f"tetapi ditemukan {len(tickers)}."
        )

    if len(set(tickers)) != len(tickers):
        raise RuntimeError(
            "Universe ticker mengandung ticker duplikat."
        )


def build_price_history(
    dataframe: pd.DataFrame,
) -> list[dict]:
    """
    Buat data visual harga untuk cockpit dashboard.
    """
    visual_df = find_swing_points(
        dataframe.tail(180).copy()
    )

    visual_df["vwap_5"] = rolling_vwap(
        visual_df,
        window=5,
    )

    price_history = []

    for index, row in visual_df.iterrows():
        volume = row.get("Volume")

        price_history.append({
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
            "vwap": clean_number(row.get("vwap_5")),
            "swing_high": clean_number(
                row.get("swing_high")
            ),
            "swing_low": clean_number(
                row.get("swing_low")
            ),
        })

    return price_history


def run_screening():
    """
    Jalankan screening untuk tepat 500 emiten IDX.
    """
    init_db()

    # Jangan membaca seluruh watchlist dari database lama.
    # Database mungkin masih menyimpan ticker dari proses 849/962 emiten.
    tickers = list(DEFAULT_WATCHLIST)

    validate_ticker_universe(tickers)

    # Tetap simpan ticker terpilih ke database untuk kompatibilitas.
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
        f"{len(price_data)}/{len(tickers)} berhasil, "
        f"{len(failed_fetch)} gagal atau tidak tersedia."
    )

    print(
        "Mengambil data IHSG untuk "
        "comparative strength..."
    )

    ihsg = fetch_daily(
        "^JKSE",
        period="1y",
    )

    print(
        "Mengambil data LQ45 untuk "
        "comparative strength..."
    )

    lq45 = fetch_daily(
        "^JKLQ45",
        period="1y",
    )

    print(
        f"Menghitung volatilitas GARCH untuk "
        f"{len(price_data)} ticker..."
    )

    volatility_items = [
        (ticker, dataframe)
        for ticker, dataframe in price_data.items()
        if len(dataframe) >= 120
    ]

    volatility_results = forecast_volatility_batch(
        volatility_items
    )

    volatility_success = sum(
        1
        for result in volatility_results.values()
        if result.get("status") == "ok"
    )

    volatility_failed = sum(
        1
        for result in volatility_results.values()
        if result.get("status") != "ok"
    )

    print(
        f"Volatilitas selesai: "
        f"{volatility_success} berhasil, "
        f"{volatility_failed} gagal."
    )

    results = []
    insufficient_data = []

    for ticker, dataframe in price_data.items():
        try:
            if len(dataframe) < 60:
                print(
                    f"[SKIP] {ticker}: "
                    f"data hanya {len(dataframe)} baris."
                )

                insufficient_data.append(ticker)
                continue

            upsert_prices(
                ticker,
                dataframe,
            )

            date_string = dataframe.index[
                -1
            ].strftime("%Y-%m-%d")

            # Analisis profil weekly.
            trend = trend_structure(
                dataframe,
                window=5,
            )

            support_resistance = (
                support_resistance_levels(
                    dataframe,
                    window=5,
                    lookback=60,
                )
            )

            vwap = price_vs_vwap(
                dataframe,
                window=5,
            )

            # Analisis profil swing.
            trend_swing = trend_structure(
                dataframe,
                window=20,
            )

            support_resistance_swing = (
                support_resistance_levels(
                    dataframe,
                    window=20,
                    lookback=180,
                )
            )

            vwap_swing = price_vs_vwap(
                dataframe,
                window=20,
            )

            save_signal(
                ticker,
                date_string,
                "trend",
                trend,
            )

            # Analisis Wyckoff.
            wyckoff = analyze_latest_trading_range(
                dataframe
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

            # Comparative strength terhadap IHSG.
            if ihsg is not None:
                comparative_strength_ihsg = (
                    comparative_strength(
                        dataframe,
                        ihsg,
                    )
                )

                comparative_strength_ihsg_swing = (
                    comparative_strength(
                        dataframe,
                        ihsg,
                        window=60,
                    )
                )
            else:
                comparative_strength_ihsg = {
                    "status": "no_ihsg_data"
                }

                comparative_strength_ihsg_swing = {
                    "status": "no_ihsg_data"
                }

            # Comparative strength terhadap LQ45.
            if lq45 is not None:
                comparative_strength_lq45 = (
                    comparative_strength(
                        dataframe,
                        lq45,
                    )
                )

                comparative_strength_lq45_swing = (
                    comparative_strength(
                        dataframe,
                        lq45,
                        window=60,
                    )
                )
            else:
                comparative_strength_lq45 = {
                    "status": "no_lq45_data"
                }

                comparative_strength_lq45_swing = {
                    "status": "no_lq45_data"
                }

            # Skor profil weekly.
            scored = compute_score(
                trend,
                wyckoff,
                vwap,
                comparative_strength_ihsg,
                support_resistance,
            )

            signal_label = classify_signal(scored)

            save_signal(
                ticker,
                date_string,
                "composite",
                signal_label,
                note=f"score={scored['score']}",
                score=scored["score"],
                breakdown=scored["breakdown"],
            )

            # Skor profil swing.
            scored_swing = compute_score(
                trend_swing,
                wyckoff,
                vwap_swing,
                comparative_strength_ihsg_swing,
                support_resistance_swing,
            )

            signal_label_swing = classify_signal(
                scored_swing
            )

            volatility = volatility_results.get(
                ticker,
                {
                    "status": "skipped",
                    "error": (
                        "Data historis tidak cukup untuk "
                        "perhitungan GARCH."
                    ),
                },
            )

            price_history = build_price_history(
                dataframe
            )

            last_close = clean_number(
                dataframe["Close"].iloc[-1]
            )

            result = {
                "ticker": ticker,
                "last_close": last_close,
                "trend": trend,
                "support": (
                    support_resistance.get(
                        "nearest_support"
                    )
                ),
                "resistance": (
                    support_resistance.get(
                        "nearest_resistance"
                    )
                ),
                "wyckoff": wyckoff,
                "vwap": vwap,
                "comparative_strength": (
                    comparative_strength_ihsg
                ),
                "comparative_strength_lq45": (
                    comparative_strength_lq45
                ),
                "score": scored["score"],
                "score_breakdown": (
                    scored["breakdown"]
                ),
                "volatility": volatility,
                "signal": signal_label,
                "score_swing": (
                    scored_swing["score"]
                ),
                "score_breakdown_swing": (
                    scored_swing["breakdown"]
                ),
                "signal_swing": (
                    signal_label_swing
                ),
                "trend_swing": trend_swing,
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
                "vwap_swing": vwap_swing,
                "comparative_strength_swing": (
                    comparative_strength_ihsg_swing
                ),
                "comparative_strength_lq45_swing": (
                    comparative_strength_lq45_swing
                ),
                "price_history": price_history,
            }

            results.append(result)

            print(
                f"{ticker}: "
                f"weekly={scored['score']} "
                f"({signal_label}), "
                f"swing={scored_swing['score']} "
                f"({signal_label_swing}), "
                f"volatilitas="
                f"{volatility.get('status')}"
            )

        except Exception as error:
            print(
                f"[ERROR] {ticker}: "
                f"{type(error).__name__}: {error}"
            )

            insufficient_data.append(ticker)

    coverage = {
        "requested": len(tickers),
        "fetched": len(price_data),
        "success": len(results),
        "failed_fetch": failed_fetch,
        "insufficient_or_failed": (
            insufficient_data
        ),
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
        f"Screening selesai. "
        f"{len(results)}/{len(tickers)} "
        f"ticker berhasil diproses."
    )

    print(
        "Data tersimpan di "
        "storage/screener.db dan "
        "web/dashboard_data.json."
    )


def export_dashboard_json(
    results: list[dict],
    coverage: dict | None = None,
):
    """
    Ekspor hasil screening ke dashboard.
    """
    results_sorted = sorted(
        results,
        key=lambda result: result["score"],
        reverse=True,
    )

    scores = [
        result["score"]
        for result in results
    ]

    signal_counts = {
        "beli": 0,
        "pantau": 0,
        "jual": 0,
    }

    for result in results:
        signal = result.get("signal")

        if signal in signal_counts:
            signal_counts[signal] += 1

    trend_healthy = sum(
        1
        for result in results
        if result.get("trend")
        in ("uptrend", "sideways")
    )

    top_pick = (
        results_sorted[0]
        if results_sorted
        else None
    )

    accumulation_candidates = [
        result
        for result in results
        if result.get(
            "wyckoff",
            {},
        ).get("bias") == "accumulation"
    ]

    strongest_accumulation = (
        max(
            accumulation_candidates,
            key=lambda result: result["score"],
        )
        if accumulation_candidates
        else None
    )

    payload = {
        "generated_at": datetime.now().isoformat(),
        "universe_size": EXPECTED_TICKER_COUNT,
        "watchlist": results_sorted,
        "summary": {
            "signal_counts": signal_counts,
            "trend_healthy": (
                f"{trend_healthy}/{len(results)}"
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
            "top_pick": top_pick,
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


if __name__ == "__main__":
    run_screening()
