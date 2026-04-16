"""
Unit tests for Task 5: Review Gate + Parse Report checks.
Tests live in a separate file per the task spec.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import pytest
from raw_to_structured import (
    check_needs_review_rate,
    check_field_lengths,
    check_boilerplate,
    check_cell_lengths,
    reconcile_manifest,
    build_parse_report,
    BOILERPLATE_PHRASES,
    MAX_CELL_LENGTH,
)


# ---------------------------------------------------------------------------
# TestNeedsReviewRate
# ---------------------------------------------------------------------------

class TestNeedsReviewRate:

    def test_below_threshold_passes(self):
        """20% needs_review with 0.50 threshold → passes."""
        obs = [{"needs_review": False}] * 8 + [{"needs_review": True}] * 2
        passed, rate = check_needs_review_rate(obs, threshold=0.50)
        assert passed is True
        assert rate == pytest.approx(0.20)

    def test_above_threshold_fails(self):
        """60% needs_review with 0.50 threshold → fails."""
        obs = [{"needs_review": False}] * 4 + [{"needs_review": True}] * 6
        passed, rate = check_needs_review_rate(obs, threshold=0.50)
        assert passed is False
        assert rate == pytest.approx(0.60)

    def test_at_threshold_fails(self):
        """Exactly at threshold → fails (must be strictly below)."""
        obs = [{"needs_review": False}] * 5 + [{"needs_review": True}] * 5
        passed, rate = check_needs_review_rate(obs, threshold=0.50)
        assert passed is False
        assert rate == pytest.approx(0.50)

    def test_empty_list_fails(self):
        """Empty list → (False, 1.0)."""
        passed, rate = check_needs_review_rate([])
        assert passed is False
        assert rate == pytest.approx(1.0)

    def test_all_clean_passes(self):
        """0% needs_review → passes."""
        obs = [{"needs_review": False}] * 10
        passed, rate = check_needs_review_rate(obs)
        assert passed is True
        assert rate == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# TestFieldLengths
# ---------------------------------------------------------------------------

class TestFieldLengths:

    def _make_obs(self, symbol="AAOI", signal="OK signal", macd_rsi="MACD flat"):
        return {
            "symbol": symbol,
            "signal": signal,
            "macd_rsi": macd_rsi,
            "needs_review": False,
        }

    def test_valid_fields_pass(self):
        obs = [self._make_obs()]
        errors = check_field_lengths(obs)
        assert errors == []

    def test_symbol_too_long_fails(self):
        obs = [self._make_obs(symbol="A" * 13)]
        errors = check_field_lengths(obs)
        assert len(errors) >= 1
        assert any("symbol" in e for e in errors)

    def test_signal_too_long_fails(self):
        obs = [self._make_obs(signal="S" * 121)]
        errors = check_field_lengths(obs)
        assert len(errors) >= 1
        assert any("signal" in e for e in errors)

    def test_macd_rsi_too_long_fails(self):
        obs = [self._make_obs(macd_rsi="M" * 121)]
        errors = check_field_lengths(obs)
        assert len(errors) >= 1
        assert any("macd_rsi" in e for e in errors)

    def test_multiple_violations_reported(self):
        obs = [self._make_obs(symbol="A" * 13, signal="S" * 121)]
        errors = check_field_lengths(obs)
        assert len(errors) >= 2

    def test_none_fields_ignored(self):
        """None values should not trigger length errors."""
        obs = [{"symbol": "AAOI", "signal": None, "macd_rsi": None}]
        errors = check_field_lengths(obs)
        assert errors == []


# ---------------------------------------------------------------------------
# TestBoilerplate
# ---------------------------------------------------------------------------

class TestBoilerplate:

    def test_clean_data_passes(self):
        obs = [{"symbol": "AAOI", "signal": "Red candle valid", "macd_rsi": "MACD curling up"}]
        errors = check_boilerplate(obs)
        assert errors == []

    def test_boilerplate_detected(self):
        phrase = BOILERPLATE_PHRASES[0]  # "Get more out of every post"
        obs = [{"symbol": "AAOI", "signal": f"Some text {phrase} here"}]
        errors = check_boilerplate(obs)
        assert len(errors) >= 1
        assert any(phrase in e for e in errors)

    def test_all_boilerplate_phrases_detected(self):
        """Each boilerplate phrase must be caught when present."""
        for phrase in BOILERPLATE_PHRASES:
            obs = [{"symbol": "TEST", "signal": phrase}]
            errors = check_boilerplate(obs)
            assert len(errors) >= 1, f"phrase not caught: {phrase!r}"

    def test_non_string_fields_ignored(self):
        """Numeric / bool fields must not cause errors or exceptions."""
        obs = [{"symbol": "AAOI", "closing_price": 107.45, "needs_review": False,
                "whale_pct": 87.08}]
        errors = check_boilerplate(obs)
        assert errors == []


# ---------------------------------------------------------------------------
# TestCellLengths
# ---------------------------------------------------------------------------

class TestCellLengths:

    def test_normal_cells_pass(self):
        md = (
            "| Ticker | Close | Support |\n"
            "|--------|-------|---------|  \n"
            "| AAOI | $107.45 | $83, $94 |\n"
        )
        errors = check_cell_lengths(md)
        assert errors == []

    def test_long_cell_fails(self):
        long_content = "X" * (MAX_CELL_LENGTH + 1)
        md = f"| Ticker | Close |\n|--------|-------|\n| AAOI | {long_content} |\n"
        errors = check_cell_lengths(md)
        assert len(errors) >= 1

    def test_separator_rows_skipped(self):
        """Separator rows should not trigger errors even if wide."""
        md = "| Ticker |\n|" + "-" * 600 + "|\n| AAOI |\n"
        errors = check_cell_lengths(md)
        assert errors == []

    def test_non_table_lines_ignored(self):
        md = "## Heading\n\nSome regular paragraph text.\n\n| A | B |\n|---|---|\n| x | y |\n"
        errors = check_cell_lengths(md)
        assert errors == []

    def test_exact_limit_passes(self):
        """A cell exactly at MAX_CELL_LENGTH must NOT trigger an error."""
        content = "A" * MAX_CELL_LENGTH
        md = f"| Ticker |\n|--------|\n| {content} |\n"
        errors = check_cell_lengths(md)
        assert errors == []


# ---------------------------------------------------------------------------
# TestReconcileManifest
# ---------------------------------------------------------------------------

class TestReconcileManifest:

    def test_all_reconciled(self):
        manifest = ["id1", "id2", "id3"]
        result = reconcile_manifest(
            manifest_scraped=manifest,
            processed=["id1", "id2"],
            skipped_no_ticker=["id3"],
            failed=[],
        )
        assert result["all_reconciled"] is True
        assert result["abort"] is False
        assert result["not_in_manifest"] == []
        assert result["unreconciled"] == []

    def test_processed_not_in_manifest_aborts(self):
        """A processed ID that is not in the manifest should trigger ABORT."""
        result = reconcile_manifest(
            manifest_scraped=["id1"],
            processed=["id1", "id_ghost"],
            skipped_no_ticker=[],
            failed=[],
        )
        assert result["abort"] is True
        assert result["all_reconciled"] is False
        assert "id_ghost" in result["not_in_manifest"]

    def test_unreconciled_manifest_entry_aborts(self):
        """A manifest ID not found in any bucket should trigger ABORT."""
        result = reconcile_manifest(
            manifest_scraped=["id1", "id_missing"],
            processed=["id1"],
            skipped_no_ticker=[],
            failed=[],
        )
        assert result["abort"] is True
        assert result["all_reconciled"] is False
        assert "id_missing" in result["unreconciled"]

    def test_skipped_counts_as_reconciled(self):
        """IDs in skipped_no_ticker satisfy the manifest."""
        result = reconcile_manifest(
            manifest_scraped=["id1", "id2"],
            processed=["id1"],
            skipped_no_ticker=["id2"],
            failed=[],
        )
        assert result["all_reconciled"] is True
        assert result["abort"] is False

    def test_failed_counts_as_reconciled(self):
        """IDs in failed bucket satisfy the manifest."""
        result = reconcile_manifest(
            manifest_scraped=["id1", "id2"],
            processed=["id1"],
            skipped_no_ticker=[],
            failed=["id2"],
        )
        assert result["all_reconciled"] is True
        assert result["abort"] is False


# ---------------------------------------------------------------------------
# TestBuildParseReport (smoke test)
# ---------------------------------------------------------------------------

class TestBuildParseReport:

    def test_builds_report(self, tmp_path):
        """build_parse_report returns a dict with expected keys."""
        # Create a dummy watchlist_next file to hash
        wl_path = tmp_path / "watchlist_next.md"
        wl_path.write_text("# test watchlist\n")

        obs = [
            {"symbol": "AAOI", "whale_pct": 87.08, "needs_review": False,
             "signal": "Red candle", "macd_rsi": "Flattening", "date": "2026-04-07"},
        ]
        report = build_parse_report(
            run_date="2026-04-16",
            raw_files_processed=1,
            raw_files_skipped_no_ticker=0,
            batch_file="/tmp/batch.md",
            watchlist_next_path=str(wl_path),
            observations=obs,
            prior_run_count=0,
            post_ids_processed=["p1"],
            post_ids_skipped_no_ticker=[],
            post_ids_from_manifest=["p1"],
            existing_symbols=["PLTR"],
        )
        assert report["run_date"] == "2026-04-16"
        assert report["observations_count"] == 1
        assert "watchlist_next_sha256" in report
        assert report["watchlist_next_sha256"] is not None
        assert report["reconcile"]["all_reconciled"] is True

    def test_new_symbols_identified(self, tmp_path):
        """Symbols not in existing_symbols are included in new_symbols."""
        wl_path = tmp_path / "wl.md"
        wl_path.write_text("# wl\n")
        obs = [{"symbol": "NVDA", "whale_pct": 90.0, "needs_review": False,
                "signal": "Red candle", "macd_rsi": "Curling up", "date": "2026-04-16"}]
        report = build_parse_report(
            run_date="2026-04-16",
            raw_files_processed=1,
            raw_files_skipped_no_ticker=0,
            batch_file="/tmp/b.md",
            watchlist_next_path=str(wl_path),
            observations=obs,
            prior_run_count=5,
            post_ids_processed=["p1"],
            post_ids_skipped_no_ticker=[],
            post_ids_from_manifest=["p1"],
            existing_symbols=["AAOI", "PLTR"],
        )
        assert "NVDA" in report["new_symbols"]
