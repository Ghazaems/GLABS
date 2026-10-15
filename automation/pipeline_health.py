"""Read-only publication contracts and idempotent screening freshness."""
import ast
import hashlib
import json
import math
import os
from datetime import datetime
from pathlib import Path
from automation.market_calendar import WIB, completed_session, in_recovery_window

FILES = {
    "screening": "web/dashboard_data.json",
    "rotation": "web/sector_rotation_data.json",
    "history": "web/rotation_history_data.json",
    "radar": "web/radar_data.json",
    "activity": "web/purbaya_activity_data.json",
    "ihsg": "web/ihsg_card_data.json",
}
PROVIDERS = {"purbayasadewa.id", "Yahoo Finance"}

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def read_feed(root, stage):
    try:
        raw=(Path(root)/FILES[stage]).read_bytes()
        data=json.loads(raw)
        return (data if isinstance(data,dict) else {}), hashlib.sha256(raw).hexdigest()
    except (OSError,ValueError):
        return {}, None

def screening_errors(data, universe, session):
    errors=[]
    if data.get("market_data_date")!=session or data.get("screening_session_date")!=session:
        errors.append("screening_session_stale")
    actual=data.get("universe_tickers",[])
    if not isinstance(actual,list) or len(actual)!=len(set(actual)) or set(actual)!=set(universe):
        errors.append("universe_mismatch")
    coverage=data.get("summary",{}).get("data_coverage",{})
    gates={"fetch_coverage_pct":80,"success_coverage_pct":80,
           "analysis_completion_pct":95,"dominant_market_date_pct":90}
    if coverage.get("quality_gate")!="passed" or any(not isinstance(coverage.get(k),(int,float)) or not math.isfinite(coverage[k]) or coverage[k]<v for k,v in gates.items()):
        errors.append("quality_gate_failed")
    if coverage.get("dominant_market_date")!=session:
        errors.append("market_source_date_mismatch")
    rows=data.get("watchlist",[])
    symbols=[r.get("ticker") for r in rows]
    if not rows or len(symbols)!=len(set(symbols)) or not set(symbols).issubset(universe):
        errors.append("invalid_processed_universe")
    missing=[]
    for key in ("failed_fetch","insufficient_data","analysis_failed"):
        for item in coverage.get(key,[]):
            missing.append(item.get("ticker") if isinstance(item,dict) else item)
    if set(symbols+missing)!=set(universe):
        errors.append("unaccounted_tickers")
    source=coverage.get("ihsg_source",{})
    if source.get("provider") not in PROVIDERS or source.get("session")!=session:
        errors.append("ihsg_source_mismatch")
    if coverage.get("requested")!=len(universe):
        errors.append("requested_universe_mismatch")
    return errors

def activity_version(root):
    tree=ast.parse((Path(root)/"data/purbaya_activity.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="VERSION" for t in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError("Missing activity VERSION")

def assess(root, universe, now=None):
    now=now or datetime.now(WIB)
    session=completed_session(now).isoformat()
    feeds={k:read_feed(root,k) for k in FILES}
    d,dh=feeds["screening"]
    errors={"screening":screening_errors(d,universe,session)}
    rotation,_=feeds["rotation"]; history,_=feeds["history"]
    errors["rotation"]=[]
    if (rotation.get("status")!="ok" or rotation.get("market_data_date")!=session
            or rotation.get("dashboard_sha256")!=dh
            or history.get("status")!="ok" or history.get("market_data_date")!=session
            or history.get("dashboard_sha256")!=dh
            or history.get("benchmarks",{}).get("COMPOSITE",{}).get("status")!="ok"):
        errors["rotation"].append("rotation_inputs_or_session_mismatch")
    if set(rotation.get("modes",{}))!={"daily","weekly","swing"}:
        errors["rotation"].append("rotation_modes_missing")
    radar,_=feeds["radar"]
    errors["radar"]=[]
    if (radar.get("status")!="ok" or radar.get("market_data_date")!=session
            or radar.get("dashboard_sha256")!=dh or radar.get("rotation_sha256")!=digest(rotation)):
        errors["radar"].append("radar_inputs_or_session_mismatch")
    card,_=feeds["ihsg"]
    source=card.get("source",{})
    errors["ihsg"]=[]
    if (card.get("market_data_date")!=session or card.get("latest",{}).get("date")!=session
            or source.get("session")!=session or source.get("provider") not in PROVIDERS):
        errors["ihsg"].append("ihsg_card_stale")
    activity,_=feeds["activity"]
    errors["activity"]=[]
    stocks=activity.get("stocks",{})
    if (activity.get("method_version")!=activity_version(root)
            or activity.get("provider")!="purbayasadewa.id"
            or activity.get("market_data_date")!=session or activity.get("screening_session_date")!=session
            or len(activity.get("universe_tickers",[]))!=len(universe)
            or set(activity.get("universe_tickers",[]))!=set(universe) or set(stocks)!=set(universe)
            or activity.get("coverage",{}).get("available",0)<=0):
        errors["activity"].append("activity_contract_mismatch")
    for item in stocks.values():
        src=item.get("source",{})
        if src.get("provider")!="purbayasadewa.id" or src.get("session")!=session:
            errors["activity"].append("activity_source_mismatch");break
        if item.get("status")=="ok" and (item.get("latest",{}).get("date")!=session or not item.get("history") or item["history"][-1].get("date")!=session):
            errors["activity"].append("activity_history_stale");break
    return {"session":session,"recovery_eligible":in_recovery_window(now),
            "healthy":not any(errors.values()),"errors":errors,
            "coverage":d.get("summary",{}).get("data_coverage",{}),
            "activity_coverage":activity.get("coverage",{})}

def freshness(root=".", now=None, requested_session=""):
    from idx_tickers_500 import IDX_SCREENING_TICKERS
    session=completed_session(now).isoformat()
    if requested_session and requested_session!=session:
        return {"run":False,"reason":"obsolete-recovery-request","session_date":session}
    data,_=read_feed(root,"screening")
    errors=screening_errors(data,IDX_SCREENING_TICKERS,session)
    return {"run":bool(errors),"reason":",".join(errors) if errors else "session-already-complete",
            "session_date":session}

def main():
    result=freshness(requested_session=os.environ.get("RECOVERY_SESSION",""))
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"],"a",encoding="utf-8") as output:
            for key,value in result.items():
                print(f"{key}={str(value).lower() if isinstance(value,bool) else value}",file=output)
    print(json.dumps(result))
if __name__=="__main__":
    main()


