"""Rotation history feed for personal research; Yahoo is not an SLA-backed feed.
No credentials, no invented benchmark, no OHLCV-volume gate for index closes.
Cache stocks off-repo; persist the small index archive and publish audited history.
"""
from __future__ import annotations
import gzip
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd

VERSION = 1
DISPLAY_ROWS = 600  # > 109 weeks needed by the maximum supported adjustment.
CACHE_ROWS = 1300
BENCHMARKS = {
    "COMPOSITE": ("IHSG (Composite)", "^JKSE"),
    "LQ45": ("LQ45", "^JKLQ45"),
    "IDX30": ("IDX30", "IDX30.JK"),
    "IDX80": ("IDX80", "IDX80.JK"),
    "KOMPAS100": ("Kompas100", "KOMPAS100.JK"),
    "BISNIS-27": ("Bisnis27", "BISNIS-27.JK"),
    "MNC36": ("MNC36", "MNC36.JK"),
    "IDXESGL": ("IDX ESG Leaders", "IDXESGL.JK"),
}


def clean_close(frame, symbol=None):
    """Zero-volume indices are valid; missing/nonpositive closes are not."""
    if frame is None or frame.empty:
        return pd.Series(dtype=float)
    if isinstance(frame.columns, pd.MultiIndex):
        for level in range(frame.columns.nlevels):
            if symbol in frame.columns.get_level_values(level):
                frame = frame.xs(symbol, axis=1, level=level)
                break
        else:
            return pd.Series(dtype=float)
    if "Close" not in frame:
        return pd.Series(dtype=float)
    close = frame["Close"]
    if isinstance(close, pd.DataFrame):
        if close.shape[1] != 1:
            return pd.Series(dtype=float)
        close = close.iloc[:, 0]
    close = pd.to_numeric(close, errors="coerce").copy()
    close.index = pd.DatetimeIndex(close.index).tz_localize(None).normalize()
    close = close[~close.index.duplicated(keep="last")].sort_index()
    return close.where(np.isfinite(close) & (close > 0)).dropna().loc[lambda x: x.index.weekday < 5]


def from_rows(rows):
    return pd.Series([r[1] for r in rows], index=pd.to_datetime([r[0] for r in rows]), dtype=float)


def to_rows(close, session, limit=CACHE_ROWS):
    if close.empty:
        return []
    close = close.loc[close.index <= pd.Timestamp(session)].tail(limit)
    return [[d.strftime("%Y-%m-%d"), round(float(v), 8)] for d, v in close.items()]


def merge_history(old, fresh, session, adjusted=False):
    """Do not splice incompatible dividend/split adjustment bases."""
    old = old.loc[old.index <= pd.Timestamp(session)] if len(old) else from_rows([])
    fresh = fresh.loc[fresh.index <= pd.Timestamp(session)] if len(fresh) else from_rows([])
    common = old.index.intersection(fresh.index)
    changed = bool(adjusted and len(common) and
                   not np.allclose(old.loc[common], fresh.loc[common], rtol=1e-5, atol=1e-6))
    merged = pd.concat([old, fresh])
    merged = merged[~merged.index.duplicated(keep="last")].sort_index().tail(CACHE_ROWS)
    return merged, changed


def download(symbols, session, start=None):
    import yfinance as yf
    result = {}
    for offset in range(0, len(symbols), 20):
        chunk = symbols[offset:offset+20]
        for attempt in range(2):
            try:
                options = {"start": start} if start else {"start": (pd.Timestamp(session)-pd.DateOffset(years=5)).strftime("%Y-%m-%d")}
                raw = yf.download(chunk, end=(pd.Timestamp(session)+pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
                                  interval="1d", group_by="ticker", auto_adjust=True,
                                  threads=False, progress=False, timeout=20, **options)
                for symbol in chunk:
                    close = clean_close(raw, symbol)
                    if len(close):
                        result[symbol] = close.loc[close.index <= pd.Timestamp(session)]
                if all(s in result for s in chunk):
                    break
            except Exception as error:
                # Never log a request URL or any credential.
                print(f"[rotation-history] Batch failed: {type(error).__name__}")
            if attempt == 0:
                time.sleep(3)
        if offset+20 < len(symbols):
            time.sleep(2)
    return result


def aligned_history(close, benchmark):
    """Only the complete suffix on real benchmark sessions, never forward-fill."""
    matched = close.reindex(benchmark.index)
    invalid = matched.isna() | (matched <= 0) | ~np.isfinite(matched)
    if invalid.any():
        matched = matched.loc[matched.index > matched.index[invalid][-1]]
    return [{"date": d.strftime("%Y-%m-%d"), "close": round(float(v), 8),
             "benchmark": round(float(benchmark.loc[d]), 8)} for d, v in matched.items()]


def basket_history(prices, members, benchmark):
    """Daily-rebalanced current-universe basket, min 3 observed return pairs per day.
    Membership changes with history availability; NOT an official sector index.
    """
    if len(members) < 3:
        return []
    closes = pd.concat([prices[t].reindex(benchmark.index) for t in members], axis=1)
    returns = closes.pct_change(fill_method=None)
    daily = returns.mean(axis=1).where(returns.count(axis=1) >= 3)
    invalid = daily.iloc[1:].isna()
    start = (daily.index.get_loc(daily.iloc[1:].index[invalid][-1])+1 if invalid.any() else 1)
    if len(daily)-start < 2:
        return []
    # Include the observed session preceding the first eligible return.
    values = 100*(1+daily.iloc[start:]).cumprod()
    values = pd.concat([pd.Series([100.0], index=benchmark.index[start-1:start]), values])
    return aligned_history(values, benchmark.loc[values.index])


def read_json(path):
    try:
        if str(path).endswith(".gz"):
            with gzip.open(path, "rt", encoding="utf-8") as f:
                return json.load(f)
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def build_views(stock_prices, index_prices, classification, sectors, session, health):
    """Keep original screener/radar modes separate from adjustable history views."""
    index_prices = {k: v.loc[v.index <= pd.Timestamp(session)].tail(DISPLAY_ROWS)
                    for k, v in index_prices.items()}
    benchmarks = {}
    for code, (name, symbol) in BENCHMARKS.items():
        series = index_prices.get(code, pd.Series(dtype=float))
        fresh = bool(len(series) and series.index[-1].strftime("%Y-%m-%d") == session)
        ready = fresh and len(series) >= 100
        benchmarks[code] = {"name": name, "symbol": symbol, "status": "ok" if ready else "insufficient_history" if fresh else "stale_or_unavailable",
                            "bars": len(series), "history": to_rows(series, session, DISPLAY_ROWS),
                            "reason": "" if ready else f"Riwayat terverifikasi {len(series)} sesi; minimum 100 dan harus berakhir pada screening terakhir"}
    views = {}
    for code, info in benchmarks.items():
        if info["status"] != "ok":
            continue
        benchmark = index_prices[code]
        stocks = []
        for ticker, close in stock_prices.items():
            if ticker not in classification:
                continue
            history = aligned_history(close, benchmark)
            if len(history) < 2 or history[-1]["date"] != session:
                continue
            stocks.append({"symbol": ticker, "name": classification[ticker]["name"],
                           "sector": classification[ticker]["sector"], "chart_history": history,
                           "source_kind": "adjusted_stock"})
        sector_rows = []
        for sector, name in sectors.items():
            official = index_prices.get(sector, pd.Series(dtype=float))
            hist = aligned_history(official, benchmark)
            official_ready = len(hist) >= 100 and hist[-1]["date"] == session
            if not official_ready:
                members = [t for t in stock_prices if t in classification and classification[t]["sector"] == sector]
                hist = basket_history(stock_prices, members, benchmark)
            else:
                members = [t for t in stock_prices if t in classification and classification[t]["sector"] == sector]
            sector_rows.append({"symbol": sector, "name": name,
                                "status": "ok" if len(hist) >= 2 else "insufficient_history",
                                "members": len(members), "chart_history": hist,
                                "source_kind": "official_index" if official_ready else "glabs_history_basket"})
        views[code] = {"stocks": stocks, "sectors": sector_rows}
    if "COMPOSITE" not in views:
        raise ValueError("Fresh complete IHSG history is required; last good publication retained")
    shared_stocks = [{"symbol": t, "name": classification[t]["name"], "sector": classification[t]["sector"],
                      "prices": to_rows(s, session, DISPLAY_ROWS)} for t,s in stock_prices.items() if t in classification]
    for view in views.values():
        view["stocks_count"] = len(view.pop("stocks"))
    return {"schema_version": VERSION, "status": "ok", "market_data_date": session, "stocks": shared_stocks,
            "generated_at": datetime.now(timezone.utc).isoformat(), "benchmarks": benchmarks,
            "views": views, "health": health,
            "method": {"source": "IHSG: purbayasadewa.id with same-symbol Yahoo fallback; other prices: Yahoo Finance; personal research",
                       "price_basis": "Stocks adjusted for dividends/splits; index closing levels",
                       "basket": "Equal-weight observed daily returns, minimum 3 valid return pairs; daily eligible membership changes. Current classification, NOT point-in-time or an official index.",
                       "retention": "Chart: up to 600 real sessions; bootstrap: 5 years when available",
                       "no_fill": "No forward-fill, synthetic IPO history, ETF substitution, or fallback to a different benchmark"}}


def run(classification, sectors, dashboard_bytes, dashboard, ihsg_frame=None, ihsg_source=None):
    session = dashboard["market_data_date"]
    if pd.Timestamp(session).weekday() >= 5:
        raise ValueError("Cannot fetch a weekend screening session")
    cache_path = Path(".cache/rotation_stock_history.json.gz")
    index_path = Path("data/rotation_index_history.json")
    stock_cache = read_json(cache_path)
    # Published views can seed a lost Actions cache. Rebase all prices if full-refresh metadata is missing.
    if not stock_cache.get("stocks"):
        previous = read_json(Path("web/rotation_history_data.json"))
        stock_cache["stocks"] = {r["symbol"]: r["prices"] for r in previous.get("stocks", [])}
        stock_cache["refresh_dates"] = previous.get("health", {}).get("refresh_dates", {})
    tickers = sorted({s["ticker"] for s in dashboard["watchlist"]})
    old = {t: from_rows(stock_cache.get("stocks", {}).get(t, [])) for t in tickers}
    refresh_dates = stock_cache.get("refresh_dates", {})
    def needs_full(t):
        date = refresh_dates.get(t)
        return not date or not len(old[t]) or (pd.Timestamp(session)-pd.Timestamp(date)).days >= 7
    bootstrap = [t for t in tickers if needs_full(t)]
    incremental = [t for t in tickers if t not in bootstrap and
                   (not len(old[t]) or old[t].index[-1].strftime("%Y-%m-%d") != session)]
    fetched = download([t+".JK" for t in bootstrap], session)
    fetched.update(download([t+".JK" for t in incremental], session,
                            (pd.Timestamp(session)-pd.Timedelta(days=45)).strftime("%Y-%m-%d")))
    prices, status, rebase = {}, {}, []
    for t in tickers:
        fresh = fetched.get(t+".JK", pd.Series(dtype=float))
        if t in bootstrap and len(fresh):
            # A full download replaces the entire adjustment basis, not just overlapping dates.
            merged = fresh.tail(CACHE_ROWS)
            changed = False
        else:
            merged, changed = merge_history(old[t], fresh, session, adjusted=True)
        if changed:
            rebase.append(t)
        prices[t] = merged
        status[t] = "ok" if len(merged) and merged.index[-1].strftime("%Y-%m-%d") == session else "stale_or_unavailable"
    if rebase:
        replacements = download([t+".JK" for t in rebase], session)
        for t in rebase:
            fresh = replacements.get(t+".JK")
            # A failed adjustment rebase must never mix old and new bases.
            prices[t] = fresh.tail(CACHE_ROWS) if fresh is not None else old[t]
            status[t] = ("ok" if fresh is not None and len(fresh) and
                         fresh.index[-1].strftime("%Y-%m-%d") == session else "adjustment_rebase_failed")
    index_cache = read_json(index_path)
    registry = {k: v[1] for k, v in BENCHMARKS.items()}
    registry.update({code: code+".JK" for code in sectors})
    if ihsg_frame is None:
        from data.ihsg_fetcher import fetch_ihsg
        ihsg_frame, ihsg_source = fetch_ihsg(session)
    index_raw = download([s for s in registry.values() if s != "^JKSE"], session)
    index_raw["^JKSE"] = clean_close(ihsg_frame)
    indices = {}
    for code, symbol in registry.items():
        merged, _ = merge_history(from_rows(index_cache.get("indices", {}).get(code, [])),
                                  index_raw.get(symbol, pd.Series(dtype=float)), session)
        indices[code] = merged
    for t in bootstrap:
        fresh = fetched.get(t+".JK", pd.Series(dtype=float))
        if len(fresh) and fresh.index[-1].strftime("%Y-%m-%d") == session:
            refresh_dates[t] = session
    for t in rebase:
        if status[t] == "ok":
            refresh_dates[t] = session
    health = {"ihsg_source": ihsg_source, "refresh_dates": refresh_dates, "stocks_requested": len(tickers), "stocks_fresh": sum(v=="ok" for v in status.values()),
              "excluded": [{"symbol": t, "reason": v} for t, v in status.items() if v != "ok"],
              "adjustment_rebases": rebase, "automatic_retry": True,
              "index_archive": "Actual daily observations accumulated; a latest quote is not historical coverage"}
    if health["stocks_fresh"] < max(3, len(tickers)*.5):
        raise ValueError("History coverage below 50%; retain last valid publication")
    views = build_views({t: prices[t] for t in prices if status[t]=="ok"},
                        indices, classification, sectors, session, health)
    views["dashboard_sha256"] = hashlib.sha256(dashboard_bytes).hexdigest()
    # Persist only after all publication validations pass.
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache = {"schema_version": VERSION, "refresh_dates": refresh_dates,
             "stocks": {t: to_rows(s, session) for t, s in prices.items()}}
    with gzip.open(cache_path, "wt", encoding="utf-8") as f:
        json.dump(cache, f, separators=(",", ":"), allow_nan=False)
    index_path.write_text(json.dumps({"schema_version": VERSION, "indices": {k: to_rows(v, session) for k,v in indices.items()}},
                                    separators=(",", ":"), allow_nan=False)+"\n", encoding="utf-8")
    output = Path("web/rotation_history_data.json")
    temp = output.with_suffix(".tmp")
    temp.write_text(json.dumps(views, ensure_ascii=False, allow_nan=False, separators=(",", ":"))+"\n", encoding="utf-8")
    temp.replace(output)
    print(f"Rotation history: {health['stocks_fresh']}/{len(tickers)} fresh; ready benchmarks={list(views['views'])}; session={session}")
    return views
