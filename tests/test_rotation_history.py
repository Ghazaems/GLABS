import json
import sys
import types
from unittest.mock import patch
import unittest
import numpy as np
import pandas as pd
from data.rotation_history import clean_close, merge_history, aligned_history, basket_history, build_views, to_rows, BENCHMARKS, download

class RotationHistoryTests(unittest.TestCase):
    def setUp(self):
        self.dates = pd.bdate_range("2023-01-02", periods=700)
        self.session = self.dates[-1].strftime("%Y-%m-%d")
        self.market = pd.Series(np.linspace(100,160,700), index=self.dates)
        self.prices = {t:pd.Series(np.linspace(100,180+i*10,700),index=self.dates)
                       for i,t in enumerate(["AAAA","BBBB","CCCC"])}
        self.classification = {t:{"name":t,"sector":"IDXFINANCE"} for t in self.prices}
        self.sectors = {"IDXFINANCE":"Keuangan"}
    def build(self, indices=None):
        return build_views(self.prices, indices or {"COMPOSITE":self.market,"LQ45":self.market*1.2},
                           self.classification,self.sectors,self.session,{})
    def test_zero_volume_index_is_kept(self):
        data = pd.DataFrame({"Close":[100,101,102],"Volume":[0,0,0]},index=self.dates[:3])
        self.assertEqual(len(clean_close(data)),3)
    def test_invalid_prices_are_not_kept(self):
        data = pd.DataFrame({"Close":[100,0,np.inf,np.nan,105]},index=self.dates[:5])
        self.assertEqual(list(clean_close(data)),[100,105])
    def test_no_weekend_or_duplicate_observations(self):
        dates=pd.to_datetime(["2026-10-02","2026-10-03","2026-10-02"])
        data=pd.DataFrame({"Close":[100,9999,101]},index=dates)
        cleaned=clean_close(data)
        self.assertEqual(len(cleaned),1)
        self.assertEqual(cleaned.iloc[0],101)
    def test_missing_multisymbol_frame_is_not_substituted(self):
        cols=pd.MultiIndex.from_product([["AAAA.JK","BBBB.JK"],["Close"]])
        frame=pd.DataFrame([[100,200]],index=self.dates[:1],columns=cols)
        self.assertTrue(clean_close(frame,"UNKNOWN.JK").empty)
        self.assertEqual(clean_close(frame,"BBBB.JK").iloc[0],200)
    def test_single_wrong_symbol_is_not_substituted(self):
        cols=pd.MultiIndex.from_product([["OTHER.JK"],["Close"]])
        frame=pd.DataFrame([[100]],index=self.dates[:1],columns=cols)
        self.assertTrue(clean_close(frame,"MISSING.JK").empty)
    def test_download_requests_inclusive_screening_session_and_adjusted_prices(self):
        frame=pd.DataFrame({"Close":[100,101],"Volume":[0,0]},index=self.dates[-2:])
        fake=types.ModuleType("yfinance")
        calls=[]
        def fetch(symbols,**options):
            calls.append((symbols,options))
            return frame
        fake.download=fetch
        with patch.dict(sys.modules,{"yfinance":fake}):
            result=download(["^JKSE"],self.session)
        self.assertEqual(len(result["^JKSE"]),2)
        self.assertTrue(calls[0][1]["auto_adjust"])
        self.assertFalse(calls[0][1]["threads"])
        self.assertEqual(calls[0][1]["end"],(pd.Timestamp(self.session)+pd.Timedelta(days=1)).strftime("%Y-%m-%d"))
    def test_download_failed_batches_retry_only_twice(self):
        fake=types.ModuleType("yfinance")
        calls=[]
        def fetch(*args,**options):
            calls.append(options)
            raise RuntimeError("provider unavailable")
        fake.download=fetch
        with patch.dict(sys.modules,{"yfinance":fake}),patch("data.rotation_history.time.sleep"):
            result=download(["^JKSE"],self.session)
        self.assertEqual(result,{})
        self.assertEqual(len(calls),2)
    def test_future_cannot_enter_cache(self):
        rows=to_rows(self.market,self.dates[-5].strftime("%Y-%m-%d"))
        self.assertEqual(rows[-1][0],self.dates[-5].strftime("%Y-%m-%d"))
    def test_adjustment_change_requires_rebase(self):
        merged,changed=merge_history(self.market,self.market.tail(20)*.5,self.session,adjusted=True)
        self.assertTrue(changed)
        _,changed=merge_history(self.market,self.market.tail(20),self.session,adjusted=True)
        self.assertFalse(changed)
    def test_suffix_never_fills_a_missing_session(self):
        close=self.market.drop(self.dates[-8])
        history=aligned_history(close,self.market)
        self.assertEqual(len(history),7)
        self.assertEqual(history[0]["date"],self.dates[-7].strftime("%Y-%m-%d"))
    def test_daily_eligible_basket_preserves_history_when_ipo_added(self):
        self.prices["NEW"]=self.market.tail(110)
        history=basket_history(self.prices,list(self.prices),self.market.tail(600))
        self.assertEqual(len(history),600)
        self.assertEqual(history[-1]["date"],self.session)
        self.assertTrue(np.isfinite(history[-1]["close"]))
    def test_basket_minimum_members_and_real_return(self):
        self.assertEqual(basket_history(self.prices,["AAAA","BBBB"],self.market),[])
        history=basket_history(self.prices,list(self.prices),self.market)
        returns=pd.concat([s.pct_change(fill_method=None) for s in self.prices.values()],axis=1).iloc[1:].mean(axis=1)
        self.assertAlmostEqual(history[-1]["close"],float(100*(1+returns).prod()),places=6)
    def test_short_benchmark_remains_disabled_and_archived(self):
        report=self.build({"COMPOSITE":self.market,"IDX30":self.market.tail(1)})
        self.assertEqual(report["benchmarks"]["IDX30"]["status"],"insufficient_history")
        self.assertEqual(report["benchmarks"]["IDX30"]["bars"],1)
        self.assertNotIn("IDX30",report["views"])
        self.assertEqual(report["benchmarks"]["LQ45"]["status"],"stale_or_unavailable")
    def test_available_benchmarks_are_real_and_compact(self):
        report=self.build()
        self.assertIn("LQ45",report["views"])
        self.assertNotIn("stocks",report["views"]["LQ45"])
        self.assertEqual(len(report["stocks"][0]["prices"]),600)
        self.assertEqual(report["benchmarks"]["LQ45"]["history"][-1][1],192)
        self.assertEqual(report["views"]["COMPOSITE"]["sectors"][0]["source_kind"],"glabs_history_basket")
        json.dumps(report,allow_nan=False)
    def test_fresh_official_history_is_not_a_basket(self):
        report=self.build({"COMPOSITE":self.market,"IDXFINANCE":self.market*1.5})
        sector=report["views"]["COMPOSITE"]["sectors"][0]
        self.assertEqual(sector["source_kind"],"official_index")
        self.assertEqual(sector["chart_history"][-1]["close"],240)
    def test_stale_official_is_not_mixed_into_fresh_basket(self):
        report=self.build({"COMPOSITE":self.market,"IDXFINANCE":self.market.iloc[:-1]})
        self.assertEqual(report["views"]["COMPOSITE"]["sectors"][0]["source_kind"],"glabs_history_basket")
    def test_stale_ihsg_cannot_publish(self):
        with self.assertRaises(ValueError):
            self.build({"COMPOSITE":self.market.iloc[:-1]})
    def test_future_prices_do_not_change_view(self):
        future=self.dates[-1]+pd.offsets.BDay()
        first=self.build()
        self.prices={t:pd.concat([s,pd.Series([999999],index=[future])]) for t,s in self.prices.items()}
        second=self.build()
        self.assertEqual(first["views"],second["views"])
        self.assertEqual(first["stocks"],second["stocks"])

if __name__=="__main__":
    unittest.main()
