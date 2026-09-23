"""Static contract tests for the generated VWAP dashboard."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "web" / "index.html"
COCKPIT = ROOT / "web" / "cockpit.js"
MAIN = ROOT / "main.py"


class DashboardContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = INDEX.read_text(encoding="utf-8")
        cls.cockpit = COCKPIT.read_text(encoding="utf-8")
        cls.main = MAIN.read_text(encoding="utf-8")

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

    def test_overview_uses_three_cards_and_hover_scrolling(self):
        for marker in (
            "overview-analysis-grid",
            "minmax(0,1.35fr)",
            "enableVwapCardWheel",
            'card.matches(":hover")',
            "event.preventDefault()",
        ):
            self.assertIn(marker, self.index)
        self.assertNotIn("Distribusi skor", self.index)
        self.assertNotIn("scoredist-text", self.index)
        self.assertNotIn("scoredist-bars", self.index)
        self.assertNotIn("sort(compareVwapCandidates).slice(0,5)", self.index)

    def test_signal_breakdown_is_fitted_bar_chart(self):
        for marker in (
            'id="signal-bar-chart"',
            "signal-bar-value",
            "signal-bar-fill",
            "maximumSignalCount",
            "* 68",
            "gap:clamp(10px,1.4vw,20px)",
        ):
            self.assertIn(marker, self.index)
        self.assertNotIn("sig-rows", self.index)
        self.assertNotIn('id="sig-track"', self.index)
        self.assertNotIn('id="count-beli"', self.index)


    def test_toggle_has_isolated_daily_weekly_swing_data(self):
        for marker in (
            'id="style-daily"',
            'id="style-weekly"',
            'id="style-swing"',
            'let currentStyle = "daily"',
            '"score_daily"',
            '"signal_daily"',
            '"score_swing"',
            '"signal_swing"',
            "styleRows = wl.filter",
            "Menunggu screening otomatis berikutnya",
            "calc(33.333% - 2px)",
            "weekly: 100",
            "swing: 200",
        ):
            self.assertIn(marker, self.index)

    def test_backend_computes_daily_without_copying_weekly(self):
        for marker in (
            "trend_daily = trend_structure",
            "window=2",
            "support_resistance_daily",
            "lookback=20",
            "cs_ihsg_daily",
            "window=5",
            "scored_daily = compute_score",
            'timeframe="daily"',
            'timeframe="weekly"',
            'timeframe="swing"',
            '"score_daily": scored_daily["score"]',
            '"signal_daily": signal_daily',
            '"composite_daily"',
            '"composite_swing"',
            "scored_swing = compute_score",
        ):
            self.assertIn(marker, self.main)

        self.assertIn(
            "scored_swing = compute_score(\n"
            "        trend_swing,\n"
            "        wyckoff_swing,",
            self.main,
        )
        self.assertIn("wyckoff_daily", self.main)
        self.assertIn("wyckoff_swing", self.main)


    def test_volatility_chart_has_trend_colors_and_animated_projection(self):
        for marker in (
            "vol-history-segment",
            "vol-projection-line",
            "vol-terminal-marker",
            "vol-end-marker",
            "vol-line-reveal",
            "vol-projection-reveal",
            "vol-dash-flow",
            "vol-tooltip-card",
            "showVolatilityTooltip",
            "hideVolatilityTooltip",
            "vol-crosshair-",
            "vol-axis-pill",
            "prefers-reduced-motion: reduce",
            'rising ? "#32d74b" : "#ff453a"',
            'stroke="#60a5fa"',
            'pathLength="1"',
            'stroke-dasharray: 2 7',
            "Proyeksi GARCH 95% (10 hari)",
        ):
            self.assertIn(marker, self.index)

    def test_backtest_renderer_tolerates_legacy_report_without_watchlist(self):
        self.assertIn("const tickerCount = Number(data.ticker_count)", self.index)
        self.assertIn("Number.isFinite(tickerCount)", self.index)
        self.assertNotIn("data.watchlist.length", self.index)

    def test_ic_web_shows_conclusions_not_raw_calculations(self):
        for marker in (
            "Validasi VWAP",
            "Daily / Weekly / Swing",
            "renderVWAPICSummary",
            "horizon_results",
            "Web hanya menampilkan",
            "Laporan lama belum sesuai metode terbaru",
        ):
            self.assertIn(marker, self.index)
        self.assertNotIn("Lihat detail teknis (IC, p-value)", self.index)
        self.assertNotIn("<th class=\"num\">IC</th>", self.index)


    def test_wyckoff_validation_is_summary_only(self):
        for marker in (
            "Validasi Wyckoff",
            "loadWyckoffValidationReport",
            "wyckoff_ic_data.json",
            "Event berbobot",
            "konteks visual",
            '"wyckoffKey": "wyckoff_daily"',
            '"wyckoffKey": "wyckoff_swing"',
        ):
            self.assertIn(marker, self.index)
        self.assertNotIn("mean_IC", self.index)
        self.assertNotIn("%positive_months", self.index)

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
