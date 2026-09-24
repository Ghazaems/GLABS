"""Wyckoff timeframe validation and scoring contracts."""
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from evaluate_wyckoff import EVENT_DIRECTION, TIMEFRAMES, evaluate
from screener.scoring import compute_score
from screener.wyckoff import WYCKOFF_TIMEFRAME_SETTINGS


class WyckoffValidationTests(unittest.TestCase):
    def _sample(self) -> pd.DataFrame:
        rows = []
        tickers = [f"T{index:03d}" for index in range(40)]
        for month in range(1, 13):
            date = pd.Timestamp("2025-01-15") + pd.DateOffset(months=month)
            for index, ticker in enumerate(tickers):
                row = {
                    "ticker": ticker,
                    "date": date.date().isoformat(),
                    "return_5d_pct": float(index),
                    "return_20d_pct": float(index) * 1.5,
                    "return_60d_pct": float(index) * 2.0,
                }
                for timeframe in TIMEFRAMES:
                    for event in EVENT_DIRECTION:
                        row[f"wyckoff_{timeframe}_{event.lower()}"] = 0
                    row[f"wyckoff_{timeframe}_spring"] = int(index >= 20)
                    row[f"wyckoff_{timeframe}_ut"] = int(index < 20)
                rows.append(row)
        return pd.DataFrame(rows)

    def test_all_timeframes_have_distinct_detection_settings(self):
        self.assertEqual(
            set(WYCKOFF_TIMEFRAME_SETTINGS),
            {"daily", "weekly", "swing"},
        )
        windows = {
            settings["range_window"]
            for settings in WYCKOFF_TIMEFRAME_SETTINGS.values()
        }
        self.assertEqual(len(windows), 3)

    def test_event_ic_uses_hac_and_fdr_before_calibration(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "backtest.csv"
            self._sample().to_csv(source, index=False)
            report = evaluate(source)

        methodology = report["methodology"]
        self.assertEqual(
            methodology["type"],
            "cross_sectional_per_date_per_event",
        )
        self.assertIn("HAC", methodology["inference"])
        self.assertIn("Benjamini-Hochberg", methodology["multiple_testing"])
        self.assertEqual(set(report["calibration"]), {"daily", "weekly", "swing"})
        for timeframe in TIMEFRAMES:
            self.assertGreater(report["calibration"][timeframe]["Spring"], 0)
            self.assertLess(report["calibration"][timeframe]["UT"], 0)

        tested = [
            row for row in report["results"]
            if row["statistics"] is not None
        ]
        self.assertTrue(tested)
        self.assertTrue(
            all(row["statistics"]["q_value_fdr"] is not None for row in tested)
        )

    def test_unvalidated_wyckoff_is_neutral_in_composite(self):
        base = compute_score(
            "sideways",
            {"current_events": ["Spring"]},
            {"position": "at_vwap"},
            {"relative_strength_trend": "neutral"},
            {"last_close": 100, "nearest_support": None, "nearest_resistance": None},
        )
        calibrated = compute_score(
            "sideways",
            {"current_events": ["Spring"]},
            {"position": "at_vwap"},
            {"relative_strength_trend": "neutral"},
            {"last_close": 100, "nearest_support": None, "nearest_resistance": None},
            wyckoff_weights={"Spring": 4.5},
        )
        self.assertEqual(base["breakdown"]["wyckoff"], 0)
        self.assertEqual(calibrated["breakdown"]["wyckoff"], 4.5)


if __name__ == "__main__":
    unittest.main()
