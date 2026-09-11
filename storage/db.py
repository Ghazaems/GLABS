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


def save_signal(ticker: str, date: str, signal_type: str, direction: str, note: str = ""):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO signals (ticker, date, signal_type, direction, note)
            VALUES (?, ?, ?, ?, ?)
        """, (ticker, date, signal_type, direction, note))


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
