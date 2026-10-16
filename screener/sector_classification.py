"""Bounded official IDX-IC refresh. A failed fetch must never re-date a snapshot."""
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import requests

SOURCE = "https://www.idx.co.id/primary/ListedCompany/GetCompanyProfiles"


def normalized(value):
    return re.sub(r"\s+", " ", html.unescape(str(value)).replace("–", "-").replace("&", " dan ")).strip().casefold()


def parse_companies(payload, sectors, previous):
    reverse = {normalized(name): code for code, name in sectors.items()}
    reverse.update({normalized(code): code for code in sectors})
    companies = {}
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise ValueError("IDX response has no company rows")
    for row in rows:
        if row.get("EfekEmiten_Saham") not in (True, 1, "true"):
            continue
        ticker = str(row.get("KodeEmiten", "")).strip().upper()
        sector = reverse.get(normalized(row.get("Sektor", "")))
        if not re.fullmatch(r"[A-Z0-9]{4}", ticker) or not sector:
            continue
        item = {"name": str(row.get("NamaEmiten", "")).strip(), "sector": sector}
        if ticker in companies and companies[ticker] != item:
            raise ValueError("Conflicting IDX classification rows")
        companies[ticker] = item
    # Retention checks compare identities, not merely the total count.
    if not companies or len(set(companies) & set(previous)) < len(previous) * .95:
        raise ValueError("IDX classification identity coverage regression")
    if set(v["sector"] for v in companies.values()) != set(sectors):
        raise ValueError("IDX classification missing a sector")
    return companies


def load_classification(sectors, path=Path("data/idx_sector_classification.json"), get=None, now=None):
    now = now or datetime.now(timezone.utc)
    today = now.date().isoformat()
    cache = json.loads(path.read_text(encoding="utf-8"))
    age = (now.date() - datetime.fromisoformat(cache["as_of"]).date()).days
    if age < 0:
        raise ValueError("Classification snapshot has a future date")
    if age < 7 or cache.get("last_refresh_attempt") == today:
        cache.setdefault("refresh_status", "cached")
        return cache
    cache["last_refresh_attempt"] = today
    try:
        response = (get or requests.get)(SOURCE,
            params={"start": 0, "length": 9999, "language": "id-id"}, timeout=20,
            headers={"Accept": "application/json"})
        response.raise_for_status()
        companies = parse_companies(response.json(), sectors, cache["companies"])
        cache.update(companies=companies, as_of=today, refresh_status="live",
                     source_url=SOURCE, verified_at=now.isoformat(),
                     verification="Company-sector mapping fetched directly from official IDX endpoint")
        cache.pop("refresh_error", None)
    except (requests.RequestException, KeyError, ValueError, TypeError) as error:
        code = getattr(getattr(error, "response", None), "status_code", None)
        cache["refresh_status"] = "cached_refresh_failed"
        cache["refresh_error"] = "official_access_blocked" if code in (403, 429) else "official_source_unavailable_or_invalid"
        print(f"[rotation] IDX refresh unavailable ({code or type(error).__name__}); snapshot remains {cache['as_of']}")
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return cache
