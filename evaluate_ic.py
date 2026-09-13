"""
Uji signifikansi statistik skor screening: Information Coefficient (IC) per
komponen + confidence interval winrate + expectancy.

INI BUKAN backtest baru -- ini MEMBACA backtest_results.csv yang sudah
dihasilkan oleh backtest.py, dan menjawab pertanyaan yang backtest.py
belum jawab secara eksplisit:
1. Apakah skor komposit & tiap komponennya (trend/wyckoff/vwap/dst) BENAR
   berkorelasi dengan return masa depan, secara statistik (bukan cuma kesan
   visual dari tabel kuartil)?
2. Apakah winrate itu SECARA STATISTIK beda dari lempar koin (50%)?
3. Kalau winrate < 50%, apakah sistem tetap bisa untung karena rata-rata
   kemenangan lebih besar dari rata-rata kekalahan (expectancy)?

REVISI PENTING (v2): versi sebelumnya menghitung IC dengan cara yang SALAH
- mencampur semua baris (semua saham, semua tanggal) jadi satu comotan besar
lalu dikorelasikan sekaligus ("pooled IC"). Cara yang benar dan standar di
dunia quant adalah IC CROSS-SECTIONAL: untuk SETIAP TANGGAL, bandingkan skor
semua saham pada tanggal itu vs return mereka setelahnya, hitung korelasinya
per tanggal, baru dirata-ratakan dari banyak tanggal. Cara lama rawan
ketutupan pergerakan pasar bersama (banyak saham naik/turun bareng di hari
yang sama), yang bukan itu yang mau diukur.

CARA PAKAI:
    python evaluate_ic.py
(jalankan setelah backtest.py, karena butuh backtest_results.csv)

OUTPUT:
- Ringkasan bahasa biasa dicetak ke layar (dan ke log GitHub Actions kalau
  dijalankan via workflow).
- web/ic_data.json -- supaya bisa ditampilkan juga di halaman Laporan pada
  web/index.html, sama caranya seperti backtest_data.json.
"""
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr, ttest_1samp
from statsmodels.stats.proportion import proportion_confint

HORIZONS = [5, 10, 20]
COMPONENT_COLS = [
    "comp_trend",
    "comp_wyckoff",
    "comp_vwap",
    "comp_comparative_strength",
    "comp_support_resistance",
]

# Minimal berapa saham di 1 tanggal yang sama supaya korelasi hari itu
# dianggap valid untuk dihitung. Kalau kurang dari ini, tanggal itu dilewati
# (korelasi dari cuma 2-3 saham terlalu tidak stabil untuk dipercaya).
MIN_TICKERS_PER_DATE = 5


def cross_sectional_ic(df: pd.DataFrame, score_col: str, horizon: int):
    """
    IC yang BENAR: dihitung per tanggal (bandingkan skor semua saham pada
    tanggal itu vs return mereka), baru dirata-ratakan lintas tanggal.
    Ini disebut "Fama-MacBeth style" di literatur keuangan kuantitatif.
    """
    ret_col = f"return_{horizon}d_pct"
    daily_ics = []
    dates_used = 0
    dates_skipped_too_few = 0

    for date, group in df.groupby("date"):
        valid = group[[score_col, ret_col]].dropna()
        if len(valid) < MIN_TICKERS_PER_DATE or valid[score_col].nunique() < 2:
            dates_skipped_too_few += 1
            continue
        ic, _ = spearmanr(valid[score_col], valid[ret_col])
        if not np.isnan(ic):
            daily_ics.append(ic)
            dates_used += 1

    if dates_used < 5:
        # Terlalu sedikit tanggal yang punya cukup saham buat dipercaya.
        return None, None, dates_used, dates_skipped_too_few, daily_ics

    mean_ic = float(np.mean(daily_ics))
    # Uji-t satu sampel: apakah rata-rata IC harian ini beda dari 0 secara
    # statistik (bukan cuma kebetulan dari sedikit tanggal yang beruntung).
    t_stat, p_value = ttest_1samp(daily_ics, 0)
    return mean_ic, float(p_value), dates_used, dates_skipped_too_few, daily_ics


def winrate_confidence_interval(df: pd.DataFrame, horizon: int):
    col = f"return_{horizon}d_pct"
    wins = int((df[col] > 0).sum())
    total = len(df)
    winrate = wins / total * 100
    lower, upper = proportion_confint(wins, total, alpha=0.05, method="wilson")
    return winrate, lower * 100, upper * 100, total


def expectancy(df: pd.DataFrame, horizon: int):
    col = f"return_{horizon}d_pct"
    wins = df[df[col] > 0][col]
    losses = df[df[col] <= 0][col]
    avg_win = wins.mean() if len(wins) else 0
    avg_loss = losses.mean() if len(losses) else 0
    winrate = len(wins) / len(df) if len(df) else 0
    exp = winrate * avg_win + (1 - winrate) * avg_loss
    return avg_win, avg_loss, exp


def main():
    df = pd.read_csv("backtest_results.csv")

    print("=" * 78)
    print("UJI STATISTIK: apakah skor benar berkorelasi dengan return masa depan?")
    print("=" * 78)

    report = {
        "generated_at": datetime.now().isoformat(),
        "total_sampel": len(df),
        "horizons": HORIZONS,
        "composite": {},
        "components": {c.replace("comp_", ""): {} for c in COMPONENT_COLS if c in df.columns},
        "winrate": {},
        "expectancy": {},
    }

    for h in HORIZONS:
        print(f"\n--- Horizon {h} hari bursa ---")

        ic, p, n_dates, n_skipped, _ = cross_sectional_ic(df, "score", h)
        if ic is None:
            print(f"  Skor komposit: tanggal dengan data cukup terlalu sedikit "
                  f"({n_dates} tanggal valid, {n_skipped} dilewati)")
            report["composite"][str(h)] = None
        else:
            signif = p < 0.05
            print(f"  Skor komposit  : IC={ic:+.4f}  p-value={p:.4f}  "
                  f"({'SIGNIFIKAN' if signif else 'tidak signifikan'}, "
                  f"{n_dates} tanggal valid, {n_skipped} dilewati krn saham < {MIN_TICKERS_PER_DATE})")
            report["composite"][str(h)] = {
                "ic": round(ic, 4), "p_value": round(p, 4), "n_dates": n_dates,
                "n_dates_skipped": n_skipped, "significant": bool(signif),
            }

        for comp in COMPONENT_COLS:
            if comp not in df.columns:
                continue
            name = comp.replace("comp_", "")
            ic, p, n_dates, n_skipped, _ = cross_sectional_ic(df, comp, h)
            label = name.ljust(20)
            if ic is None:
                print(f"    {label}: tanggal dengan data cukup terlalu sedikit ({n_dates} tanggal)")
                report["components"][name][str(h)] = None
                continue
            signif = p < 0.05
            print(f"    {label}: IC={ic:+.4f}  p-value={p:.4f}  "
                  f"({'SIGNIFIKAN' if signif else 'tidak signifikan'}, {n_dates} tanggal valid)")
            report["components"][name][str(h)] = {
                "ic": round(ic, 4), "p_value": round(p, 4), "n_dates": n_dates,
                "n_dates_skipped": n_skipped, "significant": bool(signif),
            }

        winrate, lower, upper, n = winrate_confidence_interval(df, h)
        beats_coinflip = lower > 50
        print(f"\n  Winrate: {winrate:.1f}% | interval 95%: [{lower:.1f}%, {upper:.1f}%] | n={n}")
        print(f"  Beda signifikan dari coin flip (>50%)? {'YA' if beats_coinflip else 'TIDAK'}")
        report["winrate"][str(h)] = {
            "winrate_pct": round(winrate, 2),
            "ci_lower_pct": round(lower, 2),
            "ci_upper_pct": round(upper, 2),
            "n": n,
            "beats_coinflip": bool(beats_coinflip),
        }

        avg_win, avg_loss, exp = expectancy(df, h)
        print(f"  Rata-rata saat untung: {avg_win:+.2f}%  |  Rata-rata saat rugi: {avg_loss:+.2f}%")
        print(f"  Expectancy per sinyal: {exp:+.3f}%  ({'POSITIF' if exp > 0 else 'NEGATIF'})")
        report["expectancy"][str(h)] = {
            "avg_win_pct": round(avg_win, 3),
            "avg_loss_pct": round(avg_loss, 3),
            "expectancy_pct": round(exp, 4),
            "positive": bool(exp > 0),
        }

    print("\n" + "=" * 78)
    print("CARA BACA:")
    print("- IC dihitung PER TANGGAL dulu (skor semua saham vs return mereka hari")
    print("  itu), baru dirata-ratakan lintas tanggal -- bukan dicampur semua jadi")
    print("  satu comotan besar (versi lama salah begini, sudah diperbaiki).")
    print("- IC positif + p-value < 0.05 -> komponen itu PUNYA nilai prediktif nyata.")
    print("- IC negatif signifikan -> arahnya TERBALIK, ada kemungkinan bug logika.")
    print("- Winrate interval mencakup 50% -> belum beda dari lempar koin secara statistik.")
    print("- Expectancy positif meski winrate <50% -> sistem masih bisa untung kalau")
    print("  kemenangan rata-rata jauh lebih besar dari kekalahan.")
    print("=" * 78)

    out_path = Path(__file__).resolve().parent / "web" / "ic_data.json"
    out_path.parent.mkdir(exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nHasil uji statistik tersimpan ke {out_path}")


if __name__ == "__main__":
    main()
