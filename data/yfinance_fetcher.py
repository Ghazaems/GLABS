
"""
Multi-source data fetcher untuk IDX — yfinance + RTI Business + Investing.com.
Otomatis fallback kalau source sebelumnya gagal.
"""
import pandas as pd
import yfinance as yf
import requests
from bs4 import BeautifulSoup
import time
import json
from pathlib import Path
from datetime import datetime, timedelta


# ============================================================
# SOURCE 1: YFINANCE (primary) — cepat tapi tidak lengkap
# ============================================================
def _fetch_yfinance_batch(tickers: list[str], period: str = "1y") -> dict[str, pd.DataFrame]:
    """Batch download yfinance."""
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

    print(f"[yfinance] Success: {len(result)}/{len(tickers)}")
    return result


# ============================================================
# SOURCE 2: RTI BUSINESS (fallback) — data lengkap IDX
# ============================================================
def _fetch_rti_single(ticker: str, period_days: int = 365) -> pd.DataFrame | None:
    """
    Fetch dari RTI Business — data paling lengkap untuk IDX.
    RTI Business adalah sumber data resmi yang dipakai trader Indonesia.
    """
    try:
        # RTI Business punya endpoint untuk historical data
        # URL pattern: https://rti.co.id/stock/{ticker}
        url = f"https://rti.co.id/stock/{ticker}"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html",
        }

        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code != 200:
            return None

        # Parse HTML untuk extract data harga
        # RTI biasanya punya tabel historical data
        soup = BeautifulSoup(response.text, "html.parser")

        # Cari tabel historical data
        # Struktur HTML RTI bisa berubah, ini pattern umum
        table = soup.find("table", class_="table-history") or soup.find("table", {"id": "historical-data"})

        if not table:
            return None

        # Extract data dari tabel
        rows = []
        for tr in table.find_all("tr")[1:]:  # skip header
            cols = tr.find_all("td")
            if len(cols) >= 6:
                try:
                    date_str = cols[0].text.strip()
                    date = pd.to_datetime(date_str)

                    # Parse harga (format: "1.234" atau "1,234")
                    def parse_price(text):
                        return float(text.replace(",", "").replace(".", ""))

                    open_p = parse_price(cols[1].text)
                    high = parse_price(cols[2].text)
                    low = parse_price(cols[3].text)
                    close = parse_price(cols[4].text)
                    volume = int(cols[5].text.replace(",", "").replace(".", ""))

                    rows.append({
                        "Date": date,
                        "Open": open_p,
                        "High": high,
                        "Low": low,
                        "Close": close,
                        "Volume": volume,
                    })
                except (ValueError, IndexError):
                    continue

        if not rows:
            return None

        df = pd.DataFrame(rows)
        df = df.set_index("Date")
        df = df.sort_index()

        # Filter by period
        cutoff = datetime.now() - timedelta(days=period_days)
        df = df[df.index >= cutoff]

        if len(df) < 30:
            return None

        return df

    except Exception as e:
        print(f"[RTI] Error {ticker}: {e}")
        return None


def _fetch_rti_batch(tickers: list[str], period_days: int = 365) -> dict[str, pd.DataFrame]:
    """Batch fetch dari RTI Business dengan rate limiting."""
    print(f"[RTI] Fetching {len(tickers)} tickers...")

    result = {}

    for i, ticker in enumerate(tickers):
        df = _fetch_rti_single(ticker, period_days)

        if df is not None:
            result[ticker] = df
            print(f"[RTI] ✓ {ticker}")
        else:
            print(f"[RTI] ✗ {ticker}")

        # Rate limiting — jangan spam RTI
        if (i + 1) % 10 == 0:
            print(f"[RTI] Progress: {i + 1}/{len(tickers)}")
            time.sleep(1)

        time.sleep(0.3)  # 300ms delay per request

    print(f"[RTI] Success: {len(result)}/{len(tickers)}")
    return result


# ============================================================
# SOURCE 3: INVESTING.COM (fallback 2) — backup terakhir
# ============================================================
def _fetch_investing_single(ticker: str, period_days: int = 365) -> pd.DataFrame | None:
    """
    Fetch dari Investing.com — backup terakhir.
    Investing.com punya data historis lengkap untuk IDX.
    """
    try:
        # Investing.com URL pattern untuk IDX
        url = f"https://www.investing.com/equities/{ticker.lower()}-historical-data"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html",
        }

        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code != 200:
            return None

        soup = BeautifulSoup(response.text, "html.parser")
        table = soup.find("table", {"id": "curr_table"})

        if not table:
            return None

        rows = []
        for tr in table.find_all("tr")[1:]:
            cols = tr.find_all("td")
            if len(cols) >= 6:
                try:
                    date_str = cols[0].text.strip()
                    date = pd.to_datetime(date_str, format="%b %d, %Y")

                    def parse_price(text):
                        return float(text.replace(",", ""))

                    close = parse_price(cols[1].text)
                    open_p = parse_price(cols[2].text)
                    high = parse_price(cols[3].text)
                    low = parse_price(cols[4].text)

                    vol_str = cols[5].text.replace(",", "")
                    if "K" in vol_str:
                        volume = int(float(vol_str.replace("K", "")) * 1000)
                    elif "M" in vol_str:
                        volume = int(float(vol_str.replace("M", "")) * 1000000)
                    else:
                        volume = int(float(vol_str))

                    rows.append({
                        "Date": date,
                        "Open": open_p,
                        "High": high,
                        "Low": low,
                        "Close": close,
                        "Volume": volume,
                    })
                except (ValueError, IndexError):
                    continue

        if not rows:
            return None

        df = pd.DataFrame(rows)
        df = df.set_index("Date")
        df = df.sort_index()

        cutoff = datetime.now() - timedelta(days=period_days)
        df = df[df.index >= cutoff]

        if len(df) < 30:
            return None

        return df

    except Exception as e:
        print(f"[Investing] Error {ticker}: {e}")
        return None


def _fetch_investing_batch(tickers: list[str], period_days: int = 365) -> dict[str, pd.DataFrame]:
    """Batch fetch dari Investing.com."""
    print(f"[Investing] Fetching {len(tickers)} tickers...")

    result = {}

    for i, ticker in enumerate(tickers):
        df = _fetch_investing_single(ticker, period_days)

        if df is not None:
            result[ticker] = df
            print(f"[Investing] ✓ {ticker}")
        else:
            print(f"[Investing] ✗ {ticker}")

        if (i + 1) % 5 == 0:
            time.sleep(1)

        time.sleep(0.5)

    print(f"[Investing] Success: {len(result)}/{len(tickers)}")
    return result


# ============================================================
# MULTI-SOURCE FETCHER — OTOMATIS FALLBACK
# ============================================================
def fetch_batch(tickers: list[str], period: str = "1y") -> dict[str, pd.DataFrame]:
    """
    Multi-source fetcher dengan automatic fallback.

    Alur:
    1. Coba yfinance (cepat, batch)
    2. Untuk yang gagal → coba RTI Business (lengkap, lebih lambat)
    3. Untuk yang masih gagal → coba Investing.com (backup)

    Returns: dict {ticker: DataFrame}
    """
    period_days = {"1mo": 30, "3mo": 90, "6mo": 180, "1y": 365, "2y": 730, "3y": 1095}.get(period, 365)

    print(f"\n{'='*60}")
    print(f"MULTI-SOURCE FETCH: {len(tickers)} tickers")
    print(f"{'='*60}\n")

    # Step 1: yfinance
    result = _fetch_yfinance_batch(tickers, period)
    failed = [t for t in tickers if t not in result]

    # Step 2: RTI Business untuk yang gagal
    if failed:
        print(f"\n[Multi-source] {len(failed)} tickers gagal dari yfinance, coba RTI...")
        rti_result = _fetch_rti_batch(failed, period_days)
        result.update(rti_result)
        failed = [t for t in failed if t not in rti_result]

    # Step 3: Investing.com untuk yang masih gagal
    if failed:
        print(f"\n[Multi-source] {len(failed)} tickers masih gagal, coba Investing.com...")
        investing_result = _fetch_investing_batch(failed, period_days)
        result.update(investing_result)
        failed = [t for t in failed if t not in investing_result]

    # Final report
    print(f"\n{'='*60}")
    print(f"FINAL RESULT:")
    print(f"  ✓ Success: {len(result)} tickers")
    print(f"  ✗ Failed: {len(failed)} tickers")
    if failed:
        print(f"  Failed list: {', '.join(failed[:10])}{'...' if len(failed) > 10 else ''}")
    print(f"{'='*60}\n")

    return result


def fetch_daily(ticker: str, period: str = "1y") -> pd.DataFrame | None:
    """
    Fetch single ticker dengan multi-source fallback.
    Untuk IHSG, LQ45, dll.
    """
    period_days = {"1mo": 30, "3mo": 90, "6mo": 180, "1y": 365, "2y": 730, "3y": 1095}.get(period, 365)

    # Coba yfinance dulu
    try:
        raw = yf.download(
            ticker, period=period, interval="1d",
            progress=False, threads=True,
        )
        if not raw.empty:
            return raw.dropna()
    except Exception:
        pass

    # Kalau gagal, coba RTI
    df = _fetch_rti_single(ticker, period_days)
    if df is not None:
        return df

    # Kalau masih gagal, coba Investing.com
    df = _fetch_investing_single(ticker, period_days)
    if df is not None:
        return df

    print(f"[Multi-source] ✗ {ticker} gagal dari semua source")
    return None
