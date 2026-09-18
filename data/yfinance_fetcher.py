"""
Fetcher data harga IDX — yfinance saja.

CATATAN PERBAIKAN (penting dibaca sebelum nambah fallback lagi):
Versi sebelumnya punya "multi-source fallback" ke RTI Business
(rti.co.id) dan Investing.com kalau yfinance gagal. Setelah dicek,
DUA-DUANYA KEMUNGKINAN BESAR TIDAK PERNAH BERHASIL (lihat riwayat commit).
Solusi: yfinance saja, ticker gagal di-skip.

CATATAN PERBAIKAN #2 (setelah 962-ticker run gagal total):
- fetch_batch dulu nembak SEMUA ticker dalam 1 request threaded raksasa
  -> langsung kena YFRateLimitError dari Yahoo, 744/853 gagal.
  Sekarang di-chunk (default 50 ticker/chunk) + jeda antar chunk +
  retry-with-backoff khusus kalau kena rate limit.
- fetch_daily kehilangan flatten MultiIndex columns (sempat ada di versi
  sebelumnya, hilang pas refactor). Ini bikin df["Close"] kadang balik
  DataFrame (bukan Series) -> crash di comparative_strength() dengan
  error "Data must be 1-dimensional". Sudah dikembalikan.
"""
import time
import pandas as pd
import yfinance as yf


def _flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


def _download_with_retry(tickers, period: str, max_retries: int = 2):
    """Download 1 chunk, retry dengan jeda panjang khusus kalau kena rate limit."""
    for attempt in range(max_retries + 1):
        try:
            return yf.download(
                tickers, period=period, interval="1d",
                group_by="ticker", threads=True, progress=False,
            )
        except Exception as e:
            msg = str(e)
            if "Rate limit" in msg or "Too Many Requests" in msg or "YFRateLimitError" in msg:
                wait = 30 * (attempt + 1)
                print(f"[yfinance] Kena rate limit, tunggu {wait}s sebelum retry "
                      f"({attempt + 1}/{max_retries})...")
                time.sleep(wait)
            else:
                print(f"[yfinance] Error saat download chunk: {e}")
                return None
    print("[yfinance] Tetap gagal setelah retry, chunk ini di-skip.")
    return None


def fetch_batch(tickers: list[str], period: str = "1y",
                 chunk_size: int = 50, delay_between_chunks: float = 8.0) -> dict[str, pd.DataFrame]:
    """
    Batch download dari yfinance, DI-CHUNK biar tidak langsung kena rate
    limit (Yahoo blokir kalau nembak ratusan ticker sekaligus dalam 1
    request). chunk_size=50 + jeda 8 detik antar chunk = jauh lebih sopan,
    walau totalnya lebih lama buat watchlist besar (962 ticker).
    """
    print(f"[yfinance] Fetching {len(tickers)} tickers dalam chunk of {chunk_size}...")
    result = {}
    chunks = [tickers[i:i + chunk_size] for i in range(0, len(tickers), chunk_size)]

    for idx, chunk in enumerate(chunks):
        print(f"[yfinance] Chunk {idx + 1}/{len(chunks)} ({len(chunk)} ticker)...")
        raw = _download_with_retry(chunk, period)

        if raw is not None and not raw.empty:
            if len(chunk) == 1:
                sub = _flatten_columns(raw).dropna()
                if not sub.empty and len(sub) > 30:
                    result[chunk[0]] = sub
            else:
                for t in chunk:
                    try:
                        sub = raw[t].dropna()
                        if not sub.empty and len(sub) > 30:
                            result[t] = sub
                    except Exception:
                        continue

        if idx < len(chunks) - 1:
            time.sleep(delay_between_chunks)

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
        raw = _flatten_columns(raw)
        if not raw.empty:
            return raw.dropna()
    except Exception as e:
        print(f"[yfinance] Error {ticker}: {e}")

    print(f"[yfinance] \u2717 {ticker} gagal diambil")
    return None
