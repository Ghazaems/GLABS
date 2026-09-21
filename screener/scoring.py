"""
Skor komposit per ticker, menggabungkan semua modul jadi 1 angka (-100 s/d 100)
untuk keperluan ranking di dashboard ('Top pick', 'Distribusi skor').

VERSI DIPERKETAT (v2):
- Threshold beli/jual SIMETRIS (dulu: beli >=40, jual <=-30 -- tidak adil,
  jual lebih gampang trigger). Sekarang keduanya butuh |score| >= 40.
- Sinyal "beli"/"jual" WAJIB didukung minimal 3 dari 5 komponen yang searah,
  bukan cuma total skor lewat threshold. Mencegah 1 komponen dominan (misal
  trend doang) memicu sinyal kuat tanpa konfirmasi faktor lain.
- Wyckoff bias "conflicting" (lihat wyckoff.py) dinetralkan (skor 0) dan
  dicatat sebagai catatan risiko di breakdown.
"""

TREND_SCORE = {"uptrend": 30, "sideways": 0, "downtrend": -30, "insufficient_data": 0}
WYCKOFF_PHASE_SCORE = {
    "A": 5, "B": 10, "C": 20, "D": 30, "E": 15,
}

BUY_THRESHOLD = 40
SELL_THRESHOLD = -40  # simetris dengan BUY_THRESHOLD
MIN_CONFIRMING_FACTORS = 3  # dari 5 komponen: trend, wyckoff, vwap, comparative, sr


def _phase_letter(phase_str: str) -> str:
    return phase_str.split(" ")[0] if phase_str else ""


def compute_score(trend: str, wyckoff: dict, vwap: dict, comparative: dict,
                   support_resistance: dict,
                   wyckoff_weights: dict[str, float] | None = None) -> dict:
    score = 0
    breakdown = {}
    notes = []

    # Trend structure
    s = TREND_SCORE.get(trend, 0)
    score += s
    breakdown["trend"] = s

    # Wyckoff hanya boleh memengaruhi skor bila event pada bar terbaru
    # sudah lolos validasi cross-sectional untuk timeframe terkait.
    weights = wyckoff_weights or {}
    current_events = wyckoff.get("current_events", [])
    s = round(
        sum(
            float(weights.get(event_type, 0.0))
            for event_type in current_events
        ),
        2,
    )
    s = max(-30.0, min(30.0, s))
    if not current_events:
        notes.append("Tidak ada event Wyckoff baru pada bar terakhir.")
    elif not any(event_type in weights for event_type in current_events):
        notes.append(
            "Event Wyckoff hanya kontekstual; belum lolos validasi statistik."
        )
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

    # Dekat support (bonus) vs dekat resistance (penalti kecil)
    last = support_resistance.get("last_close")
    support = support_resistance.get("nearest_support")
    resistance = support_resistance.get("nearest_resistance")
    s = 0
    if last and support and (last - support) / last < 0.03:
        s += 10
    if last and resistance and (resistance - last) / last < 0.03:
        s -= 5
    score += s
    breakdown["support_resistance"] = s

    positive_count = sum(1 for v in breakdown.values() if v > 0)
    negative_count = sum(1 for v in breakdown.values() if v < 0)

    result = {
        "score": round(score, 1),
        "breakdown": breakdown,
        "positive_count": positive_count,
        "negative_count": negative_count,
    }
    if notes:
        result["notes"] = notes
    return result


def classify_signal(scored: dict) -> str:
    """
    Terjemahkan skor jadi label aksi (Beli/Pantau/Jual).

    Butuh 2 syarat sekaligus:
    1. |score| melewati threshold (simetris +-40)
    2. Minimal MIN_CONFIRMING_FACTORS komponen searah dengan sinyal
       (mencegah 1 komponen dominan trigger sinyal sendirian)
    """
    score = scored["score"]
    pos = scored.get("positive_count", 0)
    neg = scored.get("negative_count", 0)

    if score >= BUY_THRESHOLD and pos >= MIN_CONFIRMING_FACTORS:
        return "beli"
    if score <= SELL_THRESHOLD and neg >= MIN_CONFIRMING_FACTORS:
        return "jual"
    return "pantau"
