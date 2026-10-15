import copy
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from automation.market_calendar import WIB,completed_session,in_recovery_window
from automation.pipeline_health import FILES,assess,digest,screening_errors,freshness
from automation.reconcile import plan,marker,run_targets,WORKFLOWS,deployment_state

class RecoveryTests(unittest.TestCase):
    def now(self,stamp="2026-10-15T21:00:00"):
        return datetime.fromisoformat(stamp).replace(tzinfo=WIB)
    def valid(self):
        source={"provider":"purbayasadewa.id","session":"2026-10-15","fallback":False}
        coverage={"requested":2,"success":1,"quality_gate":"passed","fetch_coverage_pct":90,
                  "success_coverage_pct":90,"analysis_completion_pct":100,"dominant_market_date_pct":100,
                  "dominant_market_date":"2026-10-15","ihsg_source":source,
                  "failed_fetch":["BBB"],"insufficient_data":[],"analysis_failed":[]}
        return {"market_data_date":"2026-10-15","screening_session_date":"2026-10-15",
                "universe_tickers":["AAA","BBB"],"watchlist":[{"ticker":"AAA"}],
                "summary":{"data_coverage":coverage}}
    def report(self,**bad):
        return {"session":"2026-10-15","recovery_eligible":True,
                "errors":{s:([bad[s]] if s in bad else []) for s in WORKFLOWS}}
    def workflow_run(self,stage,status="completed",event="schedule",title=None,created="2026-10-15T12:00:00Z",**kw):
        return {"path":".github/workflows/"+WORKFLOWS[stage],"head_branch":"main","status":status,
                "event":event,"created_at":created,"display_title":title or "Daily screening",**kw}
    def test_clock_calendar_and_grace(self):
        cases={"2026-10-15T15:00:00":"2026-10-14","2026-10-15T16:15:00":"2026-10-15",
               "2026-10-17T02:00:00":"2026-10-16","2026-10-18T21:00:00":"2026-10-16",
               "2026-12-25T21:00:00":"2026-12-23","2026-08-17T20:00:00":"2026-08-14"}
        for stamp,want in cases.items():
            self.assertEqual(completed_session(self.now(stamp)).isoformat(),want)
        self.assertFalse(in_recovery_window(self.now("2026-10-15T17:59:00")))
        self.assertTrue(in_recovery_window(self.now("2026-10-15T18:00:00")))
        self.assertTrue(in_recovery_window(self.now("2026-10-17T02:00:00")))
        with self.assertRaises(ValueError):completed_session(self.now("2027-01-04T21:00:00"))
        with self.assertRaises(ValueError):completed_session(datetime(2026,10,15))
    def test_exact_universe_not_only_count(self):
        d=self.valid()
        self.assertFalse(screening_errors(d,["AAA","BBB"],"2026-10-15"))
        d["universe_tickers"]=["AAA","CCC"]
        self.assertIn("universe_mismatch",screening_errors(d,["AAA","BBB"],"2026-10-15"))
        d["universe_tickers"]=["AAA","AAA"]
        self.assertIn("universe_mismatch",screening_errors(d,["AAA","BBB"],"2026-10-15"))
    def test_quality_source_and_missing_report(self):
        for key,value in [("quality_gate","failed"),("fetch_coverage_pct",79),("analysis_completion_pct",90)]:
            d=self.valid();d["summary"]["data_coverage"][key]=value
            self.assertIn("quality_gate_failed",screening_errors(d,["AAA","BBB"],"2026-10-15"))
        d=self.valid();d["summary"]["data_coverage"]["failed_fetch"]=[]
        self.assertIn("unaccounted_tickers",screening_errors(d,["AAA","BBB"],"2026-10-15"))
        d=self.valid();d["summary"]["data_coverage"]["ihsg_source"]["session"]="2026-10-14"
        self.assertIn("ihsg_source_mismatch",screening_errors(d,["AAA","BBB"],"2026-10-15"))
    def test_recovery_dependency_order(self):
        r=self.report(screening="stale",rotation="stale",radar="stale")
        self.assertEqual(plan(r,[])["dispatch"],["screening"])
        r=self.report(rotation="stale",radar="stale")
        self.assertEqual(plan(r,[])["dispatch"],["rotation"])
        self.assertEqual(plan(self.report(radar="stale"),[])["dispatch"],["radar"])
        self.assertEqual(plan(self.report(),[])["dispatch"],[])
        r["recovery_eligible"]=False
        self.assertEqual(plan(r,[])["dispatch"],[])
    def test_no_duplicate_active_runs(self):
        for status in ("queued","in_progress","waiting","requested","pending"):
            r=plan(self.report(screening="stale"),[self.workflow_run("screening",status=status)])
            self.assertEqual(r["dispatch"],[])
            self.assertEqual(r["waiting"],["screening"])
    def test_recovery_once_per_session_even_after_failure(self):
        for stage in WORKFLOWS:
            r=plan(self.report(**{stage:"stale"}),[self.workflow_run(stage,event="workflow_dispatch",
                title=marker(stage,"2026-10-15"),conclusion="failure",run_attempt=2)])
            self.assertEqual(r["dispatch"],[])
            self.assertEqual(r["exhausted"],[stage])
        previous=self.workflow_run("screening",event="workflow_dispatch",created="2026-10-14T14:00:00Z")
        self.assertEqual(plan(self.report(screening="stale"),[previous])["dispatch"],["screening"])
    def test_old_manual_recovery_is_not_repeated(self):
        run=self.workflow_run("screening",event="workflow_dispatch",created="2026-10-15T14:00:00Z")
        self.assertEqual(plan(self.report(screening="stale"),[run])["exhausted"],["screening"])
        late=self.workflow_run("screening",event="workflow_dispatch",created="2026-10-15T18:00:00Z")
        self.assertEqual(plan(self.report(screening="stale"),[late])["exhausted"],["screening"])
    def test_allowlist_never_contains_validation(self):
        self.assertEqual(set(WORKFLOWS),{"screening","activity","ihsg","rotation","radar"})
        self.assertFalse(any("validation" in path or "backtest" in path for path in WORKFLOWS.values()))
    def test_fresh_dispatch_is_noop_and_obsolete_request_rejected(self):
        from types import SimpleNamespace
        with patch.dict("sys.modules",{"idx_tickers_500":SimpleNamespace(IDX_SCREENING_TICKERS=["AAA","BBB"])}):
            with patch("automation.pipeline_health.read_feed",return_value=(self.valid(),"hash")):
                self.assertFalse(freshness(now=self.now())["run"])
                self.assertEqual(freshness(now=self.now(),requested_session="2026-10-14")["reason"],"obsolete-recovery-request")
    def test_nonfinite_quality_does_not_pass(self):
        d=self.valid();d["summary"]["data_coverage"]["fetch_coverage_pct"]=float("nan")
        self.assertIn("quality_gate_failed",screening_errors(d,["AAA","BBB"],"2026-10-15"))
    def test_deployment_is_not_confused_with_unit_tests(self):
        self.assertEqual(deployment_state([{"context":"Unit tests","state":"success"}]),"unknown")
        self.assertEqual(deployment_state([{"context":"Vercel","state":"pending"},{"context":"Vercel","state":"success"}]),"pending")
        self.assertEqual(deployment_state([{"context":"Vercel","state":"failure"}]),"failure")
    def test_dispatch_transport_and_budget_exhaustion(self):
        from automation import reconcile
        from types import SimpleNamespace
        import os
        calls=[]
        report=self.report(screening="stale");report["healthy"]=False
        def api(path,body=None):
            if body is not None:
                calls.append((path,body));return {}
            if path=="commits/main":return {"sha":"abc"}
            return {"statuses":[{"context":"Vercel","state":"success"}]}
        with tempfile.TemporaryDirectory() as tmp:
            previous=os.getcwd()
            try:
                os.chdir(tmp)
                with patch.dict("sys.modules",{"idx_tickers_500":SimpleNamespace(IDX_SCREENING_TICKERS=["AAA","BBB"])}), patch.object(reconcile,"assess",return_value=report), patch.object(reconcile,"api",side_effect=api), patch("builtins.print"):
                    with patch.object(reconcile,"recent_runs",return_value=[]):
                        reconcile.main()
                    self.assertEqual(calls,[("actions/workflows/daily-screening.yml/dispatches",{"ref":"main","inputs":{"recovery_session":"2026-10-15"}})])
                    used=self.workflow_run("screening",event="workflow_dispatch",title=marker("screening","2026-10-15"))
                    with patch.object(reconcile,"recent_runs",return_value=[used]),self.assertRaisesRegex(RuntimeError,"exhausted"):
                        reconcile.main()
                    self.assertEqual(len(calls),1)
                    self.assertEqual(json.loads(Path("pipeline-health.json").read_text())["exhausted"],["screening"])
            finally:
                os.chdir(previous)
    def test_full_snapshot_hashes_and_partial_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"web").mkdir();(root/"data").mkdir()
            (root/"data/purbaya_activity.py").write_text("VERSION = 2")
            d=self.valid()
            raw=json.dumps(d).encode()
            import hashlib
            dh=hashlib.sha256(raw).hexdigest()
            rotation={"status":"ok","market_data_date":"2026-10-15","dashboard_sha256":dh,
                      "modes":{k:{} for k in ("daily","weekly","swing")}}
            data={"screening":d,"rotation":rotation,
                  "history":{"status":"ok","market_data_date":"2026-10-15","dashboard_sha256":dh,
                             "benchmarks":{"COMPOSITE":{"status":"ok"}}},
                  "radar":{"status":"ok","market_data_date":"2026-10-15","dashboard_sha256":dh,
                           "rotation_sha256":digest(rotation)},
                  "ihsg":{"market_data_date":"2026-10-15","latest":{"date":"2026-10-15"},
                          "source":{"provider":"purbayasadewa.id","session":"2026-10-15"}},
                  "activity":{"method_version":2,"provider":"purbayasadewa.id","market_data_date":"2026-10-15",
                     "screening_session_date":"2026-10-15","universe_tickers":["AAA","BBB"],
                     "coverage":{"total":2,"available":1,"unavailable":1},
                     "stocks":{"AAA":{"status":"ok","source":{"provider":"purbayasadewa.id","session":"2026-10-15"},
                                      "latest":{"date":"2026-10-15"},"history":[{"date":"2026-10-15"}]},
                               "BBB":{"status":"unavailable","source":{"provider":"purbayasadewa.id","session":"2026-10-15"}}}}}
            for key,payload in data.items():
                (root/FILES[key]).write_text(json.dumps(payload))
            before=(root/FILES["screening"]).read_bytes()
            report=assess(root,["AAA","BBB"],self.now())
            self.assertTrue(report["healthy"],report)
            self.assertEqual(before,(root/FILES["screening"]).read_bytes())
            data["radar"]["rotation_sha256"]="stale"
            (root/FILES["radar"]).write_text(json.dumps(data["radar"]))
            self.assertEqual(plan(assess(root,["AAA","BBB"],self.now()),[])["dispatch"],["radar"])
            (root/FILES["activity"]).unlink()
            self.assertIn("activity",run_targets(assess(root,["AAA","BBB"],self.now())))
if __name__=="__main__":
    unittest.main()


