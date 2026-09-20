"""Regression tests untuk engine VWAP multi-horizon."""

import unittest

import numpy as np
import pandas as pd

from screener.vwap import (
    analyze_vwap_signals,
    relative_volume,
    rolling_vwap,
)


class TestVwapEngine(unittest.TestCase):
    @staticmethod
    def frame(rows: int = 100) -> pd.DataFrame:
        index = pd.date_range(
            "2025-01-01",
            periods=rows,
            freq="B",
        )
        close = np.linspace(100.0, 150.0, rows)

        return pd.DataFrame(
            {
                "High": close + 1.0,
                "Low": close - 1.0,
                "Close": close,
                "Volume": np.full(rows, 1_000_000.0),
            },
            index=index,
        )

    def test_equal_volume_vwap_equals_hlc3_mean(self):
        frame = self.frame(10)
        actual = rolling_vwap(frame, window=5)
        expected = (
            (
                frame["High"]
                + frame["Low"]
                + frame["Close"]
            )
            / 3.0
        ).rolling(5).mean()

        self.assertAlmostEqual(
            actual.iloc[-1],
            expected.iloc[-1],
            places=8,
        )

    def test_invalid_price_volume_pair_is_rejected(self):
        frame = self.frame(10)
        frame.loc[frame.index[-1], "High"] = np.nan
        actual = rolling_vwap(frame, window=5)

        self.assertTrue(pd.isna(actual.iloc[-1]))

    def test_negative_volume_is_rejected(self):
        frame = self.frame(10)
        frame.loc[frame.index[-1], "Volume"] = -100
        actual = rolling_vwap(frame, window=5)

        self.assertTrue(pd.isna(actual.iloc[-1]))

    def test_rvol_excludes_current_candle(self):
        frame = self.frame(30)
        frame.loc[frame.index[-1], "Volume"] = 2_000_000
        actual = relative_volume(frame, window=20)

        self.assertAlmostEqual(
            actual.iloc[-1],
            2.0,
            places=8,
        )

    def test_short_history_returns_wait(self):
        result = analyze_vwap_signals(self.frame(30))

        self.assertEqual(
            result["status"],
            "insufficient_data",
        )
        self.assertEqual(result["signal"], "WAIT")

    def test_complete_analysis_has_known_signal(self):
        result = analyze_vwap_signals(self.frame(100))

        self.assertEqual(result["status"], "ok")
        self.assertIn(
            result["signal"],
            {
                "BUY",
                "HOLD",
                "WAIT",
                "REDUCE",
                "EXIT",
                "AVOID",
            },
        )
        self.assertEqual(
            result["confidence_status"],
            "requires_out_of_sample_calibration",
        )
        self.assertIsNone(result["confidence"])

    def test_flat_market_does_not_create_buy(self):
        frame = self.frame(100)
        frame[["High", "Low", "Close"]] = 100.0
        result = analyze_vwap_signals(frame)

        self.assertNotEqual(result["signal"], "BUY")


if __name__ == "__main__":
    unittest.main()
