"""
Pipeline screening harian — SELURUH 962 TICKER IDX.
Jalankan manual: python main.py
Otomatis via GitHub Actions (cron 15:55 WIB / 5 menit sebelum closing).
"""
import json
from datetime import datetime
import pandas as pd
from data.yfinance_fetcher import fetch_batch, fetch_daily
from data.jarvis_fetcher import get_market_regime
from screener.trend import trend_structure, support_resistance_levels, find_swing_points
from screener.wyckoff import analyze_latest_trading_range, comparative_strength
from screener.vwap import price_vs_vwap, rolling_vwap
from screener.scoring import compute_score, classify_signal
from screener.volatility import forecast_volatility_batch
from storage.db import init_db, upsert_prices, save_signal, get_watchlist, add_to_watchlist
from idx_tickers import IDX_TICKERS_COMPLETE

# Watchlist - SELURUH 962 ticker IDX
DEFAULT_WATCHLIST = IDX_TICKERS_COMPLETE


def run_screening():
    init_db()
    add_to_watchlist(DEFAULT_WATCHLIST)
    tickers = get_watchlist() or DEFAULT_WATCHLIST

    print(f"Mengambil data untuk {len(tickers)} saham (SELURUH IDX)...")
    price_data = fetch_batch(tickers, period="1y")  # 1y biar TR & event lebih kebentuk

    print("Mengambil data IHSG untuk comparative strength...")
    ihsg = fetch_daily("^JKSE", period="1y")

    print("Mengambil data LQ45 untuk comparative strength (pembanding kedua)...")
    lq45 = fetch_daily("^JKLQ45", period="1y")

    print("Mengambil market regime dari Jarvis API (kalau token tersedia)...")
    jarvis_regime = get_market_regime()
    if jarvis_regime:
        print(f"  Jarvis regime: {jarvis_regime}")
    # Catatan: get_stock_signals_batch() (sinyal per-ticker) sengaja DIHAPUS -
    # itu manggil API 962x dengan jeda 1.1 detik/request (patuh rate limit
    # Jarvis), total ~17.6 menit cuma buat data yang sudah tidak dipakai.
    # Kalau nanti mau dipakai lagi, cache hasilnya (jangan fetch ulang tiap
    # run) atau cuma query ticker yang masuk weekly-picks Jarvis sendiri.

    # ============================================================
    # BATCH VOLATILITY (GARCH paralel) — di luar loop, sekali jalan
    # ============================================================
    print(f"\nMenghitung volatility GARCH untuk {len(price_data)} ticker (parallel)...")
    vol_items = [(t, d) for t, d in price_data.items() if len(d) >= 120]
    vol_results = forecast_volatility_batch(vol_items)
    print(f"  Selesai: {len(vol_results)} ticker dihitung")

    results = []

    for ticker, df in price_data.items():
        if len(df) < 60:
            print(f"[SKIP] {ticker}: data terlalu sedikit ({len(df)} baris)")
            continue

        upsert_prices(ticker, df)

        date_str = df.index[-1].strftime("%Y-%m-%d")

        # 1. Trend structure - profil WEEKLY (default, window pendek)
        trend = trend_structure(df, window=5)
        save_signal(ticker, date_str, "trend", trend)

        # 1b. Trend structure - profil SWING (window lebih panjang)
        trend_swing = trend_structure(df, window=20)

        # 2. Support/resistance - WEEKLY & SWING
        sr = support_resistance_levels(df, window=5, lookback=60)
        sr_swing = support_resistance_levels(df, window=20, lookback=180)

        # 3. Wyckoff
        wy = analyze_latest_trading_range(df)
        if wy.get("bias") and wy["bias"] != "unclear":
            events_str = ", ".join(e["type"] for e in wy["events"])
            save_signal(ticker, date_str, "wyckoff", wy["bias"],
                        note=f"phase={wy['phase']}, events={events_str}")

        # 4. VWAP
        vwap = price_vs_vwap(df, window=5)
        vwap_swing = price_vs_vwap(df, window=20)

        # 5. Comparative strength vs IHSG
        cs = comparative_strength(df, ihsg) if ihsg is not None else {"status": "no_ihsg_data"}
        cs_swing = comparative_strength(df, ihsg, window=60) if ihsg is not None else {"status": "no_ihsg_data"}

        # 5b. Comparative strength vs LQ45
        cs_lq45 = comparative_strength(df, lq45) if lq45 is not None else {"status": "no_lq45_data"}
        cs_lq45_swing = comparative_strength(df, lq45, window=60) if lq45 is not None else {"status": "no_lq45_data"}

        # 6. Skor komposit - WEEKLY
        scored = compute_score(trend, wy, vwap, cs, sr)
        vol = vol_results.get(ticker, {"status": "skipped"})  # Ambil dari batch
        signal_label = classify_signal(scored)
        save_signal(ticker, date_str, "composite", signal_label,
                    note=f"score={scored['score']}",
                    score=scored["score"], breakdown=scored["breakdown"])

        # 6b. Skor komposit - SWING
        scored_swing = compute_score(trend_swing, wy, vwap_swing, cs_swing, sr_swing)
        signal_label_swing = classify_signal(scored_swing)

        # Data visual untuk cockpit
        visual_df = find_swing_points(df.tail(180).copy())
        visual_df["vwap_5"] = rolling_vwap(visual_df, window=5)
        price_history = []
        for idx, row in visual_df.iterrows():
            def clean(value):
                return None if pd.isna(value) else round(float(value), 2)

            price_history.append({
                "date": idx.strftime("%Y-%m-%d"),
                "open": clean(row["Open"]),
                "high": clean(row["High"]),
                "low": clean(row["Low"]),
                "close": clean(row["Close"]),
                "volume": int(row["Volume"]) if not pd.isna(row["Volume"]) else 0,
                "vwap": clean(row["vwap_5"]),
                "swing_high": clean(row.get("swing_high")),
                "swing_low": clean(row.get("swing_low")),
            })

        print(f"\n{ticker}: skor={scored['score']} -> {signal_label} (swing: {scored_swing['score']} -> {signal_label_swing})")
        print(f"  Trend           : {trend}")
        print(f"  Support         : {sr['nearest_support']}")
        print(f"  Resistance      : {sr['nearest_resistance']}")
        if wy.get("status") == "no_trading_range_found":
            print(f"  Wyckoff TR      : tidak ditemukan (belum konsolidasi)")
        else:
            print(f"  Wyckoff TR      : {wy['tr_low']} - {wy['tr_high']} ({wy['tr_start']} s/d {wy['tr_end']})")
            print(f"  Wyckoff bias    : {wy['bias']} | fase: {wy['phase']}")
            print(f"  Wyckoff events  : {[e['type'] for e in wy['events']]}")
        print(f"  vs VWAP(5d)     : {vwap.get('position', '-')}")
        print(f"  vs IHSG         : {cs.get('relative_strength_trend', '-')}")
        print(f"  vs LQ45         : {cs_lq45.get('relative_strength_trend', '-')}")

        results.append({
            "ticker": ticker,
            "last_close": round(float(df["Close"].iloc[-1]), 2),
            "trend": trend,
            "support": sr.get("nearest_support"),
            "resistance": sr.get("nearest_resistance"),
            "wyckoff": wy,
            "vwap": vwap,
            "comparative_strength": cs,
            "comparative_strength_lq45": cs_lq45,
            "score": scored["score"],
            "score_breakdown": scored["breakdown"],
            "volatility": vol,
            "signal": signal_label,
            "score_swing": scored_swing["score"],
            "score_breakdown_swing": scored_swing["breakdown"],
            "signal_swing": signal_label_swing,
            "trend_swing": trend_swing,
            "support_swing": sr_swing.get("nearest_support"),
            "resistance_swing": sr_swing.get("nearest_resistance"),
            "vwap_swing": vwap_swing,
            "comparative_strength_swing": cs_swing,
            "comparative_strength_lq45_swing": cs_lq45_swing,
            "price_history": price_history,
        })

    export_dashboard_json(results, jarvis_regime)
    print(f"\nSelesai. {len(results)} ticker diproses.")
    print("Data tersimpan di storage/screener.db dan web/dashboard_data.json")


def export_dashboard_json(results: list[dict], jarvis_regime: dict | None = None):
    """Tulis ringkasan untuk dikonsumsi dashboard (web/index.html) via fetch()."""
    results_sorted = sorted(results, key=lambda r: r["score"], reverse=True)
    scores = [r["score"] for r in results]

    signal_counts = {"beli": 0, "pantau": 0, "jual": 0}
    for r in results:
        signal_counts[r["signal"]] += 1

    trend_healthy = sum(1 for r in results if r["trend"] in ("uptrend", "sideways"))

    top_pick = results_sorted[0] if results_sorted else None
    strongest_accumulation = max(
        (r for r in results if r["wyckoff"].get("bias") == "accumulation"),
        key=lambda r: r["score"], default=None
    )

    payload = {
        "generated_at": datetime.now().isoformat(),
        "watchlist": results_sorted,
        "summary": {
            "signal_counts": signal_counts,
            "trend_healthy": f"{trend_healthy}/{len(results)}",
            "score_min": round(min(scores), 1) if scores else None,
            "score_max": round(max(scores), 1) if scores else None,
            "score_avg": round(sum(scores) / len(scores), 1) if scores else None,
            "top_pick": top_pick,
            "strongest_accumulation": strongest_accumulation,
            "jarvis_regime": jarvis_regime,
        },
    }

    import os
    os.makedirs("web", exist_ok=True)
    with open("web/dashboard_data.json", "w") as f:
        json.dump(payload, f, indent=2, default=str)


if __name__ == "__main__":
    run_screening()
