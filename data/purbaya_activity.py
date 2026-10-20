"""Price-volume analytics from Purbaya only; no broker-flow or identity claims."""
from __future__ import annotations
import json
import re
import time
from datetime import datetime
from pathlib import Path
from threading import Event, Lock
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import numpy as np
import pandas as pd
from data.ihsg_fetcher import decode_bars

VERSION = 2
WINDOW = 20
MIN_ROWS = 60
MAX_BYTES = 4_000_000
PROVIDER = "purbayasadewa.id"
STOP = Event()
FETCH_LOCK = Lock()
LAST_REQUEST = 0.0
DEADLINE = float('inf')

def source_url(ticker):
    if not re.fullmatch(r"[A-Z][A-Z0-9]{2,7}", ticker):
        raise ValueError("invalid_ticker")
    return f"https://purbayasadewa.id/idx/saham/{ticker}"

def parse_stock(html, ticker, session):
    source_url(ticker)
    marker = re.search(
        r'security:\$R\[\d+\]=\{code:"' + re.escape(ticker)
        + r'",[^}]*kind:"stock"[^}]*\},bars:', html, re.S)
    if not marker:
        raise ValueError("source_format_or_symbol")
    rows = decode_bars(html, marker.end())
    if not rows:
        raise ValueError("empty_history")
    dates = pd.to_datetime([r[0] for r in rows], unit="ms", utc=True).tz_convert("Asia/Jakarta").tz_localize(None).normalize()
    frame = pd.DataFrame([r[1:] for r in rows], index=dates, columns=["Open","High","Low","Close","Volume"])
    return validate_frame(frame, session)

def validate_frame(frame, session):
    cutoff = pd.Timestamp(session)
    if cutoff.weekday() >= 5:
        raise ValueError("invalid_session")
    if frame.index.has_duplicates:
        raise ValueError("duplicate_dates")
    frame = frame.loc[(frame.index <= cutoff) & (frame.index.weekday < 5)].sort_index()
    values = frame.to_numpy(dtype=float)
    if not np.isfinite(values).all() or (frame.iloc[:,:4] <= 0).any().any() or (frame.Volume < 0).any():
        raise ValueError("invalid_numeric")
    if ((frame.High < frame[["Open","Close","Low"]].max(axis=1)) | (frame.Low > frame[["Open","Close","High"]].min(axis=1))).any():
        raise ValueError("invalid_ohlc")
    if len(frame) < MIN_ROWS:
        raise ValueError("insufficient_history")
    if frame.index[-1] != cutoff:
        raise ValueError("stale_history")
    return frame

def fetch_stock(ticker, session):
    global LAST_REQUEST
    for attempt in range(2):
        if time.monotonic()>DEADLINE:
            STOP.set()
        if STOP.is_set():
            raise ValueError("provider_temporarily_unavailable")
        # Shared pacing: at most two requests/second across both workers.
        with FETCH_LOCK:
            time.sleep(max(0, 0.5 - (time.monotonic()-LAST_REQUEST)))
            LAST_REQUEST = time.monotonic()
        try:
            req = Request(source_url(ticker), headers={"User-Agent":"GLABS-PriceVolume/1.0","Accept":"text/html"})
            with urlopen(req, timeout=25) as response:
                body = response.read(MAX_BYTES+1)
            if len(body)>MAX_BYTES:
                raise ValueError("response_too_large")
            return parse_stock(body.decode("utf-8"), ticker, session)
        except HTTPError as error:
            if error.code in (403,429):
                STOP.set()
                raise ValueError("provider_temporarily_unavailable") from error
            if 400 <= error.code < 500:
                raise ValueError("source_not_available") from error
            if attempt:
                raise ValueError("fetch_failed") from error
        except ValueError:
            raise
        except Exception as error:
            if attempt:
                raise ValueError("fetch_failed") from error
        time.sleep(2)
    raise ValueError("fetch_failed")

def compute(frame):
    """Experimental, causal OHLCV proxies; never broker flow or ownership."""
    # Fixed input window makes cached v1 OHLCV and fresh fetches reproducible.
    # The cumulative level is local to history_start; compare slopes, not levels.
    frame = frame.tail(180).copy()
    spread = frame.High-frame.Low
    clv = (2*frame.Close-frame.High-frame.Low)/spread.where(spread!=0)
    multiplier = clv.fillna(0)
    mfv = multiplier*frame.Volume
    baseline = frame.Volume.shift(1).rolling(WINDOW).mean()
    rvol = frame.Volume/baseline.where(baseline>0)
    intensity = (rvol-1).clip(lower=0)**2
    directional = (multiplier*rvol).where(rvol.notna())
    pressure = directional.cumsum().ewm(span=5,adjust=False).mean().where(rvol.notna())
    rotation = (rvol*(1-clv.abs())).where(spread>0)
    adl = mfv.cumsum()
    def number(value):
        return round(float(value),6) if pd.notna(value) and np.isfinite(value) else None
    history=[]
    for date,row in frame.iterrows():
        history.append({
            "date":date.strftime("%Y-%m-%d"),
            "open":number(row.Open),"high":number(row.High),"low":number(row.Low),"close":number(row.Close),
            "volume":number(row.Volume),
            "pressure":number(pressure.loc[date]),
            "money_flow_bar":number(mfv.loc[date]),
            "money_flow_line":number(adl.loc[date]),
            "relative_volume":number(rvol.loc[date]),
            "intensity":number(intensity.loc[date]),
            "volume_rotation":number(rotation.loc[date]),
        })
    return {"status":"ok","history":history,"latest":history[-1],"history_start":frame.index[0].strftime("%Y-%m-%d"),
            "bars":len(frame),"window":WINDOW}

def migrate_cached(cached, session):
    """Recompute only verified same-session Purbaya OHLCV, never v1 indicators."""
    if (cached.get("status")!="ok" or cached.get("source",{}).get("provider")!=PROVIDER
            or cached.get("source",{}).get("session")!=session
            or cached.get("latest",{}).get("date")!=session):
        return None
    try:
        rows=cached["history"]
        frame=pd.DataFrame([{k:r[k.lower()] for k in ("Open","High","Low","Close","Volume")} for r in rows],
                           index=pd.to_datetime([r["date"] for r in rows]))
        result=compute(validate_frame(frame,session))
        result["source"]=dict(cached["source"])
        result["recomputed_from_cached_ohlcv"]=True
        return result
    except (KeyError,TypeError,ValueError,OverflowError):
        return None

def generate(dashboard, previous=None, fetcher=None):
    session=dashboard["market_data_date"]
    if dashboard.get("screening_session_date")!=session:
        raise ValueError("dashboard_session_mismatch")
    tickers=sorted(set(dashboard["universe_tickers"]))
    previous=previous or {}
    reusable=(previous.get("market_data_date")==session and previous.get("method_version")==VERSION)
    old=previous.get("stocks",{}) if previous.get("market_data_date")==session else {}
    fetcher=fetcher or fetch_stock
    def process(ticker):
        cached=old.get(ticker,{})
        if (reusable and cached.get("status")=="ok" and cached.get("source",{}).get("provider")==PROVIDER
                and cached.get("source",{}).get("session")==session and cached.get("latest",{}).get("date")==session):
            return ticker,cached
        if previous.get("method_version")==1:
            migrated=migrate_cached(cached,session)
            if migrated is not None:
                return ticker,migrated
        source={"provider":PROVIDER,"url":source_url(ticker),"session":session}
        try:
            item=compute(fetcher(ticker,session))
            item["source"]=source
        except Exception as error:
            reason=str(error) if isinstance(error,ValueError) else "fetch_failed"
            if reason not in {"invalid_ticker","source_format_or_symbol","malformed_candle","empty_history","duplicate_dates",
                              "invalid_session","invalid_numeric","invalid_ohlc","insufficient_history","stale_history",
                              "provider_temporarily_unavailable","source_not_available","response_too_large","fetch_failed"}:
                reason="fetch_failed"
            item={"status":"unavailable","reason":reason,"source":source}
        return ticker,item
    with ThreadPoolExecutor(max_workers=2) as pool:
        stocks=dict(pool.map(process,tickers))
    available=sum(item["status"]=="ok" for item in stocks.values())
    return {"schema_version":1,"method_version":VERSION,"market_data_date":session,"screening_session_date":session,
            "generated_at":datetime.now().astimezone().isoformat(),"provider":PROVIDER,"universe_tickers":tickers,
            "coverage":{"total":len(tickers),"available":available,"unavailable":len(tickers)-available},
            "method":{"pressure":"EMA5(cumsum(CLV * RVOL20)); window-local anchor; not BandarMetrics LPM",
                      "money_flow_bar":"CLV * volume in shares; not actual rupiah inflow",
                      "money_flow_line":"ADL cumulative from history_start; not broker holdings",
                      "relative_volume":"Volume / mean(previous 20 sessions), excluding current session",
                      "intensity":"max(RVOL20 - 1, 0)^2; non-directional excess-activity score",
                      "volume_rotation":"RVOL20 * (1 - abs(CLV)); balanced-close activity proxy, not float turnover",
                      "rotation_colors":"<1 green, 1..2 yellow, >=2 red; heuristic activity bands, not buy/sell",
                      "CLV":"(2*Close - High - Low) / (High - Low)",
                      "anchor":"Recomputed from latest <=180 OHLCV sessions; absolute cumulative levels are not comparable across windows/stocks",
                      "zero_range":"Directional contribution = 0; rotation = null when High = Low",
                      "validation":"Experimental heuristics; no statistical predictive validation",
                      "missing_data":"null, never fabricated or Yahoo fallback"},
            "stocks":stocks}

def main():
    global DEADLINE
    DEADLINE=time.monotonic()+1200
    STOP.clear()
    dashboard=json.loads(Path("web/dashboard_data.json").read_text(encoding="utf-8"))
    path=Path("web/purbaya_activity_data.json")
    previous=json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if (previous.get("market_data_date")==dashboard["market_data_date"] and previous.get("method_version")==VERSION
            and set(previous.get("universe_tickers",[]))==set(dashboard["universe_tickers"])
            and previous.get("coverage",{}).get("available",0)>0):
        print("Purbaya activity already published for completed screening session")
        return
    data=generate(dashboard,previous)
    if data["coverage"]["available"]==0:
        raise RuntimeError("Purbaya unavailable for all stocks; previous publication retained")
    temp=path.with_suffix(".tmp")
    temp.write_text(json.dumps(data,ensure_ascii=False,allow_nan=False,separators=(",",":")),encoding="utf-8")
    temp.replace(path)
    print(f"Purbaya activity: {data['coverage']}; session={data['market_data_date']}")
if __name__=="__main__":
    main()
