"""The source snapshot expands, never replaces, the owner's configured stocks."""
import re
import unittest
from data.purbaya_stock_universe import PURBAYA_STOCK_TICKERS, SOURCE_URL, SNAPSHOT_DATE
from idx_tickers_500 import IDX_TICKERS_500, REQUESTED_SCREENING_TICKERS, IDX_SCREENING_TICKERS

class PublicStockUniverseTests(unittest.TestCase):
    def test_snapshot_count_unique_and_sorted(self):
        self.assertEqual(len(PURBAYA_STOCK_TICKERS), 922)
        self.assertEqual(list(PURBAYA_STOCK_TICKERS), sorted(set(PURBAYA_STOCK_TICKERS)))
    def test_only_stock_codes_no_indices(self):
        self.assertTrue(all(re.fullmatch(r"[A-Z]{4}", code) or code == "GOTOM" for code in PURBAYA_STOCK_TICKERS))
        self.assertFalse({"IHSG", "COMPOSITE", "LQ45", "^JKSE"} & set(PURBAYA_STOCK_TICKERS))
    def test_all_source_stocks_are_screened(self):
        self.assertTrue(set(PURBAYA_STOCK_TICKERS).issubset(IDX_SCREENING_TICKERS))
    def test_old_and_requested_stocks_are_retained(self):
        old = set(IDX_TICKERS_500) | set(REQUESTED_SCREENING_TICKERS)
        self.assertEqual(len(old), 509)
        self.assertTrue(old.issubset(IDX_SCREENING_TICKERS))
        self.assertEqual(len(IDX_SCREENING_TICKERS), 959)
        self.assertEqual(IDX_SCREENING_TICKERS, sorted(set(IDX_SCREENING_TICKERS)))
    def test_source_provenance(self):
        self.assertEqual(SOURCE_URL, "https://purbayasadewa.id/idx/saham/IHSG")
        self.assertEqual(SNAPSHOT_DATE, "2026-10-09")
