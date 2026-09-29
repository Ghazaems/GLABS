"""Regression tests for coverage: unavailable symbols must not block healthy data."""
import json
import tempfile
import unittest
from pathlib import Path
from main import validate_available_universe

class CoverageTests(unittest.TestCase):
    def test_stable_partial_universe_is_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "previous.json"
            path.write_text(json.dumps({"watchlist": [{"ticker": str(i)} for i in range(438)]}))
            validate_available_universe({str(i): None for i in range(441)},
                                        [str(i) for i in range(500)], path)

    def test_provider_regression_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "previous.json"
            path.write_text(json.dumps({"watchlist": [{"ticker": str(i)} for i in range(438)]}))
            with self.assertRaisesRegex(RuntimeError, "Coverage regression"):
                validate_available_universe({str(i): None for i in range(400)},
                                            [str(i) for i in range(500)], path)

    def test_missing_baseline_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            validate_available_universe({}, [], Path(tmp) / "missing.json")
