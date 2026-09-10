"""
Fetcher untuk data resmi IDX (keterbukaan informasi / pengumuman emiten).
STUB: endpoint & struktur HTML idx.co.id perlu dicek manual dulu (bisa berubah).
Ini kerangka supaya modul sentimen berita punya sumber resmi terpisah dari yfinance.
"""
import requests
from bs4 import BeautifulSoup

IDX_ANNOUNCEMENT_URL = "https://www.idx.co.id/id/perusahaan-tercatat/keterbukaan-informasi"


def fetch_announcements(ticker: str | None = None) -> list[dict]:
    """
    TODO: cek struktur halaman IDX terbaru sebelum dipakai production.
    Return list of {ticker, title, date, url}
    """
    try:
        resp = requests.get(IDX_ANNOUNCEMENT_URL, timeout=10)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[ERROR] Gagal ambil data IDX: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    # NOTE: parsing sebenarnya perlu disesuaikan setelah inspect elemen HTML asli.
    # Ini placeholder supaya modul lain bisa langsung diintegrasikan.
    return []
