"""
Pipeline screening harian.
UPDATE: Sekarang support SEMUA 900+ saham IDX dengan batch download cepat!
"""
import json
from datetime import datetime
import pandas as pd
from data.yfinance_fetcher import fetch_batch_fast, fetch_daily
from data.jarvis_fetcher import get_market_regime, get_stock_signals_batch
from screener.trend import trend_structure, support_resistance_levels, find_swing_points
from screener.wyckoff import analyze_latest_trading_range, comparative_strength
from screener.vwap import price_vs_vwap, rolling_vwap
from screener.scoring import compute_score, classify_signal
from screener.volatility import forecast_volatility
from storage.db import init_db, upsert_prices, save_signal, get_watchlist, add_to_watchlist

# MODE: "LQ45" (45 saham) atau "ALL_IDX" (900+ saham)
MODE = "ALL_IDX"

LQ45_WATCHLIST = [
    "AADI", "ADMR", "ADRO", "AKRA", "AMMN", "AMRT", "ANTM", "ASII", "BBCA",
    "BBNI", "BBRI", "BBTN", "BMRI", "BRPT", "BUMI", "CPIN", "CUAN", "DEWA",
    "EMTK", "ESSA", "EXCL", "GOTO", "HRTA", "ICBP", "INCO", "INDF", "INDY",
    "INKP", "ISAT", "ITMG", "JPFA", "KLBF", "MAPI", "MBMA", "MDKA", "MEDC",
    "NCKL", "PGAS", "PGEO", "PTBA", "SCMA", "TLKM", "UNTR", "UNVR", "WIFI",
]

try:
    from idx_tickers import IDX_TICKERS_COMPLETE
    ALL_IDX_WATCHLIST = IDX_TICKERS_COMPLETE
except ImportError:
    print("⚠️  idx_tickers.py tidak ditemukan, pakai LQ45")
    ALL_IDX_WATCHLIST = LQ45_WATCHLIST

if MODE == "LQ45":
    DEFAULT_WATCHLIST = LQ45_WATCHLIST
else:
    DEFAULT_WATCHLIST = ALL_IDX_WATCHLIST
    print(f"\n📊 Mode: ALL IDX ({len(DEFAULT_WATCHLIST)} saham)")

def run_screening():
    init_db()
    add_to_watchlist(DEFAULT_WATCHLIST)
    tickers = get_watchlist() or DEFAULT_WATCHLIST

    print(f"\n{'='*60}")
    print(f"  ⚡ GLABS — Fast Batch Download")
    print(f"{'='*60}")
    print(f"\n📊 Mengambil data untuk {len(tickers)} saham...")
    
    price_data = fetch_batch_fast(tickers, period="1y", batch_size=50)

    print("\nMengambil data IHSG...")
    ihsg = fetch_daily("^JKSE", period="1y")
    lq45 = fetch_daily("^JKLQ45", period="1y")

    jarvis_regime = get_market_regime()
    jarvis_signals = get_stock_signals_batch(tickers)

    results = []

    for ticker, df in price_data.items():
        if len(df) < 60:
            continue

        upsert_prices(ticker, df)
        date_str = df.index[-1].strftime("%Y-%m-%d")

        trend = trend_structure(df, window=5)
        save_signal(ticker, date_str, "trend", trend)
        trend_swing = trend_structure(df, window=20)

        sr = support_resistance_levels(df, window=5, lookback=60)
        sr_swing = support_resistance_levels(df, window=20, lookback=180)

        wy = analyze_latest_trading_range(df)
        if wy.get("bias") and wy["bias"] != "unclear":
            events_str = ", ".join(e["type"] for e in wy["events"])
            save_signal(ticker, date_str, "wyckoff", wy["bias"],
                        note=f"phase={wy['phase']}, events={events_str}")

        vwap = price_vs_vwap(df, window=5)
        vwap_swing = price_vs_vwap(df, window=20)

        cs = comparative_strength(df, ihsg) if ihsg is not None else {"status": "no_ihsg_data"}
        cs_swing = comparative_strength(df, ihsg, window=60) if ihsg is not None else {"status": "no_ihsg_data"}
        cs_lq45 = comparative_strength(df, lq45) if lq45 is not None else {"status": "no_lq45_data"}
        cs_lq45_swing = comparative_strength(df, lq45, window=60) if lq45 is not None else {"status": "no_lq45_data"}

        scored = compute_score(trend, wy, vwap, cs, sr)
        vol = forecast_volatility(df)
        signal_label = classify_signal(scored)
        save_signal(ticker, date_str, "composite", signal_label,
                    note=f"score={scored['score']}",
                    score=scored["score"], breakdown=scored["breakdown"])

        scored_swing = compute_score(trend_swing, wy, vwap_swing, cs_swing, sr_swing)
        signal_label_swing = classify_signal(scored_swing)

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

        if len(tickers) <= 100:
            print(f"\n{ticker}: skor={scored['score']} -> {signal_label}")
        else:
            if len(results) % 50 == 0:
                print(f"  ... {len(results)}/{len(tickers)} tickers")

        jarvis_signal = jarvis_signals.get(ticker)

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
            "jarvis_signal": jarvis_signal,
        })

    export_dashboard_json(results, jarvis_regime)
    
    print(f"\n{'='*60}")
    print(f"✅ Selesai! {len(results)} saham")
    print(f"{'='*60}\n")

def export_dashboard_json(results: list[dict], jarvis_regime: dict | None = None):
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
