"""
Skor komposit per ticker, menggabungkan semua modul jadi 1 angka (-100 s/d 100)
untuk keperluan ranking di dashboard ('Top pick', 'Distribusi skor').
Bobot bisa di-tuning nanti setelah lihat hasil live.
"""

TREND_SCORE = {"uptrend": 30, "sideways": 0, "downtrend": -30, "insufficient_data": 0}
WYCKOFF_PHASE_SCORE = {
    "A": 5, "B": 10, "C": 20, "D": 30, "E": 15,
}


def _phase_letter(phase_str: str) -> str:
    return phase_str.split(" ")[0] if phase_str else ""


def compute_score(trend: str, wyckoff: dict, vwap: dict, comparative: dict,
                   support_resistance: dict) -> dict:
    score = 0
    breakdown = {}

    # Trend structure (bobot terbesar - fondasi swing)
    s = TREND_SCORE.get(trend, 0)
    score += s
    breakdown["trend"] = s

    # Wyckoff bias + phase
    s = 0
    if wyckoff.get("bias") == "accumulation":
        s += WYCKOFF_PHASE_SCORE.get(_phase_letter(wyckoff.get("phase", "")), 0)
    elif wyckoff.get("bias") == "distribution":
        s -= WYCKOFF_PHASE_SCORE.get(_phase_letter(wyckoff.get("phase", "")), 0)
    score += s
    breakdown["wyckoff"] = s

    # VWAP position
    s = 15 if vwap.get("position") == "above" else -15 if vwap.get("position") == "below" else 0
    score += s
    breakdown["vwap"] = s

    # Comparative strength vs IHSG
    s = 15 if comparative.get("relative_strength_trend") == "outperforming" else \
        -15 if comparative.get("relative_strength_trend") == "underperforming" else 0
    score += s
    breakdown["comparative_strength"] = s

    # Dekat support (bonus) vs dekat resistance (penalti kecil, makin dekat makin berisiko)
    last = support_resistance.get("last_close")
    support = support_resistance.get("nearest_support")
    resistance = support_resistance.get("nearest_resistance")
    s = 0
    if last and support and (last - support) / last < 0.03:
        s += 10  # dekat support = area entry potensial
    if last and resistance and (resistance - last) / last < 0.03:
        s -= 5  # dekat resistance = risiko tertahan
    score += s
    breakdown["support_resistance"] = s

    return {"score": round(score, 1), "breakdown": breakdown}


def classify_signal(score: float) -> str:
    """Terjemahkan skor jadi label aksi, sesuai badge di dashboard (Beli/Pantau/Jual)."""
    if score >= 40:
        return "beli"
    if score <= -30:
        return "jual"
    return "pantau"
