"""Verified IDX equity sessions, Jakarta time; unknown years fail closed."""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

WIB = ZoneInfo("Asia/Jakarta")
# Conservative publication boundary, after the closing phases.
PUBLICATION_CLOSE = time(16, 15)
RECOVERY_DEADLINE = time(18)
CALENDAR_SOURCES = (
    "https://www.idx.id/id/berita/jadwal-libur-bursa",
    "https://web.ksei.co.id/files/1767843003_Penyesuaian_Pengumuman_Hari_Libur_dan_Cuti_Bersama_PT_KSEI_Ta....pdf",
)
HOLIDAYS = {2026: frozenset(date.fromisoformat(s) for s in (
    "2026-01-01", "2026-01-16", "2026-02-16", "2026-02-17",
    "2026-03-18", "2026-03-19", "2026-03-20", "2026-03-23", "2026-03-24",
    "2026-04-03", "2026-05-01", "2026-05-14", "2026-05-15",
    "2026-05-27", "2026-05-28", "2026-06-01", "2026-06-16",
    "2026-08-17", "2026-08-25", "2026-12-24", "2026-12-25", "2026-12-31",
))}
VERIFIED_THROUGH = date(2026, 12, 31)

def is_session(day):
    if day.year not in HOLIDAYS:
        raise ValueError(f"IDX calendar not verified for {day.year}; retain published data")
    return day.weekday() < 5 and day not in HOLIDAYS[day.year]

def completed_session(now=None):
    now = now or datetime.now(WIB)
    if now.tzinfo is None:
        raise ValueError("Timezone-aware clock required")
    local = now.astimezone(WIB)
    day = local.date()
    # Verify the current calendar even before looking backwards.
    is_session(day)
    if local.time() < PUBLICATION_CLOSE:
        day -= timedelta(days=1)
    for _ in range(30):
        if is_session(day):
            return day
        day -= timedelta(days=1)
    raise ValueError("No verified completed session within 30 days")

def in_recovery_window(now=None):
    local = (now or datetime.now(WIB)).astimezone(WIB)
    session = completed_session(local)
    return session < local.date() or local.time() >= RECOVERY_DEADLINE


