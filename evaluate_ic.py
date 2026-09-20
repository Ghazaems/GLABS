"""Evaluate cross-sectional IC and signal outcomes from a backtest JSON file."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

COMPONENTS = ("technical", "fundamental", "sentiment", "risk", "composite")


def _safe_spearman(x: pd.Series, y: pd.Series) -> float | None:
    pair = pd.concat([pd.to_numeric(x, errors="coerce"), pd.to_numeric(y, errors="coerce")], axis=1).dropna()
    if len(pair) < 5 or pair.iloc[:, 0].nunique() < 2 or pair.iloc[:, 1].nunique() < 2:
        return None
    value, _ = spearmanr(pair.iloc[:, 0], pair.iloc[:, 1])
    return float(value) if np.isfinite(value) else None


def _cross_sectional_ic(frame: pd.DataFrame, score: str, target: str) -> dict:
    daily = []
    for date, group in frame.groupby("signal_date"):
        ic = _safe_spearman(group[score], group[target])
        if ic is not None:
            daily.append((date, ic))
    if not daily:
        return {"mean": None, "median": None, "positive_rate": None, "days": 0}
    values = np.asarray([value for _, value in daily], dtype=float)
    return {
        "mean": round(float(values.mean()), 4),
        "median": round(float(np.median(values)), 4),
        "positive_rate": round(float((values > 0).mean() * 100), 2),
        "days": int(len(values)),
    }


def _outcome(values: pd.Series) -> dict:
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    if numeric.empty:
        return {"n": 0, "mean": None, "median": None, "winrate": None, "p05": None, "p95": None}
    return {
        "n": int(len(numeric)),
        "mean": round(float(numeric.mean()), 4),
        "median": round(float(numeric.median()), 4),
        "winrate": round(float((numeric > 0).mean() * 100), 2),
        "p05": round(float(numeric.quantile(0.05)), 4),
        "p95": round(float(numeric.quantile(0.95)), 4),
    }


def evaluate(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("rows", [])
    frame = pd.DataFrame(rows)
    if frame.empty:
        return {"error": "Tidak ada baris backtest.", "source": str(path)}

    frame["signal_date"] = pd.to_datetime(frame["signal_date"], errors="coerce")
    return_columns = [column for column in ("return_5d", "return_10d", "return_20d") if column in frame]
    available_components = [component for component in COMPONENTS if component in frame]

    report: dict = {
        "source": str(path),
        "methodology": payload.get("methodology", {}),
        "sample_count": int(len(frame)),
        "cross_sectional_ic": {},
        "outcomes": {},
        "vwap_signal_outcomes": {},
    }

    for component in available_components:
        report["cross_sectional_ic"][component] = {
            target: _cross_sectional_ic(frame, component, target) for target in return_columns
        }

    report["outcomes"]["all"] = {target: _outcome(frame[target]) for target in return_columns}
    if "composite" in frame:
        ranked = frame.dropna(subset=["composite"]).copy()
        if not ranked.empty:
            ranked["bucket"] = pd.qcut(
                ranked["composite"].rank(method="first"),
                q=min(5, len(ranked)),
                labels=False,
                duplicates="drop",
            )
            for bucket, group in ranked.groupby("bucket"):
                report["outcomes"][f"composite_bucket_{int(bucket) + 1}"] = {
                    target: _outcome(group[target]) for target in return_columns
                }

    if "vwap_signal" in frame:
        for signal, group in frame.dropna(subset=["vwap_signal"]).groupby("vwap_signal"):
            report["vwap_signal_outcomes"][str(signal)] = {
                target: _outcome(group[target]) for target in return_columns
            }

    return report


def main() -> None:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("reports/backtest_latest.json")
    output = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("reports/ic_latest.json")
    report = evaluate(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
