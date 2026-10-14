"""Independent, completed-close global index card. Never imported by stock scoring."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import json
import math
from pathlib import Path

INDICES = [
    ("^GSPC", "S&P 500", "AS", "America/New_York"),
    ("^IXIC", "Nasdaq Composite", "AS", "America/New_York"),
    ("^DJI", "Dow Jones", "AS", "America/New_York"),
    ("^N225", "Nikkei 225", "Jepang", "Asia/Tokyo"),
    ("^HSI", "Hang Seng", "Hong Kong", "Asia/Hong_Kong"),
    ("000001.SS", "Shanghai Composite", "China", "Asia/Shanghai"),
    ("^GDAXI", "DAX P", "Jerman", "Europe/Berlin"),
    ("^FTSE", "FTSE 100", "Inggris", "Europe/London"),
]

def completed_snapshot(rows, now, exchange_timezone, regular_end=None):
    local_today = now.astimezone(ZoneInfo(exchange_timezone)).date()
    valid = {}
    for row in rows:
        day = datetime.strptime(row["date"], "%Y-%m-%d").date()
        close = row["close"]
        if isinstance(close, bool) or not isinstance(close, (int, float)) or not math.isfinite(close) or close <= 0:
            raise ValueError("Invalid index close")
        if day > local_today:
            raise ValueError("Future index session")
        confirmed_close = (isinstance(regular_end, (int, float)) and not isinstance(regular_end, bool)
                           and datetime.fromtimestamp(regular_end, ZoneInfo(exchange_timezone)).date() == day
                           and now.timestamp() >= regular_end)
        if day == local_today and not confirmed_close:
            continue  # Do not label the current intraday bar as a completed close.
        if row["date"] in valid:
            raise ValueError("Duplicate index date")
        valid[row["date"]] = float(close)
    clean = sorted(valid.items())
    if len(clean) < 2:
        raise ValueError("Insufficient completed-session history")
    previous, last = clean[-2:]
    change = last[1] - previous[1]
    return {"date": last[0], "close": last[1], "previous_date": previous[0],
            "previous_close": previous[1], "change": change,
            "change_pct": change / previous[1] * 100}

def build_feed(fetcher, previous=None, now=None):
    now = now or datetime.now(timezone.utc)
    old = {x["symbol"]: x for x in (previous or {}).get("indices", []) if isinstance(x, dict) and "symbol" in x}
    output, fresh = [], 0
    for symbol, name, region, tz in INDICES:
        base = {"symbol": symbol, "name": name, "region": region, "timezone": tz}
        try:
            rows, regular_end = fetcher(symbol)
            latest = completed_snapshot(rows, now, tz, regular_end)
            output.append({**base, **latest, "status": "ok", "fetched_at": now.isoformat()})
            fresh += 1
        except Exception as error:
            print(f"{symbol}: fetch unavailable ({type(error).__name__}: {error})")
            cached = old.get(symbol, {})
            try:
                latest = completed_snapshot(
                    [{"date": cached["previous_date"], "close": cached["previous_close"]},
                     {"date": cached["date"], "close": cached["close"]}], now, tz, now.timestamp())
                output.append({**base, **latest, "status": "cached", "fetched_at": cached.get("fetched_at")})
            except (ValueError, TypeError, KeyError):
                output.append({**base, "status": "unavailable"})
    if not fresh:
        raise ValueError("All providers failed; preserve the last valid published feed")
    return {"schema_version": 1, "source": "Yahoo Finance via yfinance",
            "generated_at": now.isoformat(), "fresh_count": fresh, "indices": output}

def run():
    import yfinance as yf
    def fetcher(symbol):
        ticker = yf.Ticker(symbol)
        frame = ticker.history(period="1mo", interval="1d", auto_adjust=False, actions=False, timeout=15)
        if frame.empty:
            raise ValueError("Empty history")
        rows = [{"date": index.strftime("%Y-%m-%d"), "close": float(row["Close"])}
                for index, row in frame.iterrows()]
        metadata = ticker.history_metadata or {}
        regular = metadata.get("currentTradingPeriod", {}).get("regular", {})
        return rows, regular.get("end")
    path = Path("web/global_indices_data.json")
    try:
        previous = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        previous = None
    feed = build_feed(fetcher, previous)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(feed, allow_nan=False, separators=(",", ":")) + "\n", encoding="utf-8")
    temp.replace(path)
    print(f"Global index card: {feed['fresh_count']}/8 fetched; screening untouched")

if __name__ == "__main__":
    run()
