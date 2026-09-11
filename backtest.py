"""
Backtest sederhana untuk sistem screening di main.py.

TUJUAN (dijelaskan tanpa istilah IT):
Script ini "memutar ulang" data harga historis, hari demi hari, dan di
setiap titik waktu berpura-pura seolah-olah hari itu adalah HARI INI --
lalu menjalankan persis formula yang sama dengan main.py (trend, Wyckoff,
VWAP, comparative strength, skor komposit) memakai data yang tersedia
SAMPAI hari itu saja (tidak mengintip masa depan).

Setelah sinyal "beli/pantau/jual" tercatat, script menunggu 5, 10, dan 20
hari bursa ke depan lalu mengecek: harga saham itu naik atau turun, dan
berapa persen. Hasilnya dikumpulkan jadi tabel ringkas: kalau sistem bilang
"beli", secara historis rata-rata hasilnya seperti apa?

INI BUKAN JAMINAN HASIL MASA DEPAN. Ini cuma alat ukur "seberapa masuk akal
skor yang dihasilkan sistem ini, berdasarkan apa yang sudah terjadi".

CARA PAKAI:
    python backtest.py

Butuh koneksi internet (sama seperti main.py, karena ambil data historis
lebih panjang dari yfinance). Hasilnya disimpan ke backtest_results.csv
dan ringkasannya dicetak ke layar dalam bahasa biasa.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))

import pandas as pd

from data.yfinance_fetcher import fetch_batch, fetch_daily
from screener.trend import trend_structure, support_resistance_levels
from screener.wyckoff import analyze_latest_trading_range, comparative_strength
from screener.vwap import price_vs_vwap
from screener.scoring import compute_score, classify_signal
from main import DEFAULT_WATCHLIST

# ---------------------------------------------------------------------------
# PENGATURAN
# ---------------------------------------------------------------------------

# Ambil histori sepanjang mungkin biar sampel backtest lebih banyak.
# yfinance untuk saham IDX biasanya sanggup kasih beberapa tahun ke belakang.
PERIOD = "3y"

# Berapa hari bursa minimum dibutuhkan sebelum sinyal pertama dihitung.
# Wyckoff & trend butuh histori cukup panjang biar tidak "insufficient_data".
WARMUP_BARS = 100

# Sinyal dicek hasilnya berapa hari bursa ke depan.
HORIZONS = [5, 10, 20]

# Ambil 1 sampel tiap N hari bursa (bukan tiap hari), supaya sampel tidak
# tumpang-tindih berlebihan (sinyal hari Senin dan Selasa itu 95% mirip,
# kalau dihitung semua, hasil backtest jadi bias seolah sampelnya banyak
# padahal sebenarnya cuma mengulang info yang sama).
STRIDE = 5


def run_backtest():
    print(f"Mengambil data historis {PERIOD} untuk {len(DEFAULT_WATCHLIST)} saham...")
    price_data = fetch_batch(DEFAULT_WATCHLIST, period=PERIOD)

    print("Mengambil data IHSG untuk comparative strength...")
    ihsg = fetch_daily("^JKSE", period=PERIOD)

    rows = []
    max_horizon = max(HORIZONS)

    for ticker, df in price_data.items():
        n = len(df)
        min_needed = WARMUP_BARS + max_horizon + 5
        if n < min_needed:
            print(f"[SKIP] {ticker}: cuma {n} hari data, butuh minimal {min_needed}")
            continue

        print(f"Memproses {ticker} ({n} hari data)...")

        for t in range(WARMUP_BARS, n - max_horizon, STRIDE):
            # "hist" = semua data SAMPAI hari ke-t saja. Ini kunci supaya
            # backtest tidak curang mengintip masa depan.
            hist = df.iloc[: t + 1]

            trend = trend_structure(hist)
            sr = support_resistance_levels(hist)
            wy = analyze_latest_trading_range(hist)
            vwap = price_vs_vwap(hist, window=5)

            if ihsg is not None:
                ihsg_hist = ihsg.iloc[: t + 1]
                cs = comparative_strength(hist, ihsg_hist)
            else:
                cs = {"status": "no_ihsg_data"}

            scored = compute_score(trend, wy, vwap, cs, sr)
            signal = classify_signal(scored)

            entry_price = float(df["Close"].iloc[t])
            row = {
                "ticker": ticker,
                "date": df.index[t].strftime("%Y-%m-%d"),
                "score": scored["score"],
                "signal": signal,
                "entry_price": round(entry_price, 2),
            }
            for h in HORIZONS:
                future_price = float(df["Close"].iloc[t + h])
                row[f"return_{h}d_pct"] = round(
                    (future_price - entry_price) / entry_price * 100, 2
                )
            rows.append(row)

    if not rows:
        print("Tidak ada sampel yang terkumpul. Cek koneksi data / WARMUP_BARS.")
        return

    result_df = pd.DataFrame(rows)
    result_df.to_csv("backtest_results.csv", index=False)
    print(f"\n{len(result_df)} sampel sinyal tersimpan ke backtest_results.csv")

    print_report(result_df)
    export_dashboard_json(result_df)


def print_report(df: pd.DataFrame):
    print("\n" + "=" * 70)
    print("RINGKASAN BACKTEST (bahasa biasa)")
    print("=" * 70)

    print(
        "\nCatatan penting: sampel di bawah ini saling berdekatan waktunya "
        "(diambil tiap beberapa hari dari watchlist yang sama), jadi masih "
        "mencerminkan kondisi pasar dalam periode yang terbatas. Anggap "
        "sebagai indikasi awal, bukan kesimpulan final -- makin lama sistem "
        "jalan dan makin banyak kondisi pasar yang terekam, makin bisa "
        "dipercaya angkanya."
    )

    print(f"\nTotal sampel sinyal: {len(df)}")

    print("\n--- Performa per kategori sinyal ---")
    for h in HORIZONS:
        col = f"return_{h}d_pct"
        summary = (
            df.groupby("signal")[col]
            .agg(
                jumlah_sampel="count",
                rata_rata_return_pct="mean",
                persen_untung=lambda s: (s > 0).mean() * 100,
                return_terburuk="min",
                return_terbaik="max",
            )
            .round(2)
        )
        print(f"\nHasil {h} hari bursa setelah sinyal muncul:")
        print(summary.to_string())

    print("\n--- Performa per rentang skor (dibagi 4 kelompok) ---")
    df["kelompok_skor"] = pd.qcut(df["score"], q=4, duplicates="drop")
    for h in HORIZONS:
        col = f"return_{h}d_pct"
        summary = (
            df.groupby("kelompok_skor", observed=True)[col]
            .agg(jumlah_sampel="count", rata_rata_return_pct="mean")
            .round(2)
        )
        print(f"\nHasil {h} hari bursa, dikelompokkan dari skor terendah ke tertinggi:")
        print(summary.to_string())

    print(
        "\nCara baca tabel kelompok skor: kalau skor makin tinggi rata-rata "
        "return-nya juga makin tinggi (naik tangga rapi), itu tanda formula "
        "scoring-nya cukup masuk akal. Kalau naik-turun tidak beraturan, "
        "berarti bobot di scoring.py perlu ditinjau ulang."
    )


def export_dashboard_json(df: pd.DataFrame):
    """
    Tulis ringkasan backtest ke web/backtest_data.json supaya bisa dibaca
    halaman Laporan di cockpit (web/index.html) via fetch(), sama caranya
    seperti main.py menulis web/dashboard_data.json untuk sinyal harian.
    """
    df = df.copy()
    df["kelompok_skor"] = pd.qcut(df["score"], q=4, duplicates="drop")

    by_signal = {}
    by_score_quartile = {}

    for h in HORIZONS:
        col = f"return_{h}d_pct"

        sig_summary = (
            df.groupby("signal")[col]
            .agg(
                jumlah_sampel="count",
                rata_rata_return_pct="mean",
                persen_untung=lambda s: round((s > 0).mean() * 100, 1),
                return_terburuk="min",
                return_terbaik="max",
            )
            .round(2)
        )
        by_signal[str(h)] = sig_summary.reset_index().to_dict(orient="records")

        q_summary = (
            df.groupby("kelompok_skor", observed=True)[col]
            .agg(jumlah_sampel="count", rata_rata_return_pct="mean")
            .round(2)
        )
        by_score_quartile[str(h)] = [
            {"rentang_skor": str(idx), **row}
            for idx, row in q_summary.reset_index().set_index("kelompok_skor").iterrows()
        ]

    payload = {
        "generated_at": datetime.now().isoformat(),
        "period": PERIOD,
        "warmup_bars": WARMUP_BARS,
        "stride": STRIDE,
        "horizons_hari_bursa": HORIZONS,
        "watchlist": DEFAULT_WATCHLIST,
        "total_sampel": len(df),
        "by_signal": by_signal,
        "by_score_quartile": by_score_quartile,
        "catatan": (
            "Sampel diambil dari histori terbatas dan watchlist blue chip saja. "
            "Anggap sebagai indikasi awal, bukan kesimpulan final."
        ),
    }

    out_path = Path(__file__).resolve().parent / "web" / "backtest_data.json"
    out_path.parent.mkdir(exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2, default=str)

    print(f"Ringkasan backtest tersimpan ke {out_path}")


if __name__ == "__main__":
    run_backtest()
