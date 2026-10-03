"""Radar compares published sessions, not wall-clock dates or inferred history."""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path

STYLES = {"daily": ("signal_daily", "vwap_fast", "5D"),
          "weekly": ("signal", "vwap_medium", "20D"),
          "swing": ("signal_swing", "vwap_swing", "60D")}
ALLOWED = {"BUY", "HOLD", "WAIT", "REDUCE", "EXIT", "AVOID"}
LABELS = {"beli": "Beli", "pantau": "Pantau", "jual": "Jual"}
VERSION = 1


def valid_session(value):
    if not isinstance(value, str):
        raise ValueError("Missing market session")
    parsed = date.fromisoformat(value)
    if parsed.weekday() >= 5:
        raise ValueError("Weekend is not a screened market session")
    return value


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def snapshot(dashboard, rotation=None):
    session = valid_session(dashboard.get("market_data_date"))
    requested = dashboard.get("screening_session_date")
    if requested and requested != session:
        raise ValueError("Screening and market dates disagree")
    rows = {}
    for stock in dashboard.get("watchlist", []):
        if stock.get("last_price_date") != session:
            continue  # Stale individual stocks cannot produce a 'new' signal.
        analysis = stock.get("vwap_analysis") or {}
        valid_vwap = analysis.get("status") == "ok" and analysis.get("signal") in ALLOWED
        rows[stock["ticker"]] = {
            "price": stock.get("last_close"),
            "signals": {s: stock.get(keys[0]) if stock.get(keys[0]) in LABELS else None
                        for s, keys in STYLES.items()},
            "focus": {s: {
                "position": (analysis.get(keys[1]) or {}).get("position"),
                "slope": (analysis.get(keys[1]) or {}).get("slope_pct"),
            } if valid_vwap else None for s, keys in STYLES.items()},
            "full_vwap": analysis.get("signal") if valid_vwap else None,
            "settings": digest(analysis.get("settings") or {}) if valid_vwap else None,
        }
    rot = {s: {} for s in STYLES}
    rotation_method = None
    if rotation and rotation.get("market_data_date") == session and rotation.get("status") == "ok":
        rotation_method = digest(rotation.get("methodology") or {})
        for s in STYLES:
            rot[s] = {r["symbol"]: {"quadrant": r["quadrant"], "sector": r.get("sector")}
                      for r in rotation.get("modes", {}).get(s, {}).get("stocks", [])
                      if r.get("date") == session}
    return {"session": session, "contract": dashboard.get("analysis_contract"),
            "rows": rows, "rotation": rot, "rotation_method": rotation_method}


def focus_bullish(value):
    if not value or value.get("position") not in {"above", "below", "at", "equal"}:
        return None
    slope = value.get("slope")
    if not isinstance(slope, (int, float)):
        return None
    return value["position"] == "above" and slope > 0


def compare(current, previous):
    if previous and previous["session"] >= current["session"]:
        raise ValueError("Radar requires two distinct chronological sessions")
    modes = {}
    common_contract = bool(previous and current.get("contract") and
                           current["contract"] == previous.get("contract"))
    previous_rows = previous.get("rows", {}) if previous else {}
    common = set(current["rows"]) & set(previous_rows)
    new = sorted(set(current["rows"]) - set(previous_rows))
    missing = sorted(set(previous_rows) - set(current["rows"]))
    def event(ticker, kind, before, after, title, meaning, priority, group):
        return {"ticker": ticker, "kind": kind, "before": before, "after": after,
                "title": title, "meaning": meaning, "priority": priority, "group": group,
                "price": current["rows"][ticker].get("price")}
    for style in STYLES:
        events = []
        rotation_ready = bool(previous and current.get("rotation_method") and
                              current["rotation_method"] == previous.get("rotation_method"))
        compared = 0
        for ticker in sorted(common):
            now, old = current["rows"][ticker], previous_rows[ticker]
            if common_contract:
                a, b = old["signals"].get(style), now["signals"].get(style)
                if a in LABELS and b in LABELS:
                    compared += 1
                    if a != b:
                        if b == "jual":
                            title, meaning, priority, group = (
                                "Sinyal komposit melemah",
                                "Skor gabungan berubah ke Jual. Evaluasi risiko; ini bukan perintah menjual otomatis.",
                                1, "risk")
                        elif b == "beli":
                            title, meaning, priority, group = (
                                "Sinyal komposit membaik",
                                "Skor gabungan berubah ke Beli. Kandidat untuk diperiksa, bukan jaminan entry.",
                                3, "opportunity")
                        else:
                            title, meaning, priority, group = (
                                "Kembali ke pantauan",
                                "Sinyal komposit berubah ke Pantau; belum memberi konfirmasi arah yang kuat.",
                                6, "watch")
                        events.append(event(ticker,"composite",LABELS[a],LABELS[b],
                                            title,meaning,priority,group))
                a, b = focus_bullish(old["focus"].get(style)), focus_bullish(now["focus"].get(style))
                if (a is not None and b is not None and a != b and
                        now.get("settings") == old.get("settings")):
                    horizon = STYLES[style][2]
                    events.append(event(ticker,"vwap_focus",
                        "Di atas & menanjak" if a else "Belum di atas & menanjak",
                        "Di atas & menanjak" if b else "Tidak lagi di atas & menanjak",
                        f"VWAP {horizon} {'membaik' if b else 'melemah'}",
                        (f"Harga kini di atas VWAP {horizon} dan garisnya menanjak. "
                         "Ini perubahan kondisi, bukan sinyal BUY."
                         if b else f"Syarat harga di atas VWAP {horizon} dengan slope positif tidak lagi terpenuhi."),
                        4 if b else 2,"opportunity" if b else "risk"))
            if rotation_ready:
                a = previous["rotation"].get(style, {}).get(ticker)
                b = current["rotation"].get(style, {}).get(ticker)
                if a and b and a.get("sector") == b.get("sector"):
                    if a["quadrant"] != "Leading" and b["quadrant"] == "Leading":
                        events.append(event(ticker,"rotation",a["quadrant"],"Leading",
                            "Baru masuk Leading",
                            "Kekuatan dan momentum relatif sekarang di atas batas 100 terhadap IHSG; bukan bukti aliran dana.",
                            4,"opportunity"))
                    elif a["quadrant"] == "Leading" and b["quadrant"] != "Leading":
                        events.append(event(ticker,"rotation","Leading",b["quadrant"],
                            "Keluar dari Leading",
                            "Kepemimpinan relatif melemah. Periksa kembali struktur dan risiko saham.",
                            2,"risk"))
        modes[style] = {"events": sorted(events,key=lambda e:(e["priority"],e["ticker"],e["kind"])),
                        "compared": compared, "rotation_baseline_available": rotation_ready,
                        "counts": {g: len({e["ticker"] for e in events if e["group"] == g})
                                   for g in ("risk","opportunity","watch")}}
    full = []
    if common_contract:
        meanings = {
            "BUY": ("Trigger BUY baru", "Full VWAP mendeteksi trigger entry baru. Periksa konfirmasi, likuiditas dan risiko sebelum bertindak.",3,"opportunity"),
            "HOLD": ("Struktur kembali sehat", "Full VWAP berubah ke HOLD: struktur masih mendukung, tetapi bukan trigger entry baru.",5,"watch"),
            "WAIT": ("Konfirmasi belum lengkap", "Full VWAP berubah ke WAIT. Tunggu setup lebih jelas.",6,"watch"),
            "REDUCE": ("Bullish mulai melemah", "Full VWAP berubah ke REDUCE. Jika memiliki posisi, evaluasi risikonya; bukan instruksi otomatis.",1,"risk"),
            "EXIT": ("Struktur bullish rusak", "Full VWAP berubah ke EXIT. Jika memiliki posisi, periksa invalidasi dan rencana keluar.",0,"risk"),
            "AVOID": ("Kondisi bearish", "Full VWAP berubah ke AVOID. Hindari menganggapnya sebagai sinyal short sell.",2,"risk"),
        }
        for ticker in sorted(common):
            old, now = previous_rows[ticker], current["rows"][ticker]
            a, b = old.get("full_vwap"), now.get("full_vwap")
            if a in ALLOWED and b in ALLOWED and a != b and old.get("settings") == now.get("settings"):
                title, meaning, priority, group = meanings[b]
                full.append(event(ticker,"full_vwap",a,b,title,meaning,priority,group))
    full.sort(key=lambda e:(e["priority"],e["ticker"]))
    return {"schema_version": VERSION, "status": "ok", "market_data_date": current["session"],
            "previous_session": previous["session"] if previous else None,
            "comparison_status": "ready" if common_contract else "baseline_unavailable",
            "comparison_note": ("Comparing published sessions with the same analysis contract"
                                if common_contract else "Previous compatible screening is unavailable; no transitions invented"),
            "coverage": {"current":len(current["rows"]),"common":len(common),
                         "new_tickers":new,"missing_tickers":missing},
            "modes": modes, "full_vwap_events": full,
            "generated_at":datetime.now(timezone.utc).isoformat(),
            "methodology": "Previous distinct published weekday session; repeated same-session runs retain the baseline. Risk-first ordering, not expected profit ranking."}


def advance(current, state):
    latest, previous = state.get("latest"), state.get("previous")
    if latest and latest["session"] > current["session"]:
        raise ValueError("Cannot roll radar back to an older session")
    if latest and latest["session"] < current["session"]:
        previous = latest
    if previous and previous["session"] >= current["session"]:
        raise ValueError("Baseline must be an earlier distinct session")
    return {"schema_version":VERSION, "latest":current, "previous":previous}


def historical_dashboard(current_session):
    # Public repository history only, no fabricated earlier signals or chart reconstruction.
    commits = subprocess.check_output(
        ["git","log","-30","--format=%H","--","web/dashboard_data.json"],text=True).splitlines()
    for commit in commits:
        try:
            raw = subprocess.check_output(["git","show",f"{commit}:web/dashboard_data.json"],
                                          stderr=subprocess.DEVNULL)
            dashboard = json.loads(raw)
            old_session = valid_session(dashboard.get("market_data_date"))
            if old_session < current_session:
                return snapshot(dashboard)
        except (subprocess.CalledProcessError, ValueError, KeyError, TypeError):
            continue
    return None


def atomic_json(path, value):
    path = Path(path)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(",",":")),
                    encoding="utf-8")
    temp.replace(path)


def run():
    raw = Path("web/dashboard_data.json").read_bytes()
    dashboard = json.loads(raw)
    rotation_path = Path("web/sector_rotation_data.json")
    rotation = json.loads(rotation_path.read_bytes()) if rotation_path.exists() else None
    current = snapshot(dashboard, rotation)
    try:
        state = json.loads(Path("web/radar_snapshot.json").read_text(encoding="utf-8"))
    except (OSError,ValueError):
        state = {}
    if state.get("schema_version") not in (None,VERSION):
        state = {}
    if not state.get("latest"):
        state["previous"] = historical_dashboard(current["session"])
    state = advance(current,state)
    report = compare(current,state.get("previous"))
    report["dashboard_sha256"] = hashlib.sha256(raw).hexdigest()
    report["rotation_sha256"] = digest(rotation) if rotation else None
    atomic_json("web/radar_data.json",report)
    atomic_json("web/radar_snapshot.json",state)
    print(f"Radar {current['session']} vs {report['previous_session']}: "
          f"{sum(len(m['events']) for m in report['modes'].values())} timeframe events, "
          f"{len(report['full_vwap_events'])} Full VWAP events; {report['comparison_status']}")


if __name__ == "__main__":
    run()
