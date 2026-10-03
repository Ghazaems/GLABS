import copy
import unittest
from radar_signals import advance,compare,snapshot,valid_session


def dashboard(day="2026-10-02",signal="pantau",vwap="WAIT",position="below",slope=-1):
    return {"market_data_date":day,"screening_session_date":day,
            "analysis_contract":{"version":1},"watchlist":[{
                "ticker":"AAAA","last_price_date":day,"last_close":100,
                "signal_daily":signal,"signal":signal,"signal_swing":signal,
                "vwap_analysis":{"status":"ok","signal":vwap,"settings":{"version":1},
                    **{k:{"position":position,"slope_pct":slope}
                       for k in ("vwap_fast","vwap_medium","vwap_swing")}}}]}


def rotation(day,q):
    return {"market_data_date":day,"status":"ok","methodology":{"version":1},
            "modes":{s:{"stocks":[{"symbol":"AAAA","date":day,"sector":"IDXFINANCE","quadrant":q}]}
                     for s in ("daily","weekly","swing")}}


class RadarTests(unittest.TestCase):
    def test_distinct_session_transitions(self):
        old=snapshot(dashboard("2026-10-01"),rotation("2026-10-01","Improving"))
        now=snapshot(dashboard(signal="beli",vwap="BUY",position="above",slope=1),
                     rotation("2026-10-02","Leading"))
        report=compare(now,old)
        self.assertEqual(report["comparison_status"],"ready")
        self.assertEqual(report["previous_session"],"2026-10-01")
        self.assertEqual({e["kind"] for e in report["modes"]["daily"]["events"]},
                         {"composite","vwap_focus","rotation"})
        self.assertEqual(report["full_vwap_events"][0]["after"],"BUY")
        self.assertEqual(report["modes"]["daily"]["counts"]["opportunity"],1)

    def test_no_change_is_empty_not_new_buy(self):
        old=snapshot(dashboard("2026-10-01",signal="beli",vwap="BUY"))
        now=snapshot(dashboard(signal="beli",vwap="BUY"))
        report=compare(now,old)
        self.assertFalse(report["full_vwap_events"])
        self.assertFalse(report["modes"]["daily"]["events"])

    def test_no_baseline_no_invented_signals(self):
        result=compare(snapshot(dashboard(signal="beli",vwap="BUY")),None)
        self.assertEqual(result["comparison_status"],"baseline_unavailable")
        self.assertFalse(result["full_vwap_events"])

    def test_same_day_rerun_keeps_previous(self):
        old=snapshot(dashboard("2026-10-01"))
        now=snapshot(dashboard(vwap="BUY"))
        state=advance(now,{"latest":old})
        repeated=advance(now,state)
        self.assertEqual(repeated["previous"]["session"],"2026-10-01")
        self.assertEqual(compare(now,state["previous"])["modes"],compare(now,repeated["previous"])["modes"])

    def test_next_session_advances_once(self):
        friday=snapshot(dashboard())
        monday=snapshot(dashboard("2026-10-05"))
        state=advance(monday,{"latest":friday})
        self.assertEqual(state["previous"]["session"],"2026-10-02")
        with self.assertRaises(ValueError):
            advance(friday,state)

    def test_same_session_cannot_create_transitions(self):
        current=snapshot(dashboard(vwap="BUY"))
        with self.assertRaises(ValueError):
            compare(current,snapshot(dashboard(vwap="WAIT")))

    def test_weekends_rejected(self):
        for day in ("2026-10-03","2026-10-04"):
            with self.assertRaises(ValueError):valid_session(day)

    def test_stale_stock_and_new_stock_not_transition(self):
        old=snapshot(dashboard("2026-10-01"))
        d=dashboard(signal="beli",vwap="BUY")
        d["watchlist"][0]["last_price_date"]="2026-10-01"
        result=compare(snapshot(d),old)
        self.assertFalse(result["full_vwap_events"])
        self.assertEqual(result["coverage"]["missing_tickers"],["AAAA"])
        result=compare(snapshot(dashboard(vwap="BUY")),snapshot({"market_data_date":"2026-10-01","watchlist":[]}))
        self.assertFalse(result["full_vwap_events"])
        self.assertEqual(result["coverage"]["new_tickers"],["AAAA"])

    def test_rotation_needs_published_baseline(self):
        now=snapshot(dashboard(),rotation("2026-10-02","Leading"))
        old=snapshot(dashboard("2026-10-01"))
        result=compare(now,old)
        self.assertFalse(result["modes"]["daily"]["rotation_baseline_available"])
        self.assertFalse(any(e["kind"]=="rotation" for e in result["modes"]["daily"]["events"]))

    def test_contract_and_settings_change_not_signals(self):
        old=snapshot(dashboard("2026-10-01"))
        d=dashboard(signal="beli",vwap="BUY")
        d["analysis_contract"]={"version":2}
        self.assertFalse(compare(snapshot(d),old)["full_vwap_events"])
        d["analysis_contract"]={"version":1}
        d["watchlist"][0]["vwap_analysis"]["settings"]={"version":2}
        self.assertFalse(compare(snapshot(d),old)["full_vwap_events"])

    def test_timeframes_are_independent(self):
        old=snapshot(dashboard("2026-10-01"))
        d=dashboard()
        d["watchlist"][0]["signal_daily"]="beli"
        result=compare(snapshot(d),old)
        self.assertTrue(result["modes"]["daily"]["events"])
        self.assertFalse(result["modes"]["weekly"]["events"])
        self.assertFalse(result["modes"]["swing"]["events"])

    def test_exit_is_risk_and_risk_sorted_first(self):
        old=snapshot(dashboard("2026-10-01"))
        result=compare(snapshot(dashboard(vwap="EXIT")),old)
        self.assertEqual(result["full_vwap_events"][0]["group"],"risk")
        self.assertEqual(result["full_vwap_events"][0]["priority"],0)

    def test_bearish_baseline_not_claimed_bullish(self):
        old=snapshot(dashboard("2026-10-01",vwap="AVOID"))
        result=compare(snapshot(dashboard(vwap="EXIT")),old)
        self.assertEqual(result["full_vwap_events"][0]["title"],"Full VWAP kini EXIT")

    def test_missing_vwap_not_wait(self):
        old=snapshot(dashboard("2026-10-01"))
        d=dashboard(vwap="BUY")
        d["watchlist"][0]["vwap_analysis"]["status"]="insufficient_data"
        self.assertFalse(compare(snapshot(d),old)["full_vwap_events"])


if __name__=="__main__":
    unittest.main()
