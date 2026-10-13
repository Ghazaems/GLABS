"""Compact IHSG card feed. Independent of sector rotation and stock scoring."""
from datetime import date, datetime, timezone
import json
import math
from pathlib import Path

def build_snapshot(rows, session, source):
    cutoff = date.fromisoformat(session)
    if cutoff.weekday() >= 5:
        raise ValueError("Session must be a trading weekday")
    if not isinstance(source, dict) or source.get("session") != session:
        raise ValueError("Source session mismatch")
    if source.get("provider") not in ("purbayasadewa.id", "Yahoo Finance"):
        raise ValueError("Unknown IHSG source")
    clean = []
    seen = set()
    for row in rows:
        day = date.fromisoformat(row["date"])
        close = row["close"]
        if day > cutoff or day.weekday() >= 5 or row["date"] in seen:
            raise ValueError("Invalid or duplicate IHSG date")
        if isinstance(close, bool) or not isinstance(close, (int, float)) or not math.isfinite(close) or close <= 0:
            raise ValueError("Invalid IHSG close")
        seen.add(row["date"])
        clean.append({"date": row["date"], "close": float(close)})
    clean.sort(key=lambda row: row["date"])
    if len(clean) < 2 or clean[-1]["date"] != session:
        raise ValueError("IHSG is stale or lacks previous close")
    clean = clean[-40:]
    last, previous = clean[-1], clean[-2]
    change = last["close"] - previous["close"]
    return {"schema_version": 1, "symbol": "^JKSE", "name": "IHSG",
            "market_data_date": session, "source": dict(source),
            "latest": {"date": session, "close": last["close"], "previous_date": previous["date"],
                       "previous_close": previous["close"], "change": round(change, 6),
                       "change_pct": round(change / previous["close"] * 100, 6)},
            "history": clean}

def run():
    from data.ihsg_fetcher import fetch_ihsg
    dashboard_path = Path("web/dashboard_data.json")
    dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
    session = dashboard.get("screening_session_date")
    if not session or dashboard.get("market_data_date") != session:
        raise ValueError("Dashboard session not verified")
    output = Path("web/ihsg_card_data.json")
    if output.exists():
        try:
            old = json.loads(output.read_text(encoding="utf-8"))
            build_snapshot(old["history"], session, old["source"])
            if old.get("schema_version") == 1 and old.get("symbol") == "^JKSE" and old.get("market_data_date") == session:
                print(f"IHSG card already current: {session}")
                return
        except (ValueError, TypeError, KeyError):
            pass
    frame, source = fetch_ihsg(session)
    rows = [{"date": index.strftime("%Y-%m-%d"), "close": float(row["Close"])}
            for index, row in frame.iterrows()]
    payload = build_snapshot(rows, session, source)
    latest_dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
    if latest_dashboard.get("market_data_date") != session or latest_dashboard.get("screening_session_date") != session:
        raise ValueError("Dashboard changed; refusing stale publication")
    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, allow_nan=False, separators=(",", ":")) + "\n", encoding="utf-8")
    temporary.replace(output)
    print(f"IHSG card: {session}; close={payload['latest']['close']}; source={source['provider']}")

if __name__ == "__main__":
    run()
