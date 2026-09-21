"""Wyckoff timeframe screening, calibration, and scoring contracts."""
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
        tickers = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]
        for month in range(1, 7):
            for index, ticker in enumerate(tickers):
                row = {
                    "ticker": ticker,
                    "date": f"2026-{month:02d}-15",
                    "return_5d_pct": float(index),
                    "return_20d_pct": float(index) * 1.5,
                    "return_60d_pct": float(index) * 2.0,
                }
                for timeframe in TIMEFRAMES:
                    for event in EVENT_DIRECTION:
                        row[f"wyckoff_{timeframe}_{event.lower()}"] = 0
                    row[f"wyckoff_{timeframe}_spring"] = int(index >= 3)
                    row[f"wyckoff_{timeframe}_ut"] = int(index < 3)
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

    def test_event_ic_is_separate_by_event_and_timeframe(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "backtest.csv"
            self._sample().to_csv(source, index=False)
            report = evaluate(source)

        self.assertEqual(
            report["methodology"]["type"],
            "cross_sectional_per_date_per_event",
        )
        self.assertEqual(
            set(report["calibration"]),
            {"daily", "weekly", "swing"},
        )
        for timeframe in TIMEFRAMES:
            self.assertGreater(
                report["calibration"][timeframe]["Spring"],
                0,
            )
            self.assertLess(
                report["calibration"][timeframe]["UT"],
                0,
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
