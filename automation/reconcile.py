"""Bounded latest-main reconciliation. No old-run retries, scores or credentials."""
import json
import os
from datetime import datetime, timedelta
from urllib.request import Request, urlopen
from automation.market_calendar import WIB, completed_session
from automation.pipeline_health import assess

WORKFLOWS = {
    "screening":"daily-screening.yml", "rotation":"sector-rotation.yml",
    "radar":"radar-signals.yml", "activity":"purbaya-activity.yml", "ihsg":"ihsg-card.yml",
}
ACTIVE = {"queued","in_progress","waiting","requested","pending"}
MAX_DISPATCHES = 2  # Independent stages only; never two runs of the same stage.

def marker(stage,session):
    return f"Recovery {stage} {session}"

def run_targets(report):
    if not report["recovery_eligible"]:
        return []
    errors=report["errors"]
    if errors["screening"]:
        return ["screening"]
    stages=[s for s in ("rotation","ihsg","activity") if errors[s]]
    # Radar must consume the final rotation, not race it.
    if not errors["rotation"] and errors["radar"]:
        stages.append("radar")
    return stages

def plan(report,runs):
    result={"dispatch":[],"waiting":[],"exhausted":[]}
    for stage in run_targets(report):
        path=".github/workflows/"+WORKFLOWS[stage]
        relevant=[r for r in runs if r.get("path")==path and r.get("head_branch")=="main"]
        if any(r.get("status") in ACTIVE for r in relevant):
            result["waiting"].append(stage);continue
        used=any(r.get("display_title")==marker(stage,report["session"]) for r in relevant)
        if stage=="screening":
            # Respect prior human/agent recovery dispatches made before these markers existed.
            for run in relevant:
                if run.get("event")=="workflow_dispatch":
                    stamp=datetime.fromisoformat(run["created_at"].replace("Z","+00:00"))
                    if completed_session(stamp).isoformat()==report["session"]:
                        used=True
        if used:
            result["exhausted"].append(stage);continue
        if len(result["dispatch"])<MAX_DISPATCHES:
            result["dispatch"].append(stage)
    return result

def api(path,body=None):
    repo=os.environ["GITHUB_REPOSITORY"]
    if repo!="Ghazaems/GLABS":
        raise ValueError("Unexpected repository")
    request=Request("https://api.github.com/repos/"+repo+"/"+path,
                    data=json.dumps(body).encode() if body is not None else None,
                    headers={"Authorization":"Bearer "+os.environ["GH_TOKEN"],
                             "Accept":"application/vnd.github+json", "Content-Type":"application/json",
                             "X-GitHub-Api-Version":"2022-11-28"})
    # Never log request headers, credentials or provider responses.
    with urlopen(request,timeout=30) as response:
        raw=response.read()
    return json.loads(raw) if raw else {}

def recent_runs(now):
    cutoff=now-timedelta(days=7)
    result=[]
    for page in range(1,11):
        batch=api(f"actions/runs?per_page=100&page={page}")["workflow_runs"]
        result.extend(batch)
        if not batch or datetime.fromisoformat(batch[-1]["created_at"].replace("Z","+00:00"))<cutoff:
            return result
    raise RuntimeError("Run history truncated; refusing duplicate recovery")

def deployment_state(statuses):
    # Status API returns newest first. Do not confuse unit-test status with Vercel.
    return next((s["state"] for s in statuses if s.get("context")=="Vercel"),"unknown")

def main():
    from idx_tickers_500 import IDX_SCREENING_TICKERS
    now=datetime.now(WIB)
    report=assess(".",IDX_SCREENING_TICKERS,now)
    operations={"dispatch":[],"waiting":[],"exhausted":[]}
    if not report["healthy"] and report["recovery_eligible"]:
        operations=plan(report,recent_runs(now))
        for stage in operations["dispatch"]:
            # Only known data workflows; never validation/backtest or a stale ref.
            api("actions/workflows/"+WORKFLOWS[stage]+"/dispatches",
                {"ref":"main","inputs":{"recovery_session":report["session"]}})
            print(f"Dispatched {stage} from main for {report['session']}")
    head=api("commits/main")["sha"]
    deployment=deployment_state(api("commits/"+head+"/status").get("statuses",[]))
    result={"session":report["session"],"data_healthy":report["healthy"],
            "healthy":report["healthy"] and deployment=="success",
            "deployment":{"commit":head,"state":deployment,"evidence":"GitHub Vercel status; not authenticated production JSON"},
            "recovery_eligible":report["recovery_eligible"],"errors":report["errors"],**operations}
    # Small artifact; avoid uploading the 150MB source feeds or any credentials.
    with open("pipeline-health.json","w",encoding="utf-8") as output:
        json.dump(result,output,indent=2)
    with open(os.environ.get("GITHUB_STEP_SUMMARY",os.devnull),"a",encoding="utf-8") as output:
        output.write("### Published data reconciliation\n\n```json\n"+json.dumps(result,indent=2)+"\n```\n")
    print(json.dumps(result))
    if deployment in {"failure","error"}:
        raise RuntimeError("Vercel deployment failed; no fake commits, credential or production-config changes attempted")
    if operations["exhausted"]:
        raise RuntimeError("Bounded recovery exhausted: "+", ".join(operations["exhausted"])+
                           ". Retain valid data; inspect the failed workflow before any further action.")
if __name__=="__main__":
    main()


