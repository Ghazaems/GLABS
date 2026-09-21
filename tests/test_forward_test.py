"""Contract tests for the persisted-signal forward-test pipeline."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import pandas as pd

import forward_test


class TestForwardTestPipeline(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        self.db_path = root / "screener.db"
        self.out_path = root / "forward_test_data.json"
        self.old_db_path = forward_test.DB_PATH
        self.old_out_path = forward_test.OUT_PATH
        forward_test.DB_PATH = self.db_path
        forward_test.OUT_PATH = self.out_path
        self._create_database()

    def tearDown(self):
        forward_test.DB_PATH = self.old_db_path
        forward_test.OUT_PATH = self.old_out_path
        self.tempdir.cleanup()

    def _create_database(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(
                """
                CREATE TABLE prices (
                    ticker TEXT NOT NULL,
                    date TEXT NOT NULL,
                    open REAL,
                    close REAL
                );
                CREATE TABLE signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    date TEXT NOT NULL,
                    signal_type TEXT NOT NULL,
                    direction TEXT,
                    note TEXT,
                    score REAL,
                    comp_trend REAL,
                    comp_wyckoff REAL,
                    comp_vwap REAL,
                    comp_comparative_strength REAL,
                    comp_support_resistance REAL
                );
                """
            )

            dates = pd.date_range(
                "2026-01-01",
                periods=30,
                freq="B",
            )
            conn.executemany(
                """
                INSERT INTO prices (
                    ticker, date, open, close
                ) VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        "TEST",
                        date.date().isoformat(),
                        100.0 + index,
                        100.5 + index,
                    )
                    for index, date in enumerate(dates)
                ],
            )

            signal_date = dates[0].date().isoformat()
            conn.execute(
                """
                INSERT INTO signals (
                    ticker, date, signal_type,
                    direction, score, note,
                    comp_trend, comp_wyckoff,
                    comp_vwap,
                    comp_comparative_strength,
                    comp_support_resistance
                ) VALUES (
                    'TEST', ?, 'composite', 'jual',
                    -60, '{}', -30, 0, -15, -15, 0
                )
                """,
                (signal_date,),
            )

            rows = [
                ("composite_daily", "beli", 60.0, "{}"),
                ("composite", "beli", 65.0, "{}"),
                ("composite_swing", "pantau", 30.0, "{}"),
                (
                    "vwap_multi",
                    "BUY",
                    None,
                    json.dumps({
                        "signal": "BUY",
                        "confidence": None,
                    }),
                ),
            ]
            conn.executemany(
                """
                INSERT INTO signals (
                    ticker, date, signal_type,
                    direction, score, note,
                    comp_trend, comp_wyckoff,
                    comp_vwap,
                    comp_comparative_strength,
                    comp_support_resistance
                ) VALUES (
                    'TEST', ?, ?, ?, ?, ?,
                    30, 0, 15, 15, 5
                )
                """,
                [
                    (
                        signal_date,
                        signal_type,
                        direction,
                        score,
                        note,
                    )
                    for (
                        signal_type,
                        direction,
                        score,
                        note,
                    ) in rows
                ],
            )

    def test_report_matches_dashboard_contract(self):
        report = forward_test.evaluate_forward()

        self.assertEqual(
            report["horizons_hari_bursa"],
            [5, 10, 20],
        )
        self.assertEqual(
            report["total_sampel_terdaftar"],
            1,
        )
        self.assertEqual(
            report["total_sampel_matang"],
            1,
        )
        self.assertEqual(
            set(report["by_timeframe"]),
            {"daily", "weekly", "swing"},
        )
        self.assertEqual(
            report["detail_terbaru"][0]["signal"],
            "beli",
        )
        self.assertEqual(
            report["by_vwap_signal"]["5"][0][
                "vwap_signal"
            ],
            "BUY",
        )
        self.assertTrue(self.out_path.exists())

        persisted = json.loads(
            self.out_path.read_text(encoding="utf-8")
        )
        self.assertEqual(
            persisted["jenis"],
            "forward_test",
        )

    def test_empty_signal_history_returns_empty_report(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM signals")

        report = forward_test.evaluate_forward()

        self.assertEqual(
            report["total_sampel_terdaftar"],
            0,
        )
        self.assertEqual(
            report["detail_terbaru"],
            [],
        )
        self.assertEqual(
            report["by_signal"]["5"],
            [],
        )

    def test_missing_database_fails_explicitly(self):
        forward_test.DB_PATH = (
            Path(self.tempdir.name) / "missing.db"
        )

        with self.assertRaises(FileNotFoundError):
            forward_test.evaluate_forward()


if __name__ == "__main__":
    unittest.main()
