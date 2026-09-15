"""
Fetcher untuk Jarvis Research Read-only API (terminal riset milik teman).
Dokumentasi: JARVIS_READONLY_API.md (dikasih langsung, bukan API publik).

PENTING SOAL KEAMANAN: token dibaca dari environment variable
JARVIS_API_TOKEN (diisi lewat GitHub Secret). JANGAN PERNAH hardcode
token di file ini atau file manapun di repo.
"""
import os
import time
import requests

BASE_URL = "https://jarvisfinance.my.id/api/v1"
TIMEOUT = 10
# Rate limit terdokumentasi: 60 request/menit/IP. Delay 1.1s antar request
# -> maksimal ~54 request/menit, aman di bawah limit dengan buffer.
DELAY_BETWEEN_REQUESTS = 1.1


def _headers() -> dict | None:
    token = os.environ.get("JARVIS_API_TOKEN")
    if not token:
        return None
    return {"Authorization": f"Bearer {token}"}


def _get(path: str) -> dict | None:
    headers = _headers()
    if headers is None:
        print("[WARN] JARVIS_API_TOKEN tidak diset di environment - skip Jarvis API")
        return None
    try:
        resp = requests.get(f"{BASE_URL}{path}", headers=headers, timeout=TIMEOUT)
        if resp.status_code == 429:
            print(f"[WARN] Jarvis API: rate limit tercapai untuk {path}")
            return None
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        print(f"[WARN] Jarvis API gagal ambil {path}: {e}")
        return None


def get_market_regime() -> dict | None:
    """Regime pasar terkini (misal 'OVERHEAT') dari model V5 Jarvis."""
    return _get("/market-regime")


def get_weekly_picks() -> dict | None:
    """Weekly picks terbaru dari model V5 Jarvis (ranked, entry/invalidation/target)."""
    return _get("/weekly-picks")


def get_stock_signal(ticker: str) -> dict | None:
    """Setup teknikal Jarvis untuk 1 ticker IDX, atau None kalau tidak terpilih/gagal."""
    return _get(f"/stocks/{ticker}/signals")


def get_stock_signals_batch(tickers: list[str], delay: float = DELAY_BETWEEN_REQUESTS) -> dict[str, dict]:
    """Ambil sinyal Jarvis untuk banyak ticker sekaligus, dengan jeda sopan antar request."""
    result = {}
    for t in tickers:
        data = get_stock_signal(t)
        if data is not None:
            result[t] = data
        time.sleep(delay)
    return result
