"""Transparent GLABS relative rotation; NOT proprietary JdK indicators.

All windows are trading sessions, including Weekly=20D and Swing=60D.
This is descriptive relative performance, NOT a validated buy/sell strategy.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

SECTORS = {
    "IDXENERGY": "Energi",
    "IDXBASIC": "Barang Baku",
    "IDXINDUST": "Perindustrian",
    "IDXNONCYC": "Barang Konsumen Primer",
    "IDXCYCLIC": "Barang Konsumen Non-Primer",
    "IDXHEALTH": "Kesehatan",
    "IDXFINANCE": "Keuangan",
    "IDXPROPERT": "Properti & Real Estat",
    "IDXTECHNO": "Teknologi",
    "IDXINFRA": "Infrastruktur",
    "IDXTRANS": "Transportasi & Logistik"
}
WINDOWS = {"daily": (5, 3), "weekly": (20, 5), "swing": (60, 10)}
SCHEMA_VERSION = 1
HISTORY = 100
TAIL = 20
SMOOTH = 3
SOURCE = "https://www.idx.co.id/primary/ListedCompany/GetCompanyProfiles"


def quadrant(strength, momentum):
    # Exactly on a boundary has no directional classification.
    if abs(strength - 100) < 1e-8 or abs(momentum - 100) < 1e-8:
        return "Neutral"
    if strength > 100:
        return "Leading" if momentum > 100 else "Weakening"
    return "Improving" if momentum > 100 else "Lagging"


def rotation_series(close, benchmark, lookback, momentum_window):
    ratio = close / benchmark
    strength = (100 * ratio / ratio.shift(lookback)).rolling(
        SMOOTH, min_periods=SMOOTH
    ).mean()
    momentum = 100 * strength / strength.shift(momentum_window)
    return pd.DataFrame({"strength": strength, "momentum": momentum})


def entity(symbol, name, close, benchmark, style):
    lookback, momentum_window = WINDOWS[style]
    trajectory = rotation_series(close, benchmark, lookback, momentum_window)
    trajectory = trajectory.replace([np.inf, -np.inf], np.nan).dropna()
    if len(trajectory) < 2 or trajectory.index[-1] != benchmark.index[-1]:
        return None
    last, prev = trajectory.iloc[-1], trajectory.iloc[-2]
    now = quadrant(last.strength, last.momentum)
    before = quadrant(prev.strength, prev.momentum)
    dx, dy = last.strength - prev.strength, last.momentum - prev.momentum
    if now != before:
        phase = f"{before} → {now}"
    elif dx > 0 and dy > 0:
        phase = "Menguat"
    elif dx < 0 and dy < 0:
        phase = "Melemah"
    elif dx > 0:
        phase = "Kekuatan naik · momentum turun"
    elif dy > 0:
        phase = "Momentum pulih · kekuatan turun"
    else:
        phase = "Stabil"
    return {
        "symbol": symbol, "name": name, "quadrant": now,
        "strength": round(float(last.strength), 6),
        "momentum": round(float(last.momentum), 6),
        "phase": phase,
        "delta_strength": round(float(dx), 6),
        "delta_momentum": round(float(dy), 6),
        "return_pct": round(float((close.iloc[-1] / close.iloc[-lookback-1] - 1) * 100), 4),
        "relative_return_pct": round(float(
            ((close.iloc[-1] / close.iloc[-lookback-1]) /
             (benchmark.iloc[-1] / benchmark.iloc[-lookback-1]) - 1) * 100
        ), 4),
        "last_close": round(float(close.iloc[-1]), 4),
        "date": benchmark.index[-1].strftime("%Y-%m-%d"),
        "trail": [
            {"date": date.strftime("%Y-%m-%d"),
             "strength": round(float(row.strength), 6),
             "momentum": round(float(row.momentum), 6)}
            for date, row in trajectory.tail(TAIL).iterrows()
        ],
        "history": [
            {"date": date.strftime("%Y-%m-%d"), "close": round(float(value), 6),
             "benchmark": round(float(benchmark.loc[date]), 6)}
            for date, value in close.items()
        ],
    }


def price_history(close, benchmark):
    """Export actual matching sessions only; no padding and no future dates."""
    return [{"date": date.strftime("%Y-%m-%d"), "close": round(float(value), 6),
             "benchmark": round(float(benchmark.loc[date]), 6)}
            for date, value in close.items()]


def screening_session(dashboard):
    """Use the last published market session, NEVER today's generation date."""
    session = dashboard.get("market_data_date")
    if not session:
        raise ValueError("Dashboard has no last screened market session")
    parsed = pd.Timestamp(session)
    if pd.isna(parsed) or parsed.weekday() >= 5:
        raise ValueError("Screening session must be Monday-Friday")
    requested = dashboard.get("screening_session_date")
    if requested and requested != session:
        raise ValueError("Dashboard screening and market dates do not match")
    return session


def build_rotation(prices, benchmark, classification, session):
    if pd.Timestamp(session).weekday() >= 5:
        raise ValueError("Rotation cannot publish a Saturday/Sunday session")
    benchmark = pd.to_numeric(benchmark, errors="coerce")
    benchmark.index = pd.DatetimeIndex(benchmark.index).tz_localize(None).normalize()
    benchmark = benchmark[~benchmark.index.duplicated(keep="last")].sort_index()
    benchmark = benchmark.loc[(benchmark.index <= pd.Timestamp(session)) & (benchmark.index.weekday < 5)]
    display_benchmark = benchmark.where(np.isfinite(benchmark) & (benchmark > 0)).dropna().tail(300)
    benchmark = display_benchmark.tail(HISTORY)
    if len(benchmark) < HISTORY or benchmark.index[-1].strftime("%Y-%m-%d") != session:
        raise ValueError("IHSG stale or fewer than 100 completed trading sessions")
    clean, display_prices, excluded = {}, {}, []
    for ticker, series in prices.items():
        if ticker not in classification:
            excluded.append({"symbol": ticker, "reason": "Klasifikasi sektor belum terverifikasi"})
            continue
        series = pd.to_numeric(series, errors="coerce").copy()
        series.index = pd.DatetimeIndex(series.index).tz_localize(None).normalize()
        series = series[~series.index.duplicated(keep="last")]
        display_series = series.reindex(display_benchmark.index)
        series = series.reindex(benchmark.index)
        if series.isna().any() or (series <= 0).any() or not np.isfinite(series).all():
            excluded.append({"symbol": ticker, "reason": "Harga tidak lengkap dalam 100 sesi IHSG terakhir"})
            continue
        clean[ticker] = series
        invalid = display_series.isna() | (display_series <= 0) | ~np.isfinite(display_series)
        bad_dates = display_series.index[invalid]
        # Retain only a contiguous valid suffix; never bridge an internal missing session.
        display_prices[ticker] = (display_series.loc[display_series.index > bad_dates[-1]]
                                  if len(bad_dates) else display_series)

    modes = {}
    for style in WINDOWS:
        stocks, sector_rows = [], []
        for code, name in SECTORS.items():
            members = sorted(t for t in clean if classification[t]["sector"] == code)
            rows = []
            for ticker in members:
                row = entity(ticker, classification[ticker]["name"], clean[ticker], benchmark, style)
                if row:
                    row["sector"] = code
                    row["chart_history"] = price_history(display_prices[ticker], display_benchmark)

                    stocks.append(row)
                    rows.append(row)
            if len(members) < 3:
                sector_rows.append({"symbol": code, "name": name, "status": "insufficient_members",
                                    "members": len(members)})
                continue
            # Daily-rebalanced equal weights, fixed current membership, NO missing-data fill.
            returns = pd.concat([clean[t].pct_change(fill_method=None) for t in members], axis=1)
            basket = 100 * (1 + returns.iloc[1:].mean(axis=1)).cumprod()
            basket = pd.concat([pd.Series([100.0], index=benchmark.index[:1]), basket])
            row = entity(code, name, basket, benchmark, style)
            common_start = max(display_prices[t].index[0] for t in members)
            display_index = display_benchmark.index[display_benchmark.index >= common_start]
            display_returns = pd.concat([display_prices[t].reindex(display_index).pct_change(fill_method=None)
                                         for t in members], axis=1)
            display_basket = 100 * (1 + display_returns.iloc[1:].mean(axis=1)).cumprod()
            display_basket = pd.concat([pd.Series([100.0], index=display_index[:1]), display_basket])
            row["chart_history"] = price_history(display_basket, display_benchmark)
            row.update({"status": "ok", "members": len(members),
                        "breadth_pct": round(sum(r["relative_return_pct"] > 0 for r in rows) /
                                             len(rows) * 100, 2)})
            sector_rows.append(row)
        order = {"Leading": 0, "Improving": 1, "Weakening": 2, "Lagging": 3, "Neutral": 4}
        def rank(row):
            return (order.get(row.get("quadrant"), 5), -row.get("momentum", 0),
                    -row.get("strength", 0), row["symbol"])
        modes[style] = {
            "lookback": WINDOWS[style][0], "momentum_window": WINDOWS[style][1],
            "sectors": sorted(sector_rows, key=rank), "stocks": sorted(stocks, key=rank),
        }
    return {
        "schema_version": SCHEMA_VERSION, "status": "ok",
        "market_data_date": session,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "benchmark": "IHSG (^JKSE)",
        "coverage": {"requested": len(prices), "valid": len(clean), "excluded": excluded},
        "methodology": {
            "name": "GLABS Relative Rotation",
            "strength": "S = SMA3(100 × (harga/IHSG)t ÷ (harga/IHSG)t-L)",
            "momentum": "M = 100 × S(t) ÷ S(t-m)",
            "sector": "Basket saham GLABS: equal-weight return harian, rebalance harian; bukan indeks IDX resmi",
            "history": "Minimal 100 sesi IHSG lengkap; chart memakai suffix lengkap yang tersedia, maksimal 300 sesi; tanpa forward fill; harga adjusted",
            "limitation": "Konstituen saat ini, bukan point-in-time; bukan backtest atau sinyal beli/jual",
            "note": "Bukan JdK RS-Ratio / RS-Momentum proprietary",
        },
        "modes": modes,
    }


def load_classification(path=Path("data/idx_sector_classification.json")):
    import requests
    cache = json.loads(path.read_text(encoding="utf-8"))
    age = (datetime.now(timezone.utc).date() -
           datetime.fromisoformat(cache["as_of"]).date()).days
    cache["refresh_status"] = "cached"
    if age < 7:
        return cache
    try:
        response = requests.get(SOURCE, params={"start": 0, "length": 9999, "language": "id-id"},
                                timeout=20, headers={"Accept": "application/json"})
        response.raise_for_status()
        rows = response.json()["data"]
        reverse = {name: code for code, name in SECTORS.items()}
        companies = {
            row["KodeEmiten"]: {"name": row["NamaEmiten"], "sector": reverse[row["Sektor"]]}
            for row in rows if row.get("EfekEmiten_Saham") and row.get("Sektor") in reverse
        }
        if len(companies) < len(cache["companies"]) * .95:
            raise ValueError("IDX classification coverage regression")
        cache.update({"companies": companies, "as_of": datetime.now(timezone.utc).date().isoformat(),
                      "refresh_status": "live", "source_url": SOURCE})
        path.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (requests.RequestException, KeyError, ValueError, TypeError) as error:
        cache["refresh_status"] = "cached_refresh_failed"
        cache["refresh_error"] = str(error)[:180]
        print(f"[rotation] Official classification refresh failed; using dated cache: {error}")
    return cache


def run():
    from data.ihsg_fetcher import fetch_ihsg
    source = Path("web/dashboard_data.json").read_bytes()
    dashboard = json.loads(source)
    session = screening_session(dashboard)
    prices = {}
    for stock in dashboard["watchlist"]:
        history = stock.get("price_history", [])
        prices[stock["ticker"]] = pd.Series(
            [bar.get("close") for bar in history],
            index=pd.to_datetime([bar["date"] for bar in history])
        )
    ihsg, ihsg_source = fetch_ihsg(session)
    classification = load_classification()
    report = build_rotation(prices, ihsg["Close"], classification["companies"], session)
    report["ihsg_source"] = ihsg_source
    report["dashboard_sha256"] = hashlib.sha256(source).hexdigest()
    report["classification"] = {k: v for k, v in classification.items() if k != "companies"}
    if report["coverage"]["valid"] < max(3, int(len(prices) * .5)):
        raise ValueError("Less than 50% of dashboard eligible for rotation; publication refused")
    # This adds an independent adjustable history contract; existing screener/radar modes remain unchanged.
    from data.rotation_history import run as fetch_rotation_history
    fetch_rotation_history(classification["companies"], SECTORS, source, dashboard, ihsg_frame=ihsg, ihsg_source=ihsg_source)
    report["history_schema_version"] = 1
    output = Path("web/sector_rotation_data.json")
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, allow_nan=False,
                                   separators=(",", ":")), encoding="utf-8")
    temporary.replace(output)
    print(f"Rotation published: {report['coverage']['valid']}/{len(prices)}, session={session}")


if __name__ == "__main__":
    run()
