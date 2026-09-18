"""
Pengambil data harga saham Indonesia melalui Yahoo Finance.

Kode internal aplikasi tetap menggunakan format BEI:
    BBRI
    BMRI
    TLKM

Saat menghubungi Yahoo Finance, kode otomatis diubah menjadi:
    BBRI.JK
    BMRI.JK
    TLKM.JK

Kode indeks seperti ^JKSE tidak diberi akhiran .JK.
"""

from __future__ import annotations

import time

import pandas as pd
import yfinance as yf


REQUIRED_COLUMNS = (
    "Open",
    "High",
    "Low",
    "Close",
    "Volume",
)

DEFAULT_CHUNK_SIZE = 20
DEFAULT_CHUNK_DELAY = 3.0
MINIMUM_PRICE_ROWS = 30


def normalize_ticker(ticker: str) -> str:
    """
    Bersihkan kode ticker untuk penggunaan internal aplikasi.
    """
    return str(ticker).strip().upper()


def to_yahoo_symbol(ticker: str) -> str:
    """
    Ubah kode ticker internal menjadi simbol Yahoo Finance.

    Contoh:
        BBRI -> BBRI.JK
        TLKM -> TLKM.JK
        ^JKSE -> ^JKSE
        BBRI.JK -> BBRI.JK
    """
    ticker = normalize_ticker(ticker)

    if not ticker:
        raise ValueError("Ticker tidak boleh kosong.")

    if ticker.startswith("^"):
        return ticker

    if ticker.endswith(".JK"):
        return ticker

    return f"{ticker}.JK"


def clean_price_frame(
    dataframe: pd.DataFrame | None,
) -> pd.DataFrame | None:
    """
    Bersihkan satu dataframe OHLCV.

    Return None apabila data kosong, tidak memiliki kolom Close,
    atau jumlah data historis terlalu sedikit.
    """
    if dataframe is None:
        return None

    if dataframe.empty:
        return None

    cleaned = dataframe.copy()

    if isinstance(cleaned.columns, pd.MultiIndex):
        cleaned.columns = (
            cleaned.columns.get_level_values(0)
        )

    available_columns = [
        column
        for column in REQUIRED_COLUMNS
        if column in cleaned.columns
    ]

    if "Close" not in available_columns:
        return None

    cleaned = cleaned[available_columns]

    cleaned = cleaned.dropna(
        subset=["Close"]
    )

    cleaned = cleaned[
        cleaned["Close"] > 0
    ]

    if len(cleaned) <= MINIMUM_PRICE_ROWS:
        return None

    return cleaned


def extract_symbol_frame(
    raw_data: pd.DataFrame | None,
    yahoo_symbol: str,
) -> pd.DataFrame | None:
    """
    Ambil data satu simbol dari hasil yf.download().

    yfinance dapat mengembalikan susunan MultiIndex yang berbeda
    tergantung jumlah ticker dan versi library. Fungsi ini mendukung
    kedua kemungkinan susunan tersebut.
    """
    if raw_data is None:
        return None

    if raw_data.empty:
        return None

    if not isinstance(
        raw_data.columns,
        pd.MultiIndex,
    ):
        return clean_price_frame(raw_data)

    level_zero = (
        raw_data.columns.get_level_values(0)
    )

    level_one = (
        raw_data.columns.get_level_values(1)
    )

    if yahoo_symbol in level_zero:
        symbol_data = raw_data[yahoo_symbol]

        return clean_price_frame(
            symbol_data
        )

    if yahoo_symbol in level_one:
        symbol_data = raw_data.xs(
            yahoo_symbol,
            axis=1,
            level=1,
        )

        return clean_price_frame(
            symbol_data
        )

    return None


def download_from_yahoo(
    yahoo_symbols: list[str],
    period: str,
) -> pd.DataFrame | None:
    """
    Jalankan satu permintaan ke Yahoo Finance.

    threads=False digunakan agar GitHub Actions tidak mengirim terlalu
    banyak request secara bersamaan.
    """
    if not yahoo_symbols:
        return None

    try:
        return yf.download(
            tickers=yahoo_symbols,
            period=period,
            interval="1d",
            group_by="ticker",
            auto_adjust=False,
            threads=False,
            progress=False,
            timeout=30,
        )

    except Exception as error:
        print(
            "[yfinance] Permintaan gagal: "
            f"{type(error).__name__}: "
            f"{error}"
        )

        return None


def download_single_ticker(
    ticker: str,
    period: str,
    max_attempts: int = 2,
) -> pd.DataFrame | None:
    """
    Unduh satu ticker dengan retry terbatas.
    """
    ticker = normalize_ticker(ticker)
    yahoo_symbol = to_yahoo_symbol(ticker)

    for attempt in range(
        1,
        max_attempts + 1,
    ):
        raw_data = download_from_yahoo(
            [yahoo_symbol],
            period,
        )

        price_data = extract_symbol_frame(
            raw_data,
            yahoo_symbol,
        )

        if price_data is not None:
            return price_data

        if attempt < max_attempts:
            wait_seconds = 5 * attempt

            print(
                f"[yfinance] {ticker} gagal. "
                f"Retry dalam {wait_seconds} detik."
            )

            time.sleep(wait_seconds)

    return None


def fetch_batch(
    tickers: list[str],
    period: str = "1y",
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    delay_between_chunks: float = (
        DEFAULT_CHUNK_DELAY
    ),
    retry_failed_individually: bool = True,
) -> dict[str, pd.DataFrame]:
    """
    Unduh banyak saham IDX secara bertahap.

    Proses:
    1. Bersihkan dan hilangkan ticker duplikat.
    2. Tambahkan .JK sebelum dikirim ke Yahoo Finance.
    3. Unduh ticker dalam batch kecil.
    4. Simpan hasil menggunakan kode tanpa .JK.
    5. Ticker yang gagal dalam batch dicoba lagi satu per satu.
    """
    normalized_tickers = list(
        dict.fromkeys(
            normalize_ticker(ticker)
            for ticker in tickers
            if ticker
            and normalize_ticker(ticker)
        )
    )

    if not normalized_tickers:
        return {}

    if chunk_size <= 0:
        raise ValueError(
            "chunk_size harus lebih besar dari nol."
        )

    results: dict[
        str,
        pd.DataFrame,
    ] = {}

    chunks = [
        normalized_tickers[
            index:index + chunk_size
        ]
        for index in range(
            0,
            len(normalized_tickers),
            chunk_size,
        )
    ]

    print(
        f"[yfinance] Mengambil "
        f"{len(normalized_tickers)} ticker "
        f"dalam {len(chunks)} batch."
    )

    for chunk_number, chunk in enumerate(
        chunks,
        start=1,
    ):
        yahoo_symbols = [
            to_yahoo_symbol(ticker)
            for ticker in chunk
        ]

        print(
            f"[yfinance] Batch "
            f"{chunk_number}/{len(chunks)}: "
            f"{len(chunk)} ticker."
        )

        raw_data = download_from_yahoo(
            yahoo_symbols,
            period,
        )

        batch_success = 0

        for ticker, yahoo_symbol in zip(
            chunk,
            yahoo_symbols,
        ):
            price_data = extract_symbol_frame(
                raw_data,
                yahoo_symbol,
            )

            if price_data is not None:
                results[ticker] = price_data
                batch_success += 1

        print(
            f"[yfinance] Batch "
            f"{chunk_number}: "
            f"{batch_success}/{len(chunk)} berhasil."
        )

        if chunk_number < len(chunks):
            time.sleep(
                delay_between_chunks
            )

    failed_tickers = [
        ticker
        for ticker in normalized_tickers
        if ticker not in results
    ]

    if (
        retry_failed_individually
        and failed_tickers
    ):
        print(
            f"[yfinance] Mencoba ulang "
            f"{len(failed_tickers)} ticker "
            f"secara individual."
        )

        for retry_number, ticker in enumerate(
            failed_tickers,
            start=1,
        ):
            print(
                f"[yfinance] Retry "
                f"{retry_number}/"
                f"{len(failed_tickers)}: "
                f"{ticker}"
            )

            price_data = download_single_ticker(
                ticker,
                period,
                max_attempts=2,
            )

            if price_data is not None:
                results[ticker] = price_data

            # Jeda pendek untuk mengurangi risiko rate limit.
            time.sleep(1.0)

    final_failed = [
        ticker
        for ticker in normalized_tickers
        if ticker not in results
    ]

    print(
        f"[yfinance] Selesai: "
        f"{len(results)}/"
        f"{len(normalized_tickers)} berhasil; "
        f"{len(final_failed)} gagal."
    )

    if final_failed:
        preview = ", ".join(
            final_failed[:30]
        )

        suffix = (
            " ..."
            if len(final_failed) > 30
            else ""
        )

        print(
            f"[yfinance] Ticker gagal: "
            f"{preview}{suffix}"
        )

    return results


def fetch_daily(
    ticker: str,
    period: str = "1y",
) -> pd.DataFrame | None:
    """
    Unduh satu saham atau indeks.

    Contoh saham:
        fetch_daily("BBRI")

    Contoh indeks:
        fetch_daily("^JKSE")
        fetch_daily("^JKLQ45")
    """
    ticker = normalize_ticker(ticker)

    price_data = download_single_ticker(
        ticker,
        period,
        max_attempts=2,
    )

    if price_data is None:
        print(
            f"[yfinance] {ticker} "
            f"gagal diambil."
        )

    return price_data
