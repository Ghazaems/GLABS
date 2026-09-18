"""
Pemilih 500 emiten dari universe IDX.

Daftar sumber tetap berada di idx_tickers.py. Pemilihan dilakukan secara
merata dari seluruh daftar agar hasil tidak hanya berisi ticker dengan
huruf awal A sampai M.
"""

from idx_tickers import IDX_TICKERS_COMPLETE


TARGET_TICKER_COUNT = 500


def clean_tickers(tickers: list[str]) -> list[str]:
    """
    Bersihkan, hilangkan duplikat, dan urutkan ticker.
    """
    return sorted({
        str(ticker).strip().upper()
        for ticker in tickers
        if ticker and str(ticker).strip()
    })


def select_representative_tickers(
    tickers: list[str],
    target: int = TARGET_TICKER_COUNT,
) -> list[str]:
    """
    Pilih ticker secara merata dari seluruh daftar alfabetis.

    Contoh:
    Jika sumber memiliki 849 ticker, fungsi ini mengambil tepat 500
    ticker dengan posisi yang tersebar di sepanjang daftar.
    """
    cleaned = clean_tickers(tickers)

    if target <= 0:
        raise ValueError(
            "Jumlah target ticker harus lebih besar dari nol."
        )

    if len(cleaned) < target:
        raise ValueError(
            f"Ticker sumber hanya berjumlah {len(cleaned)}, "
            f"sedangkan target berjumlah {target}."
        )

    if len(cleaned) == target:
        return cleaned

    selected_indexes = [
        int(index * len(cleaned) / target)
        for index in range(target)
    ]

    selected = [
        cleaned[index]
        for index in selected_indexes
    ]

    # Menjaga urutan sekaligus menghapus duplikat.
    selected = list(dict.fromkeys(selected))

    if len(selected) != target:
        selected_set = set(selected)

        for ticker in cleaned:
            if ticker not in selected_set:
                selected.append(ticker)
                selected_set.add(ticker)

            if len(selected) == target:
                break

    if len(selected) != target:
        raise RuntimeError(
            f"Gagal memilih tepat {target} ticker. "
            f"Hasil akhir berjumlah {len(selected)}."
        )

    return selected


IDX_TICKERS_500 = select_representative_tickers(
    IDX_TICKERS_COMPLETE,
    target=TARGET_TICKER_COUNT,
)


if __name__ == "__main__":
    print(
        f"Total ticker sumber: "
        f"{len(clean_tickers(IDX_TICKERS_COMPLETE))}"
    )
    print(
        f"Total ticker screening: "
        f"{len(IDX_TICKERS_500)}"
    )
    print(
        "10 ticker pertama: "
        f"{', '.join(IDX_TICKERS_500[:10])}"
    )
    print(
        "10 ticker terakhir: "
        f"{', '.join(IDX_TICKERS_500[-10:])}"
    )
