import unittest
from unittest.mock import patch
import pandas as pd
import numpy as np
from data.ihsg_fetcher import parse_history, validate_frame, fetch_ihsg

class IHSGTests(unittest.TestCase):
    def setUp(self):
        self.dates = pd.bdate_range("2026-01-01", periods=110)
        self.session = self.dates[-1].strftime("%Y-%m-%d")
        self.frame = pd.DataFrame({"Open":100., "High":102., "Low":99., "Close":101., "Volume":0.}, index=self.dates)
    def html(self, frame=None, code="COMPOSITE"):
        frame = self.frame if frame is None else frame
        rows = []
        for i,(date,row) in enumerate(frame.iterrows()):
            timestamp = int(date.tz_localize("Asia/Jakarta").timestamp()*1000)
            import json
            rows.append("$R[%d]=" % (i+2) + json.dumps([timestamp,*row.tolist()],separators=(",",":")))
        return 'security:$R[0]={code:"'+code+'",name:"IHSG"},bars:$R[1]=['+','.join(rows)+'],intraday:null'
    def test_zero_volume_index_is_valid(self):
        self.assertEqual(len(parse_history(self.html(),self.session)),110)
    def test_future_candle_is_excluded(self):
        future = pd.concat([self.frame, self.frame.tail(1).set_axis([self.dates[-1]+pd.offsets.BDay()])])
        result = parse_history(self.html(future),self.session)
        self.assertEqual(result.index[-1],self.dates[-1])
        self.assertEqual(len(result),110)
    def test_stale_and_short_rejected(self):
        for frame in [self.frame.iloc[:-1],self.frame.tail(50)]:
            with self.assertRaises(ValueError):
                validate_frame(frame,self.session)
    def test_wrong_security_and_schema_rejected(self):
        for html in [self.html(code="LQ45"),self.html().replace("bars:","changed:"),
                     self.html().replace("101.0","null",1)]:
            with self.assertRaises(ValueError):
                parse_history(html,self.session)
    def test_duplicates_rejected(self):
        with self.assertRaises(ValueError):
            parse_history(self.html(pd.concat([self.frame,self.frame.tail(1)])),self.session)
    def test_invalid_ohlc_rejected(self):
        for col,val in [("Close",0),("High",90),("Volume",-1),("Low",np.inf)]:
            frame=self.frame.copy()
            frame.iloc[-1,frame.columns.get_loc(col)]=val
            with self.assertRaises(ValueError):
                validate_frame(frame,self.session)
    def test_weekend_rejected(self):
        with self.assertRaises(ValueError):
            validate_frame(self.frame,"2026-10-10")
    def test_primary_success_does_not_call_yahoo(self):
        def yahoo(_): raise AssertionError("Must not fetch Yahoo")
        frame,source=fetch_ihsg(self.session,public_fetch=lambda _:self.frame,yahoo_fetch=yahoo)
        self.assertFalse(source["fallback"])
    def test_primary_failure_retries_and_falls_back(self):
        calls=[]
        def fail(_):
            calls.append(1)
            raise ValueError("unavailable")
        with patch("data.ihsg_fetcher.time.sleep"):
            frame,source=fetch_ihsg(self.session,public_fetch=fail,yahoo_fetch=lambda _:self.frame)
        self.assertEqual(len(calls),2)
        self.assertTrue(source["fallback"])
    def test_both_stale_fail_closed(self):
        with patch("data.ihsg_fetcher.time.sleep"),self.assertRaises(ValueError):
            fetch_ihsg(self.session,public_fetch=lambda _:self.frame.iloc[:-1],yahoo_fetch=lambda _:self.frame.iloc[:-1])
    def test_wrong_yahoo_symbol_rejected(self):
        wrong=self.frame.copy()
        wrong.columns=pd.MultiIndex.from_product([wrong.columns,["^JKLQ45"]])
        with patch("data.ihsg_fetcher.time.sleep"),self.assertRaises(ValueError):
            fetch_ihsg(self.session,public_fetch=lambda _:None,yahoo_fetch=lambda _:wrong)
