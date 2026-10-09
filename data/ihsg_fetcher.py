"""Public IHSG HTML history adapter. Never execute the site's JavaScript.
Only actual weekday OHLC observations through the requested screening session.
"""
from __future__ import annotations
import json
import re
import time
from urllib.request import Request, urlopen
import numpy as np
import pandas as pd

SOURCE_URL = "https://purbayasadewa.id/idx/saham/IHSG"
MAX_BYTES = 4_000_000
MIN_ROWS = 100
NUMBER = r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?"
ROW = re.compile(r"\$R\[\d+\]=(\[" + NUMBER + r"(?:," + NUMBER + r"){5}\])")

def validate_frame(frame, session):
    cutoff = pd.Timestamp(session)
    if cutoff.weekday() >= 5:
        raise ValueError("IHSG session must be a completed weekday")
    if frame is None or frame.empty:
        raise ValueError("IHSG history is empty")
    frame = frame.copy()
    frame.index = pd.DatetimeIndex(frame.index).tz_localize(None).normalize()
    frame = frame.loc[(frame.index <= cutoff) & (frame.index.weekday < 5)]
    if frame.index.has_duplicates:
        raise ValueError("Duplicate IHSG dates")
    frame = frame.sort_index()
    cols = ["Open", "High", "Low", "Close", "Volume"]
    frame = frame[cols].apply(pd.to_numeric, errors="raise")
    values = frame.to_numpy(dtype=float)
    if not np.isfinite(values).all() or (frame[cols[:4]] <= 0).any().any() or (frame.Volume < 0).any():
        raise ValueError("Invalid IHSG numeric values")
    if ((frame.High < frame[["Open", "Close", "Low"]].max(axis=1)) |
        (frame.Low > frame[["Open", "Close", "High"]].min(axis=1))).any():
        raise ValueError("Invalid IHSG OHLC range")
    if len(frame) < MIN_ROWS or frame.index[-1] != cutoff:
        raise ValueError("IHSG stale or fewer than 100 completed sessions")
    return frame

def parse_history(html, session):
    block = re.search(
        r'security:\$R\[\d+\]=\{code:"COMPOSITE"[^}]*\},bars:\$R\[\d+\]=\[(.*?)\],intraday:',
        html, re.S)
    if not block:
        raise ValueError("IHSG HTML history format changed or wrong security")
    body = block.group(1)
    matches = list(ROW.finditer(body))
    # Fail closed: do not quietly omit a malformed candle.
    remainder = ROW.sub("", body).replace(",", "").strip()
    if not matches or remainder:
        raise ValueError("Malformed IHSG candle array")
    rows = [json.loads(m.group(1)) for m in matches]
    dates = pd.to_datetime([r[0] for r in rows], unit="ms", utc=True).tz_convert("Asia/Jakarta").tz_localize(None).normalize()
    frame = pd.DataFrame([r[1:] for r in rows], index=dates,
                         columns=["Open", "High", "Low", "Close", "Volume"])
    return validate_frame(frame, session)

def fetch_public(session):
    request = Request(SOURCE_URL, headers={"User-Agent": "GLABS-IHSG/1.0", "Accept": "text/html"})
    with urlopen(request, timeout=25) as response:
        content = response.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise ValueError("IHSG response too large")
    return parse_history(content.decode("utf-8"), session)

def fetch_ihsg(session, public_fetch=None, yahoo_fetch=None):
    """Bounded retries, then same-symbol Yahoo fallback; no stale publication."""
    public_fetch = public_fetch or fetch_public
    errors = []
    for attempt in range(2):
        try:
            frame = validate_frame(public_fetch(session), session)
            return frame, {"provider": "purbayasadewa.id", "url": SOURCE_URL,
                           "session": session, "bars": len(frame), "fallback": False}
        except Exception as error:
            errors.append(type(error).__name__)
            if attempt == 0:
                time.sleep(2)
    if yahoo_fetch is None:
        import yfinance as yf
        yahoo_fetch = lambda date: yf.download(
            "^JKSE", start=(pd.Timestamp(date)-pd.DateOffset(years=5)).strftime("%Y-%m-%d"),
            end=(pd.Timestamp(date)+pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
            auto_adjust=True, threads=False, progress=False, timeout=25)
    try:
        raw = yahoo_fetch(session)
        if raw is not None and isinstance(raw.columns, pd.MultiIndex):
            for level in range(raw.columns.nlevels):
                if "^JKSE" in raw.columns.get_level_values(level):
                    raw = raw.xs("^JKSE", axis=1, level=level)
                    break
            else:
                raise ValueError("Wrong Yahoo benchmark")
        frame = validate_frame(raw, session)
        return frame, {"provider": "Yahoo Finance", "symbol": "^JKSE", "session": session,
                       "bars": len(frame), "fallback": True, "primary_errors": errors}
    except Exception as error:
        raise ValueError("Both IHSG sources unavailable or stale; retain previous publication") from error
