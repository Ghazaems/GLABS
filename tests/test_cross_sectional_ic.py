"""Tests for robust horizon-specific cross-sectional VWAP IC."""
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from evaluate_ic import HORIZONS, evaluate


class CrossSectionalICTests(unittest.TestCase):
    def _sample(self) -> pd.DataFrame:
        rows = []
        tickers = [f"T{index:03d}" for index in range(40)]
        for month in range(1, 13):
            date = pd.Timestamp("2025-01-15") + pd.DateOffset(months=month)
            for index, ticker in enumerate(tickers):
                predictor = float(index) / 10.0
                base = predictor + month / 100.0
                rows.append({
                    "ticker": ticker,
                    "date": date.date().isoformat(),
                    "vwap_distance_5d_pct": predictor,
                    "vwap_distance_20d_pct": predictor,
                    "vwap_distance_60d_pct": -predictor,
                    "return_5d_pct": base,
                    "return_20d_pct": base * 1.5,
                    "return_60d_pct": base * 2.0,
                })
        return pd.DataFrame(rows)

    def test_required_horizons_match_dashboard_styles(self):
        self.assertEqual(list(HORIZONS), [5, 20, 60])
        self.assertEqual(HORIZONS[5]["style"], "Daily")
        self.assertEqual(HORIZONS[20]["style"], "Weekly")
        self.assertEqual(HORIZONS[60]["style"], "Swing")

    def test_evaluate_uses_continuous_cross_sectional_predictor(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "rows.csv"
            self._sample().to_csv(source, index=False)
            report = evaluate(source)

        methodology = report["methodology"]
        self.assertEqual(methodology["type"], "cross_sectional_per_date")
        self.assertIn("continuous distance", methodology["prediction"])
        self.assertEqual(methodology["inference"], "HAC/Newey-West intercept test")
        self.assertIn("Benjamini-Hochberg", methodology["multiple_testing"])
        self.assertEqual(set(report["horizon_results"]), {"5", "20", "60"})
        self.assertEqual(report["horizon_results"]["5"]["status"], "proven_positive")
        self.assertEqual(report["horizon_results"]["60"]["status"], "reversed")
        for horizon in ("5", "20", "60"):
            stats = report["horizon_results"][horizon]["statistics"]
            for field in (
                "mean_ic",
                "std_ic",
                "t_stat_hac",
                "p_value_raw",
                "q_value_fdr",
                "hac_lags",
                "positive_months_pct",
            ):
                self.assertIn(field, stats)


if __name__ == "__main__":
    unittest.main()
