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
from data.ihsg_fetcher import ROW

VERSION = 1
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
    pattern = (r'security:\$R\[\d+\]=\{code:"' + re.escape(ticker)
               + r'",[^}]*kind:"stock"[^}]*\},bars:\$R\[\d+\]=\[(.*?)\],intraday:')
    match = re.search(pattern, html, re.S)
    if not match:
        raise ValueError("source_format_or_symbol")
    body = match.group(1)
    if ROW.sub("", body).replace(",", "").strip():
        raise ValueError("malformed_candle")
    rows = [json.loads(m.group(1)) for m in ROW.finditer(body)]
    if not rows:
        raise ValueError("empty_history")
    dates = pd.to_datetime([r[0] for r in rows], unit="ms", utc=True).tz_convert("Asia/Jakarta").tz_localize(None).normalize()
    frame = pd.DataFrame([r[1:] for r in rows], index=dates, columns=["Open","High","Low","Close","Volume"])
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
    """CMF20 pressure; daily Money Flow Volume + cumulative ADL; lagged RVOL20."""
    spread = frame.High-frame.Low
    multiplier = ((2*frame.Close-frame.High-frame.Low)/spread.where(spread!=0)).fillna(0)
    mfv = multiplier*frame.Volume
    denominator = frame.Volume.rolling(WINDOW).sum()
    cmf = (mfv.rolling(WINDOW).sum()/denominator.where(denominator!=0))*100
    baseline = frame.Volume.shift(1).rolling(WINDOW).mean()
    rvol = frame.Volume/baseline.where(baseline!=0)
    adl = mfv.cumsum()
    def number(value):
        return round(float(value),6) if pd.notna(value) and np.isfinite(value) else None
    history=[]
    for date,row in frame.tail(180).iterrows():
        history.append({
            "date":date.strftime("%Y-%m-%d"),
            "open":number(row.Open),"high":number(row.High),"low":number(row.Low),"close":number(row.Close),
            "volume":number(row.Volume),
            "pressure":number(cmf.loc[date]),
            "money_flow_bar":number(mfv.loc[date]),
            "money_flow_line":number(adl.loc[date]),
            "intensity":number(rvol.loc[date]),
        })
    return {"status":"ok","history":history,"latest":history[-1],"history_start":frame.index[0].strftime("%Y-%m-%d"),
            "bars":len(frame),"window":WINDOW}

def generate(dashboard, previous=None, fetcher=None):
    session=dashboard["market_data_date"]
    if dashboard.get("screening_session_date")!=session:
        raise ValueError("dashboard_session_mismatch")
    tickers=sorted(set(dashboard["universe_tickers"]))
    previous=previous or {}
    reusable=(previous.get("market_data_date")==session and previous.get("method_version")==VERSION)
    old=previous.get("stocks",{}) if reusable else {}
    fetcher=fetcher or fetch_stock
    def process(ticker):
        cached=old.get(ticker,{})
        if (cached.get("status")=="ok" and cached.get("source",{}).get("provider")==PROVIDER
                and cached.get("latest",{}).get("date")==session):
            return ticker,cached
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
            "method":{"pressure":"CMF20 × 100 (−100..100); not BandarMetrics LPM",
                      "money_flow_bar":"Money Flow Volume in shares; not actual rupiah inflow",
                      "money_flow_line":"ADL cumulative from history_start; not broker holdings",
                      "intensity":"Volume / mean of previous 20 completed sessions; not trade identity",
                      "zero_range":"Money Flow Volume = 0 when High = Low",
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
