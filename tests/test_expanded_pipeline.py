"""Every configured stock uses the same screening route and all three horizons."""
import io
import os
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch, Mock
import pandas as pd
import main
from idx_tickers_500 import IDX_SCREENING_TICKERS

class ExpandedPipelineTests(unittest.TestCase):
    def test_every_configured_stock_is_fetched_analyzed_and_exported(self):
        frame = pd.DataFrame({"Open": 100., "High": 102., "Low": 98., "Close": 101., "Volume": 10000.},
                             index=pd.bdate_range(end="2026-10-08", periods=130))
        prices = {ticker: frame for ticker in IDX_SCREENING_TICKERS}
        def result(ticker, *args):
            return {"ticker": ticker, "last_price_date": "2026-10-08", "score": 1,
                    "signal": "pantau", "vwap_signal": "WAIT", "volatility": {"status": "ok"}}
        with patch.dict(os.environ, {"SCREENING_SESSION_DATE": "2026-10-08"}), \
             patch("main.init_db"), patch("main.add_to_watchlist") as add, \
             patch("main.fetch_batch", return_value=prices) as fetch, \
             patch("main.fetch_daily", return_value=frame), \
             patch("data.ihsg_fetcher.fetch_ihsg", return_value=(frame, {"provider": "test"})), \
             patch("main.forecast_volatility_batch", return_value={}) as volatility, \
             patch("main.load_wyckoff_calibration", return_value={}), \
             patch("main.process_ticker", side_effect=result) as process, \
             patch("main.export_dashboard_json") as export, redirect_stdout(io.StringIO()):
            main.run_screening()
        add.assert_called_once_with(list(IDX_SCREENING_TICKERS))
        fetch.assert_called_once_with(list(IDX_SCREENING_TICKERS), period="1y")
        self.assertEqual([call.args[0] for call in process.call_args_list], list(IDX_SCREENING_TICKERS))
        self.assertEqual({t for t, _ in volatility.call_args.args[0]}, set(IDX_SCREENING_TICKERS))
        rows, coverage = export.call_args.args
        self.assertEqual({row["ticker"] for row in rows}, set(IDX_SCREENING_TICKERS))
        self.assertEqual(coverage["requested"], len(IDX_SCREENING_TICKERS))
        self.assertEqual(coverage["analysis_completion_pct"], 100)
        self.assertEqual(coverage["failed_fetch"], [])
        self.assertEqual(coverage["analysis_failed"], [])

    def test_process_ticker_computes_daily_weekly_swing_without_stock_whitelist(self):
        frame = pd.DataFrame({"Open": 100., "High": 102., "Low": 98., "Close": 101., "Volume": 10000.},
                             index=pd.bdate_range(end="2026-10-08", periods=130))
        score = {"score": 1, "breakdown": {}}
        for ticker in ("BBCA", "GOTOM", "SUPA"):
            with self.subTest(ticker=ticker), \
                 patch("main.upsert_prices") as upsert, patch("main.save_signal") as save, \
                 patch("main.trend_structure", return_value="sideways") as trend, \
                 patch("main.support_resistance_levels", return_value={}) as support, \
                 patch("main.price_vs_vwap", return_value={}) as vwap, \
                 patch("main.analyze_vwap_signals", return_value={"signal": "WAIT"}), \
                 patch("main.analyze_latest_trading_range", return_value={}) as wyckoff, \
                 patch("main.safe_comparative_strength", return_value={}), \
                 patch("main.compute_score", return_value=score) as compute, \
                 patch("main.classify_signal", return_value="pantau"), \
                 patch("main.build_price_history", return_value=[]):
                row = main.process_ticker(ticker, frame, frame, frame, {}, {})
            upsert.assert_called_once_with(ticker, frame)
            self.assertEqual([c.kwargs["window"] for c in trend.call_args_list], [2, 5, 20])
            self.assertEqual([c.kwargs["window"] for c in vwap.call_args_list], [5, 20, 60])
            self.assertEqual([c.kwargs["timeframe"] for c in wyckoff.call_args_list], ["daily", "weekly", "swing"])
            self.assertEqual(compute.call_count, 3)
            self.assertTrue({"signal_daily", "signal", "signal_swing"}.issubset(row))
            self.assertTrue({"composite_daily", "composite", "composite_swing"}.issubset({c.args[2] for c in save.call_args_list}))
