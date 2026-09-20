"""Static contract tests for the generated VWAP dashboard."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "web" / "index.html"
COCKPIT = ROOT / "web" / "cockpit.js"


class DashboardContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = INDEX.read_text(encoding="utf-8")
        cls.cockpit = COCKPIT.read_text(encoding="utf-8")

    def test_dashboard_exposes_multi_horizon_decision(self):
        for marker in (
            "Full VWAP 5/20/60",
            "vwap_signal",
            "vwap_analysis",
            "vwap-signal-list",
            "vwap-signal-row",
        ):
            self.assertIn(marker, self.index)

    def test_html_preserves_all_six_vwap_signals(self):
        for signal in ("BUY", "HOLD", "WAIT", "REDUCE", "EXIT", "AVOID"):
            self.assertIn(signal, self.index)
        self.assertIn("vwap-signal-list", self.index)
        self.assertIn("vwap-signal-row", self.index)
        self.assertNotIn("vwapDisplaySignal", self.index)

    def test_vwap_card_uses_only_valid_vwap_ranking(self):
        for marker in (
            'r.vwap_analysis?.status === "ok"',
            "compareVwapCandidates",
            "VWAP_SIGNAL_PRIORITY",
            "vwapRankMetrics",
        ):
            self.assertIn(marker, self.index)
        self.assertNotIn("return priorityDiff || ((b.score", self.index)

    def test_cockpit_has_three_vwap_lines_and_risk_context(self):
        for marker in (
            "VWAP 5D",
            "VWAP 20D",
            "VWAP 60D",
            "Protective stop",
            "next_session_open",
            "Confidence sengaja tidak ditampilkan",
        ):
            self.assertIn(marker, self.cockpit)

    def test_old_single_vwap_panel_is_removed(self):
        self.assertNotIn("VWAP MINGGUAN", self.cockpit)


if __name__ == "__main__":
    unittest.main()
