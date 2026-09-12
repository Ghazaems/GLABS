"""
Forward-test: mengukur hasil NYATA (bukan simulasi) dari sinyal komposit
(beli/pantau/jual) yang pernah muncul, dibandingkan harga N hari bursa
kemudian - menggunakan data yang benar-benar terkumpul harian dari cron job.

BEDA dengan backtest historis:
- Backtest: bisa langsung dihitung hari ini pakai data 3 tahun lalu (instan)
- Forward-test: HARUS menunggu waktu nyata berjalan - sinyal yang muncul
  kemarin baru bisa diukur horizon 5 harinya, 5 hari bursa dari sekarang

Jalankan: python forward_test.py
Butuh minimal beberapa minggu data terkumpul dulu supaya horizon 20 hari
punya cukup sampel (kalau belum, laporan tetap jalan tapi sampelnya sedikit/kosong).
"""
import json
from datetime import datetime
from storage.db import get_conn

HORIZONS = [5, 10, 20]  # hari bursa setelah sinyal muncul


def get_composite_signals():
    """Ambil semua sinyal komposit yang pernah tersimpan, urut per ticker+tanggal."""
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT ticker, date, direction AS signal, note
            FROM signals
            WHERE signal_type = 'composite'
            ORDER BY ticker, date
        """).fetchall()
    return [dict(r) for r in rows]


def get_price_series(ticker: str) -> list[dict]:
    """Ambil semua harga historis ticker tsb, urut tanggal naik."""
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT date, close FROM prices WHERE ticker = ? ORDER BY date ASC
        """, (ticker,)).fetchall()
    return [dict(r) for r in rows]


def compute_forward_returns():
    signals = get_composite_signals()
    price_cache = {}  # ticker -> list of {date, close}

    results = []

    for sig in signals:
        ticker = sig["ticker"]
        if ticker not in price_cache:
            price_cache[ticker] = get_price_series(ticker)
        prices = price_cache[ticker]

        # cari index tanggal sinyal muncul di deretan harga
        dates = [p["date"] for p in prices]
        try:
            idx = dates.index(sig["date"])
        except ValueError:
            continue  # tanggal sinyal belum punya harga tersimpan, skip

        entry_price = prices[idx]["close"]
        row = {
            "ticker": ticker,
            "date": sig["date"],
            "signal": sig["signal"],
            "entry_price": entry_price,
            "returns": {},
        }

        for h in HORIZONS:
            target_idx = idx + h
            if target_idx < len(prices):
                future_price = prices[target_idx]["close"]
                pct = round((future_price - entry_price) / entry_price * 100, 2)
                row["returns"][str(h)] = pct
            else:
                row["returns"][str(h)] = None  # belum cukup waktu berjalan

        results.append(row)

    return results


def aggregate_by_signal(results: list[dict]) -> dict:
    """Ringkas performa per horizon per label sinyal (beli/pantau/jual)."""
    agg = {str(h): {} for h in HORIZONS}

    for h in HORIZONS:
        h_key = str(h)
        by_label = {}
        for r in results:
            pct = r["returns"].get(h_key)
            if pct is None:
                continue
            by_label.setdefault(r["signal"], []).append(pct)

        rows = []
        for label, pcts in by_label.items():
            untung = sum(1 for p in pcts if p > 0)
            rows.append({
                "signal": label,
                "jumlah_sampel": len(pcts),
                "rata_rata_return_pct": round(sum(pcts) / len(pcts), 2),
                "persen_untung": round(untung / len(pcts) * 100, 1),
            })
        agg[h_key] = rows

    return agg


def export_forward_test_json(results: list[dict]):
    matured = [r for r in results if any(v is not None for v in r["returns"].values())]

    payload = {
        "generated_at": datetime.now().isoformat(),
        "jenis": "forward_test",
        "catatan": (
            "Ini hasil NYATA (bukan simulasi historis) dari sinyal yang pernah "
            "muncul, diukur pakai harga real setelah waktu berjalan. Sampel akan "
            "terus bertambah tiap hari cron job jalan. Horizon yang belum cukup "
            "waktu (misal sinyal baru muncul 3 hari lalu, horizon 20 hari) belum "
            "masuk hitungan sampai waktunya cukup."
        ),
        "total_sampel_matang": len(matured),
        "total_sampel_terdaftar": len(results),
        "horizons_hari_bursa": HORIZONS,
        "by_signal": aggregate_by_signal(results),
        "detail_terbaru": sorted(results, key=lambda r: r["date"], reverse=True)[:50],
    }

    import os
    os.makedirs("web", exist_ok=True)
    with open("web/forward_test_data.json", "w") as f:
        json.dump(payload, f, indent=2, default=str)

    print(f"Selesai. {len(matured)}/{len(results)} sampel sudah matang (punya hasil).")
    print("Tersimpan di web/forward_test_data.json")


if __name__ == "__main__":
    results = compute_forward_returns()
    export_forward_test_json(results)
