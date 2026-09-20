"""Tests for horizon-specific cross-sectional VWAP IC."""
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from evaluate_ic import HORIZONS, evaluate


class CrossSectionalICTests(unittest.TestCase):
    def _sample(self) -> pd.DataFrame:
        rows = []
        tickers = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]
        ranks = [-1, -1, 0, 0, 1, 1]
        for month in range(1, 7):
            date = f"2026-{month:02d}-15"
            for index, ticker in enumerate(tickers):
                base = float(index + month / 10)
                rows.append(
                    {
                        "ticker": ticker,
                        "date": date,
                        "vwap_rank_5d": ranks[index],
                        "vwap_rank_20d": ranks[index],
                        "vwap_rank_60d": -ranks[index],
                        "return_5d_pct": base,
                        "return_20d_pct": base * 1.5,
                        "return_60d_pct": base * 2.0,
                    }
                )
        return pd.DataFrame(rows)

    def test_required_horizons_match_dashboard_styles(self):
        self.assertEqual(list(HORIZONS), [5, 20, 60])
        self.assertEqual(HORIZONS[5]["style"], "Daily")
        self.assertEqual(HORIZONS[20]["style"], "Weekly")
        self.assertEqual(HORIZONS[60]["style"], "Swing")

    def test_evaluate_ranks_stocks_within_each_date(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "rows.csv"
            self._sample().to_csv(source, index=False)
            report = evaluate(source)

        self.assertEqual(
            report["methodology"]["type"],
            "cross_sectional_per_date",
        )
        self.assertTrue(
            report["methodology"]["no_time_series_per_stock"]
        )
        self.assertEqual(set(report["horizon_results"]), {"5", "20", "60"})
        self.assertEqual(
            report["horizon_results"]["5"]["status"],
            "proven_positive",
        )
        self.assertEqual(
            report["horizon_results"]["60"]["status"],
            "reversed",
        )
        for horizon in ("5", "20", "60"):
            stats = report["horizon_results"][horizon]["statistics"]
            for field in (
                "mean_ic",
                "std_ic",
                "t_stat",
                "p_value",
                "positive_months_pct",
            ):
                self.assertIn(field, stats)


if __name__ == "__main__":
    unittest.main()
