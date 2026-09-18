"""
Fetcher data harga IDX — yfinance saja.

CATATAN PERBAIKAN (penting dibaca sebelum nambah fallback lagi):
Versi sebelumnya punya "multi-source fallback" ke RTI Business
(rti.co.id) dan Investing.com kalau yfinance gagal. Setelah dicek,
DUA-DUANYA KEMUNGKINAN BESAR TIDAK PERNAH BERHASIL:

1. RTI: URL & struktur HTML (class="table-history") itu TEBAKAN,
   bukan hasil verifikasi ke situs aslinya (komentar di kode lama
   sendiri bilang "pattern umum", bukan "sudah dicek").
2. Investing.com: tabel historical data di situs ini di-render pakai
   JavaScript (React) sejak beberapa tahun terakhir. request.get biasa
   cuma dapat kerangka HTML kosong sebelum JS jalan -- gak akan pernah
   nemu tabelnya. Situs ini juga sering pasang proteksi anti-bot.

Akibatnya: setiap ticker yang gagal di yfinance nunggu ~20 detik
(2x timeout 10 detik) TANPA HASIL, sebelum akhirnya di-skip juga.
Untuk watchlist besar (ratusan ticker), ini bisa nambah puluhan menit
tanpa manfaat sama sekali.

Solusi: kembali ke yfinance saja. Ticker yang gagal di-skip langsung
(sudah ditangani main.py: cek panjang data, print "[SKIP]" kalau
kurang). Kalau nanti mau nambah sumber data kedua, JANGAN nebak
struktur HTML -- verifikasi dulu manual (buka situsnya, curl manual,
cek response beneran ada tabelnya) sebelum ditulis jadi scraper.
"""
import pandas as pd
import yfinance as yf


def fetch_batch(tickers: list[str], period: str = "1y") -> dict[str, pd.DataFrame]:
    """
    Batch download dari yfinance. Ticker yang gagal/datanya kurang dari
    30 baris otomatis tidak masuk hasil (bukan error, cuma di-skip).
    """
    print(f"[yfinance] Fetching {len(tickers)} tickers...")

    raw = yf.download(
        tickers, period=period, interval="1d",
        group_by="ticker", threads=True, progress=False,
    )

    result = {}
    if len(tickers) == 1:
        if not raw.empty:
            result[tickers[0]] = raw.dropna()
        return result

    for t in tickers:
        try:
            sub = raw[t].dropna()
            if not sub.empty and len(sub) > 30:
                result[t] = sub
        except Exception:
            continue

    failed = [t for t in tickers if t not in result]
    print(f"[yfinance] Success: {len(result)}/{len(tickers)}")
    if failed:
        print(f"[yfinance] Gagal/di-skip ({len(failed)}): {', '.join(failed[:15])}"
              f"{' ...' if len(failed) > 15 else ''}")

    return result


def fetch_daily(ticker: str, period: str = "1y") -> pd.DataFrame | None:
    """Fetch 1 ticker dari yfinance (dipakai untuk IHSG, LQ45, dll)."""
    try:
        raw = yf.download(
            ticker, period=period, interval="1d",
            progress=False, threads=True,
        )
        if not raw.empty:
            return raw.dropna()
    except Exception as e:
        print(f"[yfinance] Error {ticker}: {e}")

    print(f"[yfinance] ✗ {ticker} gagal diambil")
    return None
