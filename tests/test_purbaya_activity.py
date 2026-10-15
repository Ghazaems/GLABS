import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from data.purbaya_activity import compute, parse_stock, generate, source_url, VERSION

class ActivityTests(unittest.TestCase):
    def frame(self,close=110,volume=100):
        dates=pd.bdate_range(end="2026-10-09",periods=80)
        return pd.DataFrame({"Open":100.,"High":110.,"Low":90.,"Close":float(close),"Volume":float(volume)},index=dates)
    def html(self,frame,code="VKTR"):
        rows=[]
        for i,(date,row) in enumerate(frame.iterrows()):
            ms=int(date.tz_localize("Asia/Jakarta").timestamp()*1000)
            rows.append(f"$R[{i+20}]=[{ms},{row.Open},{row.High},{row.Low},{row.Close},{row.Volume}]")
        return 'security:$R[14]={code:"'+code+'",name:"Example",kind:"stock"},bars:$R[15]=['+','.join(rows)+'],intraday:'
    def test_formula(self):
        result=compute(self.frame())
        self.assertAlmostEqual(result["latest"]["pressure"],58,places=5)
        self.assertEqual(result["latest"]["money_flow_bar"],100)
        self.assertEqual(result["latest"]["money_flow_line"],8000)
        self.assertEqual(result["latest"]["intensity"],0)
        self.assertEqual(result["latest"]["relative_volume"],1)
        self.assertEqual(result["latest"]["volume_rotation"],0)
        self.assertAlmostEqual(compute(self.frame(close=90))["latest"]["pressure"],-58,places=5)
        self.assertEqual(compute(self.frame(close=100))["latest"]["pressure"],0)
    def test_intensity_excludes_current_bar(self):
        frame=self.frame();frame.iloc[-1,frame.columns.get_loc("Volume")]=1000
        self.assertEqual(compute(frame)["latest"]["intensity"],81)
        self.assertEqual(compute(frame)["latest"]["relative_volume"],10)
    def test_zero_volume_and_range(self):
        result=compute(self.frame(volume=0))
        self.assertIsNone(result["latest"]["pressure"])
        self.assertIsNone(result["latest"]["intensity"])
        frame=self.frame(close=100);frame["High"]=100;frame["Low"]=100
        self.assertEqual(compute(frame)["latest"]["money_flow_bar"],0)
        self.assertIsNone(compute(frame)["latest"]["volume_rotation"])
    def test_parse_and_cutoff(self):
        frame=self.frame()
        actual=parse_stock(self.html(frame),"VKTR","2026-10-09")
        self.assertEqual(len(actual),80)
        self.assertEqual(actual.index[-1],pd.Timestamp("2026-10-09"))
        self.assertEqual(parse_stock(self.html(frame),"VKTR","2026-10-08").index[-1],pd.Timestamp("2026-10-08"))
    def test_fail_closed(self):
        frame=self.frame()
        with self.assertRaises(ValueError):parse_stock(self.html(frame),"BBCA","2026-10-09")
        with self.assertRaises(ValueError):parse_stock(self.html(frame),"VKTR","2026-10-12")
        with self.assertRaises(ValueError):parse_stock(self.html(frame),"VKTR","2026-10-10")
        with self.assertRaises(ValueError):parse_stock(self.html(frame.iloc[:20]),"VKTR","2026-10-09")
        with self.assertRaises(ValueError):parse_stock(self.html(frame)+"" ,"../X","2026-10-09")
        broken=self.html(frame).replace(",100.0]",",null]",1)
        with self.assertRaises(ValueError):parse_stock(broken,"VKTR","2026-10-09")
    def test_partial_and_provider(self):
        dashboard={"market_data_date":"2026-10-09","screening_session_date":"2026-10-09","universe_tickers":["VKTR","BBCA"]}
        def fetcher(ticker,session):
            if ticker=="BBCA":raise ValueError("stale_history")
            return self.frame()
        result=generate(dashboard,fetcher=fetcher)
        self.assertEqual(result["coverage"],{"total":2,"available":1,"unavailable":1})
        self.assertEqual(result["stocks"]["BBCA"]["status"],"unavailable")
        self.assertEqual(result["stocks"]["VKTR"]["source"]["provider"],"purbayasadewa.id")
        self.assertNotIn("history",result["stocks"]["BBCA"])
    def test_reuse_matching_source_session_only(self):
        d={"market_data_date":"2026-10-09","screening_session_date":"2026-10-09","universe_tickers":["VKTR"]}
        first=generate(d,fetcher=lambda *args:self.frame())
        def fail(*args):self.fail("same session must reuse")
        self.assertEqual(generate(d,first,fetcher=fail)["coverage"]["available"],1)
        first["stocks"]["VKTR"]["source"]["provider"]="Yahoo"
        self.assertEqual(generate(d,first,fetcher=lambda *args:self.frame())["stocks"]["VKTR"]["source"]["provider"],"purbayasadewa.id")

    def test_causal_and_scale_invariant(self):
        frame=self.frame(close=106)
        frame["Volume"]=np.arange(80,dtype=float)+20
        full=compute(frame)
        prefix=compute(frame.iloc[:-1])
        self.assertEqual(full["history"][-2],prefix["latest"])
        scaled=frame.copy()
        scaled[["Open","High","Low","Close"]]*=10
        scaled["Volume"]*=100
        actual=compute(scaled)
        for key in ("pressure","intensity","relative_volume","volume_rotation"):
            self.assertEqual(full["latest"][key],actual["latest"][key])
        self.assertTrue(all(r["intensity"] is None for r in full["history"][:20]))
    def test_spike_rotation_and_direction(self):
        frame=self.frame(close=100)
        frame.iloc[-1,frame.columns.get_loc("Volume")]=300
        result=compute(frame)["latest"]
        self.assertEqual(result["intensity"],4)
        self.assertEqual(result["volume_rotation"],3)
        self.assertEqual(result["pressure"],0)
        self.assertGreater(compute(self.frame(close=110))["latest"]["pressure"],0)
        self.assertLess(compute(self.frame(close=90))["latest"]["pressure"],0)
    def test_cache_migration(self):
        d={"market_data_date":"2026-10-09","screening_session_date":"2026-10-09","universe_tickers":["VKTR"]}
        legacy=generate(d,fetcher=lambda *args:self.frame())
        legacy["method_version"]=1
        legacy["stocks"]["VKTR"]["latest"]["intensity"]=9999
        def fail(*args):self.fail("valid Purbaya OHLCV must recompute without network")
        result=generate(d,legacy,fetcher=fail)
        self.assertEqual(result["method_version"],VERSION)
        self.assertEqual(result["stocks"]["VKTR"]["latest"]["intensity"],0)
        self.assertTrue(result["stocks"]["VKTR"]["recomputed_from_cached_ohlcv"])
        legacy["stocks"]["VKTR"]["history"][0]["high"]=1
        calls=[]
        def fresh(*args):
            calls.append(args)
            return self.frame()
        self.assertEqual(generate(d,legacy,fetcher=fresh)["coverage"]["available"],1)
        self.assertEqual(len(calls),1)
    def test_history_anchor(self):
        frame=self.frame()
        frame=pd.concat([frame]*3,ignore_index=True)
        frame.index=pd.bdate_range(end="2026-10-09",periods=240)
        result=compute(frame)
        self.assertEqual(result["bars"],180)
        self.assertEqual(result["history_start"],frame.index[-180].strftime("%Y-%m-%d"))

if __name__=="__main__":unittest.main()
