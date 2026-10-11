import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from data.purbaya_activity import compute, parse_stock, generate, source_url

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
        self.assertEqual(result["latest"]["pressure"],100)
        self.assertEqual(result["latest"]["money_flow_bar"],100)
        self.assertEqual(result["latest"]["money_flow_line"],8000)
        self.assertEqual(result["latest"]["intensity"],1)
        self.assertEqual(compute(self.frame(close=90))["latest"]["pressure"],-100)
        self.assertEqual(compute(self.frame(close=100))["latest"]["pressure"],0)
    def test_intensity_excludes_current_bar(self):
        frame=self.frame();frame.iloc[-1,frame.columns.get_loc("Volume")]=1000
        self.assertEqual(compute(frame)["latest"]["intensity"],10)
    def test_zero_volume_and_range(self):
        result=compute(self.frame(volume=0))
        self.assertIsNone(result["latest"]["pressure"])
        self.assertIsNone(result["latest"]["intensity"])
        frame=self.frame(close=100);frame["High"]=100;frame["Low"]=100
        self.assertEqual(compute(frame)["latest"]["money_flow_bar"],0)
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
if __name__=="__main__":unittest.main()
