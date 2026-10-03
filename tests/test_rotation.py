import json
import unittest
import numpy as np
import pandas as pd
from screener.rotation import build_rotation, entity, quadrant, rotation_series, screening_session


class RotationTests(unittest.TestCase):
    def setUp(self):
        self.dates = pd.bdate_range("2026-01-01", periods=130)
        self.market = pd.Series(np.linspace(100, 115, 130), index=self.dates)
        self.prices = {t: pd.Series(np.linspace(100, 120 + i * 5, 130), index=self.dates)
                       for i, t in enumerate(["AAAA", "BBBB", "CCCC"])}
        self.classification = {t: {"name": t, "sector": "IDXFINANCE"} for t in self.prices}
        self.session = self.dates[-1].strftime("%Y-%m-%d")

    def test_last_screening_not_wall_clock_date(self):
        self.assertEqual(screening_session({
            "market_data_date": "2026-10-02",
            "screening_session_date": "2026-10-02",
            "generated_at": "2026-10-03T16:44:35+00:00",
        }), "2026-10-02")
        # Holidays keep the last successful published session too.
        self.assertEqual(screening_session({"market_data_date": "2026-09-30",
                                           "generated_at": "2026-10-03"}), "2026-09-30")

    def test_weekend_and_mismatched_screening_rejected(self):
        for day in ["2026-10-03", "2026-10-04"]:
            with self.assertRaises(ValueError):
                screening_session({"market_data_date": day})
            with self.assertRaises(ValueError):
                build_rotation(self.prices,self.market,self.classification,day)
        with self.assertRaises(ValueError):
            screening_session({"market_data_date":"2026-10-02",
                               "screening_session_date":"2026-10-03"})

    def test_weekend_benchmark_candles_are_ignored(self):
        # Even spurious historic weekend bars cannot enter a rotation window.
        original = build_rotation(self.prices,self.market,self.classification,self.session)
        weekend = self.dates[10] + pd.offsets.Week(weekday=5)
        corrupt = pd.concat([self.market, pd.Series([999999.0],index=[weekend])])
        result = build_rotation(self.prices,corrupt,self.classification,self.session)
        self.assertEqual(original["modes"], result["modes"])

    def test_quadrants_and_boundary(self):
        for x, y, q in [(101,101,"Leading"),(99,101,"Improving"),
                        (101,99,"Weakening"),(99,99,"Lagging"),
                        (100,99,"Neutral"),(101,100,"Neutral")]:
            self.assertEqual(quadrant(x,y),q)

    def test_exact_public_formula(self):
        value = rotation_series(self.prices["AAAA"], self.market, 20, 5)
        ratio = self.prices["AAAA"] / self.market
        expected = (100 * ratio / ratio.shift(20)).rolling(3).mean()
        pd.testing.assert_series_equal(value.strength, expected, check_names=False)
        pd.testing.assert_series_equal(value.momentum, 100 * expected / expected.shift(5),
                                       check_names=False)

    def test_identical_benchmark_is_neutral(self):
        row = entity("MATCH", "Matches IHSG", self.market, self.market, "weekly")
        self.assertEqual(row["quadrant"], "Neutral")
        self.assertEqual(row["strength"], 100)
        self.assertEqual(row["momentum"], 100)
        self.assertEqual(row["relative_return_pct"], 0)

    def test_all_modes_and_equal_weight(self):
        report = build_rotation(self.prices, self.market, self.classification, self.session)
        self.assertEqual(report["coverage"]["valid"], 3)
        self.assertEqual(set(report["modes"]), {"daily", "weekly", "swing"})
        for style, mode in report["modes"].items():
            self.assertEqual(len(mode["stocks"]), 3)
            sector = next(r for r in mode["sectors"] if r["symbol"] == "IDXFINANCE")
            self.assertEqual(sector["members"], 3)
            self.assertEqual(sector["status"], "ok")
            aligned = pd.concat(list(self.prices.values()), axis=1).tail(100)
            expected = 100 * (1 + aligned.pct_change(fill_method=None).iloc[1:].mean(axis=1)).prod()
            self.assertAlmostEqual(sector["last_close"], expected, places=3)
            for row in mode["stocks"]:
                self.assertEqual(row["date"], self.session)
                self.assertLessEqual(len(row["trail"]), 20)
        json.dumps(report, allow_nan=False)

    def test_missing_prices_and_unknown_not_filled(self):
        self.prices["AAAA"].iloc[-10] = np.nan
        self.prices["UNKNOWN"] = self.market
        report = build_rotation(self.prices,self.market,self.classification,self.session)
        self.assertEqual(report["coverage"]["valid"],2)
        self.assertEqual(len(report["coverage"]["excluded"]),2)
        sector = next(r for r in report["modes"]["weekly"]["sectors"] if r["symbol"]=="IDXFINANCE")
        self.assertEqual(sector["status"],"insufficient_members")

    def test_stale_benchmark_rejected(self):
        with self.assertRaises(ValueError):
            build_rotation(self.prices,self.market.iloc[:-1],self.classification,self.session)

    def test_future_prices_cannot_change_result(self):
        earlier = self.dates[-5].strftime("%Y-%m-%d")
        original = build_rotation(self.prices,self.market,self.classification,earlier)
        for close in self.prices.values():
            close.iloc[-4:] = 999999
        again = build_rotation(self.prices,self.market,self.classification,earlier)
        self.assertEqual(original["modes"],again["modes"])

    def test_invalid_and_short_history_rejected(self):
        with self.assertRaises(ValueError):
            build_rotation(self.prices,self.market.tail(99),self.classification,self.session)
        self.prices["AAAA"].iloc[-1] = np.inf
        report = build_rotation(self.prices,self.market,self.classification,self.session)
        self.assertEqual(report["coverage"]["valid"],2)


if __name__ == "__main__":
    unittest.main()
