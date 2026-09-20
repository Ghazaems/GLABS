"""
Storage layer - SQLite untuk harga historis dan sinyal.
Kenapa SQLite: gratis, tanpa server, cukup untuk watchlist puluhan saham.
"""
import sqlite3
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(__file__).parent / "screener.db"


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS prices (
            ticker TEXT NOT NULL,
            date TEXT NOT NULL,
            open REAL, high REAL, low REAL, close REAL, volume INTEGER,
            PRIMARY KEY (ticker, date)
        );

        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            date TEXT NOT NULL,
            signal_type TEXT NOT NULL,   -- 'trend', 'wyckoff', 'support_resistance'
            direction TEXT,              -- 'bullish' / 'bearish' / 'neutral'
            note TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS watchlist (
            ticker TEXT PRIMARY KEY,
            name TEXT,
            active INTEGER DEFAULT 1
        );
        """)
        _migrate_signal_score_columns(conn)


def _migrate_signal_score_columns(conn):
    """
    Tambah kolom skor numerik ke tabel signals yang sudah ada (kalau belum ada).
    Dulu skor komposit cuma disimpan sebagai teks di kolom note (mis. "score=82"),
    jadi tidak bisa dihitung statistiknya (uji IC butuh angka). Kolom-kolom ini
    supaya ke depannya skor & breakdown per komponen tersimpan sebagai angka asli.

    ALTER TABLE ADD COLUMN di SQLite akan error kalau kolomnya sudah ada, makanya
    dicek dulu lewat PRAGMA table_info sebelum nambah - supaya aman dijalankan
    berkali-kali (idempotent), tidak akan mengubah data yang sudah tersimpan.
    """
    existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(signals)")}
    new_cols = {
        "score": "REAL",
        "comp_trend": "REAL",
        "comp_wyckoff": "REAL",
        "comp_vwap": "REAL",
        "comp_comparative_strength": "REAL",
        "comp_support_resistance": "REAL",
    }
    for col, col_type in new_cols.items():
        if col not in existing_cols:
            conn.execute(f"ALTER TABLE signals ADD COLUMN {col} {col_type}")


def upsert_prices(ticker: str, df):
    """df: pandas DataFrame dengan index=Date, kolom Open/High/Low/Close/Volume"""
    with get_conn() as conn:
        rows = [
            (ticker, str(idx.date()), float(row["Open"]), float(row["High"]),
             float(row["Low"]), float(row["Close"]), int(row["Volume"]))
            for idx, row in df.iterrows()
        ]
        conn.executemany("""
            INSERT INTO prices (ticker, date, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker, date) DO UPDATE SET
                open=excluded.open, high=excluded.high, low=excluded.low,
                close=excluded.close, volume=excluded.volume
        """, rows)


def save_signal(ticker: str, date: str, signal_type: str, direction: str,
                 note: str = "", score: float = None, breakdown: dict = None):
    """
    score & breakdown bersifat opsional - dipakai khusus untuk signal_type
    'composite' supaya bisa dihitung uji signifikansi (IC) di forward_test.py.
    Untuk signal_type lain ('trend', 'wyckoff', dst) cukup abaikan parameter ini.
    """
    breakdown = breakdown or {}
    with get_conn() as conn:
        # Satu hasil per ticker, tanggal, dan tipe sinyal. Rerun workflow
        # memperbarui hasil, bukan menggandakan sampel forward-test.
        conn.execute(
            """
            DELETE FROM signals
            WHERE ticker = ? AND date = ? AND signal_type = ?
            """,
            (ticker, date, signal_type),
        )

        conn.execute("""
            INSERT INTO signals (
                ticker, date, signal_type, direction, note, score,
                comp_trend, comp_wyckoff, comp_vwap,
                comp_comparative_strength, comp_support_resistance
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ticker, date, signal_type, direction, note, score,
            breakdown.get("trend"), breakdown.get("wyckoff"), breakdown.get("vwap"),
            breakdown.get("comparative_strength"), breakdown.get("support_resistance"),
        ))


def get_watchlist():
    with get_conn() as conn:
        rows = conn.execute("SELECT ticker FROM watchlist WHERE active=1").fetchall()
        return [r["ticker"] for r in rows]


def add_to_watchlist(tickers: list[str]):
    with get_conn() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO watchlist (ticker) VALUES (?)",
            [(t,) for t in tickers]
        )
