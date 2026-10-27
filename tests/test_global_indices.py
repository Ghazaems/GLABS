import unittest
from datetime import datetime, timezone
from data.global_indices import completed_snapshot, build_feed, INDICES, usable_history, repair_missing_closes

class GlobalIndexTests(unittest.TestCase):
    def setUp(self):
        self.rows=[{"date":"2026-10-13","close":100.0},{"date":"2026-10-14","close":102.0},{"date":"2026-10-15","close":103.0}]
        self.now=datetime(2026,10,15,2,tzinfo=timezone.utc)
    def test_completed_close_and_change(self):
        result=completed_snapshot(self.rows,self.now,"Asia/Tokyo")
        self.assertEqual(result["date"],"2026-10-14")
        self.assertEqual(result["change_pct"],2)
    def test_today_requires_confirmed_market_close(self):
        end=datetime(2026,10,15,6,tzinfo=timezone.utc).timestamp()
        result=completed_snapshot(self.rows,self.now,"Asia/Tokyo",end)
        self.assertEqual(result["date"],"2026-10-14")
        result=completed_snapshot(self.rows,datetime(2026,10,15,7,tzinfo=timezone.utc),"Asia/Tokyo",end)
        self.assertEqual(result["date"],"2026-10-15")
    def test_invalid_numbers_and_future_dates(self):
        for value in [0,-1,float("nan"),True]:
            with self.assertRaises(ValueError):
                completed_snapshot([{"date":"2026-10-13","close":value}],self.now,"Asia/Tokyo")
        with self.assertRaises(ValueError):
            completed_snapshot([{"date":"2026-10-16","close":100}],self.now,"Asia/Tokyo")
    def test_partial_failure_preserves_original_fetch_time(self):
        now=datetime(2026,10,14,22,tzinfo=timezone.utc)
        rows=[{"date":"2026-10-13","close":100},{"date":"2026-10-14","close":102}]
        def good(symbol): return rows,now.timestamp()
        old=build_feed(good,now=now)
        def partial(symbol):
            if symbol=="^GSPC": raise OSError("provider")
            return rows,now.timestamp()
        result=build_feed(partial,old,now=datetime(2026,10,15,2,tzinfo=timezone.utc))
        cached=result["indices"][0]
        self.assertEqual(cached["status"],"cached")
        self.assertEqual(cached["date"],"2026-10-14")
        self.assertEqual(cached["fetched_at"],old["indices"][0]["fetched_at"])
        self.assertEqual(len(result["indices"]),8)
    def test_total_failure_does_not_publish(self):
        def fail(symbol): raise OSError("provider")
        with self.assertRaises(ValueError): build_feed(fail,now=self.now)
    def test_yahoo_placeholder_prices_are_not_filled(self):
        rows=self.rows+[{"date":"2026-10-16","close":float("nan")},{"date":"2026-10-17","close":0}]
        self.assertEqual(usable_history(rows),self.rows)

    def test_missing_daily_close_is_repaired_from_intraday(self):
        rows=[{"date":"2026-10-23","close":100.0},{"date":"2026-10-26","close":None}]
        hourly=[{"date":"2026-10-26","close":90.0},{"date":"2026-10-26","close":101.5}]
        repaired=repair_missing_closes(rows,lambda: hourly)
        self.assertEqual(repaired[-1]["close"],101.5)
        self.assertEqual(repaired[0]["close"],100.0)

    def test_missing_daily_close_without_intraday_is_dropped(self):
        rows=[{"date":"2026-10-23","close":100.0},{"date":"2026-10-26","close":None}]
        self.assertEqual(usable_history(repair_missing_closes(rows,lambda: [])),
                         [{"date":"2026-10-23","close":100.0}])
        def boom(): raise OSError("provider")
        self.assertEqual(len(usable_history(repair_missing_closes(rows,boom))),1)

    def test_feed_never_regresses_a_published_session(self):
        now=datetime(2026,10,27,1,tzinfo=timezone.utc)
        rows=[{"date":"2026-10-22","close":100},{"date":"2026-10-23","close":101}]
        def stale(symbol): return rows,None
        old=build_feed(stale,now=now)
        newer=dict(old["indices"][3],date="2026-10-26",previous_date="2026-10-23",previous_close=101,
                   close=105,change=4,change_pct=4/101*100)
        old["indices"][3]=newer
        result=build_feed(stale,old,now=datetime(2026,10,27,4,tzinfo=timezone.utc))
        kept=result["indices"][3]
        self.assertEqual(kept["date"],"2026-10-26")
        self.assertEqual(kept["close"],105)
        self.assertEqual(kept["status"],"cached")
        self.assertEqual(kept["fetched_at"],newer["fetched_at"])

    def test_exact_catalog(self):
        self.assertEqual(len(INDICES),8)
        self.assertEqual(len({r[0] for r in INDICES}),8)
if __name__=="__main__": unittest.main()
