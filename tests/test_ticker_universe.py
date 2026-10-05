"""Owner-requested symbols must be screened without displacing old issuers."""
import unittest
from idx_tickers_500 import (
    IDX_TICKERS_500, IDX_SCREENING_TICKERS, REQUESTED_SCREENING_TICKERS,
)
from main import DEFAULT_WATCHLIST, EXPECTED_TICKER_COUNT, validate_ticker_universe


class TickerUniverseTests(unittest.TestCase):
    def test_all_requested_symbols_are_in_active_universe(self):
        requested = set("DEWA ENRG ESSA FAST GEMS HRUM JARR KIJA PACK PGEO ARCI BBCA BBRI BMRI BRMS BRPT BULL BUMI BUVA CUAN PGUN SUPA TEBE VKTR".split())
        self.assertEqual(requested, set(REQUESTED_SCREENING_TICKERS))
        self.assertTrue(requested.issubset(IDX_SCREENING_TICKERS))

    def test_existing_five_hundred_are_retained(self):
        self.assertEqual(len(IDX_TICKERS_500), 500)
        self.assertTrue(set(IDX_TICKERS_500).issubset(IDX_SCREENING_TICKERS))
        self.assertEqual(len(IDX_SCREENING_TICKERS), len(set(IDX_SCREENING_TICKERS)))
        self.assertEqual(IDX_SCREENING_TICKERS, sorted(IDX_SCREENING_TICKERS))

    def test_pipeline_uses_expanded_universe(self):
        self.assertEqual(DEFAULT_WATCHLIST, IDX_SCREENING_TICKERS)
        self.assertEqual(EXPECTED_TICKER_COUNT, len(IDX_SCREENING_TICKERS))
        validate_ticker_universe(list(IDX_SCREENING_TICKERS))
        with self.assertRaises(RuntimeError):
            validate_ticker_universe(list(IDX_SCREENING_TICKERS[:-1]))
