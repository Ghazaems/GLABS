"""
Pipeline screening harian.
Jalankan manual: python main.py
Nanti dijadwalkan via GitHub Actions (cron gratis).
"""
import json
from datetime import datetime
import pandas as pd
from data.yfinance_fetcher import fetch_batch, fetch_daily
from screener.trend import trend_structure, support_resistance_levels, find_swing_points
from screener.wyckoff import analyze_latest_trading_range, comparative_strength
from screener.vwap import price_vs_vwap, rolling_vwap
from screener.scoring import compute_score, classify_signal
from storage.db import init_db, upsert_prices, save_signal, get_watchlist, add_to_watchlist

# Watchlist awal - blue chip LQ45 untuk uji coba
DEFAULT_WATCHLIST = [
    "AADI", "ADMR", "ADRO", "AMRT", "ANTM", "ASII", "BBCA", "BBNI", "BBRI",
    "BMRI", "BRPT", "BUMI", "CPIN", "DEWA", "EMTK", "GOTO", "ICBP", "INCO",
    "INDF", "INKP", "JPFA", "KLBF", "MBMA", "MDKA", "MEDC", "PGAS", "PGEO",
    "TLKM", "UNTR", "UNVR",
]


def run_screening():
    init_db()
    add_to_watchlist(DEFAULT_WATCHLIST)
    tickers = get_watchlist() or DEFAULT_WATCHLIST

    print(f"Mengambil data untuk {len(tickers)} saham...")
    price_data = fetch_batch(tickers, period="1y")  # 1y biar TR & event lebih kebentuk

    print("Mengambil data IHSG untuk comparative strength...")
    ihsg = fetch_daily("^JKSE", period="1y")

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

        # 1b. Trend structure - profil SWING (window lebih panjang, ~1 bulan
        # per swing point, cocok gaya 3-4 bulanan sesuai temuan backtest)
        trend_swing = trend_structure(df, window=20)

        # 2. Support/resistance - WEEKLY (default) & SWING (lookback lebih panjang)
        sr = support_resistance_levels(df, window=5, lookback=60)
        sr_swing = support_resistance_levels(df, window=20, lookback=180)

        # 3. Wyckoff - trading range + event detection (dipakai bersama, belum
        # dibedakan per gaya - deteksi TR-nya tidak diparameterisasi window)
        wy = analyze_latest_trading_range(df)
        if wy.get("bias") and wy["bias"] != "unclear":
            events_str = ", ".join(e["type"] for e in wy["events"])
            save_signal(ticker, date_str, "wyckoff", wy["bias"],
                        note=f"phase={wy['phase']}, events={events_str}")

        # 4. VWAP - weekly (5 hari) & swing (~1 bulan/20 hari)
        vwap = price_vs_vwap(df, window=5)
        vwap_swing = price_vs_vwap(df, window=20)

        # 5. Comparative strength vs IHSG - weekly (20 hari) & swing (60 hari)
        cs = comparative_strength(df, ihsg) if ihsg is not None else {"status": "no_ihsg_data"}
        cs_swing = comparative_strength(df, ihsg, window=60) if ihsg is not None else {"status": "no_ihsg_data"}

        # 6. Skor komposit - WEEKLY (dipakai Top pick, Trend structure, dst -
        # semua card selain Sinyal breakdown & Watchlist tetap pakai ini)
        scored = compute_score(trend, wy, vwap, cs, sr)
        signal_label = classify_signal(scored)
        save_signal(ticker, date_str, "composite", signal_label, note=f"score={scored['score']}")

        # 6b. Skor komposit - SWING (khusus buat toggle di Sinyal breakdown & Watchlist)
        scored_swing = compute_score(trend_swing, wy, vwap_swing, cs_swing, sr_swing)
        signal_label_swing = classify_signal(scored_swing)

        # Data visual untuk cockpit. Batasi 180 bar agar file dashboard tetap ringan.
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

        results.append({
            "ticker": ticker,
            "last_close": round(float(df["Close"].iloc[-1]), 2),
            "trend": trend,
            "support": sr.get("nearest_support"),
            "resistance": sr.get("nearest_resistance"),
            "wyckoff": wy,
            "vwap": vwap,
            "comparative_strength": cs,
            "score": scored["score"],
            "score_breakdown": scored["breakdown"],
            "signal": signal_label,
            "score_swing": scored_swing["score"],
            "signal_swing": signal_label_swing,
            "price_history": price_history,
        })

    export_dashboard_json(results)
    print("\nSelesai. Data tersimpan di storage/screener.db dan web/dashboard_data.json")


def export_dashboard_json(results: list[dict]):
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
        },
    }

    import os
    os.makedirs("web", exist_ok=True)
    with open("web/dashboard_data.json", "w") as f:
        json.dump(payload, f, indent=2, default=str)


if __name__ == "__main__":
    run_screening()
