import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import requests
from screener.sector_classification import load_classification, parse_companies


class ClassificationTests(unittest.TestCase):
    sectors = {"IDXENERGY": "Energi", "IDXPROPERT": "Properti & Real Estat"}
    previous = {"AADI": {"sector": "IDXENERGY"}, "APLN": {"sector": "IDXPROPERT"}}

    def test_parser_normalizes_labels_and_rejects_replacement_names(self):
        rows = [{"KodeEmiten": ticker, "NamaEmiten": ticker, "Sektor": sector, "EfekEmiten_Saham": True}
                for ticker, sector in [("AADI", "Energi"), ("APLN", "Properti &amp; Real Estat")]]
        self.assertEqual(parse_companies({"data": rows}, self.sectors, self.previous)["APLN"]["sector"], "IDXPROPERT")
        rows[0]["KodeEmiten"] = "ZZZZ"
        with self.assertRaises(ValueError):
            parse_companies({"data": rows}, self.sectors, self.previous)

    def test_blocked_source_retains_date_and_backs_off_until_next_day(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "classification.json"
            initial = {"as_of": "2026-02-03", "companies": self.previous}
            path.write_text(json.dumps(initial), encoding="utf-8")
            calls = []
            def blocked(*args, **kwargs):
                calls.append(args)
                response = requests.Response()
                response.status_code = 403
                raise requests.HTTPError(response=response)
            now = datetime(2026, 10, 16, tzinfo=timezone.utc)
            result = load_classification(self.sectors, path, blocked, now)
            self.assertEqual(result["as_of"], "2026-02-03")
            self.assertEqual(result["companies"], self.previous)
            self.assertEqual(result["refresh_error"], "official_access_blocked")
            load_classification(self.sectors, path, blocked, now)
            self.assertEqual(len(calls), 1)
            load_classification(self.sectors, path, blocked, now.replace(day=17))
            self.assertEqual(len(calls), 2)
