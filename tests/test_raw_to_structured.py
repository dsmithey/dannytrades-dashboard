"""
Unit tests for scripts/raw_to_structured.py
TDD — tests written before implementation.
Fixtures:
  - single_ticker.txt: PLTR post (155338136), single-line file with literal \n sequences
  - multi_ticker.txt:  AAOI/LITE/COHR/CIEN post (154978919), real newlines, 4 numbered blocks
  - no_ticker.txt:     Weekly Insights commentary, no ticker data
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import pytest
from raw_to_structured import (
    strip_chrome,
    extract_post_metadata,
    split_ticker_blocks,
    extract_ticker_fields,
    parse_raw_post,
    format_batch_entry,
    write_batch_file,
    read_watchlist,
    merge_watchlist,
    write_watchlist_next,
    BOILERPLATE_PHRASES,
    FIELD_LIMITS,
    MAX_CELL_LENGTH,
)

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> str:
    """Load a fixture file.  single_ticker.txt is stored with literal \\n — decode them."""
    raw = (FIXTURES / name).read_text(encoding="utf-8")
    # single_ticker.txt is a JSON-like string: starts with '"' and uses literal \n
    if raw.startswith('"') and r"\n" in raw:
        # Strip surrounding quotes and decode escape sequences
        raw = raw.strip().strip('"')
        raw = raw.replace(r"\n", "\n")
    return raw


# ---------------------------------------------------------------------------
# Shared fixture strings used across multiple test classes
# ---------------------------------------------------------------------------

MULTI_RAW = load_fixture("multi_ticker.txt")
SINGLE_RAW = load_fixture("single_ticker.txt")
NO_TICKER_RAW = load_fixture("no_ticker.txt")


# ---------------------------------------------------------------------------
# TestStripChrome
# ---------------------------------------------------------------------------

class TestStripChrome:
    """strip_chrome(raw) should remove Patreon navigation boilerplate."""

    def test_removes_nav_header(self):
        """Top nav (DannyTrades / Home / Posts / ...) must be removed."""
        body = strip_chrome(MULTI_RAW)
        assert "Home\n" not in body
        assert "Collections\n" not in body
        assert "Shop\n" not in body
        assert "Membership\n" not in body
        assert "Recommendations\n" not in body
        assert "Gift\n" not in body

    def test_removes_related_posts(self):
        """Everything at/after 'Related posts' must be stripped."""
        body = strip_chrome(MULTI_RAW)
        assert "Related posts" not in body

    def test_removes_get_more(self):
        """'Get more out of every post' line must be stripped."""
        body = strip_chrome(MULTI_RAW)
        assert "Get more out of every post" not in body

    def test_strips_comments_section(self):
        """Comments (e.g. 'N comments' line or individual comment text) must be stripped."""
        body = strip_chrome(MULTI_RAW)
        # The comments section starts around '4 comments' in multi_ticker.txt
        assert "Bought AAOI" not in body
        assert "Well done!" not in body

    def test_single_ticker_strip(self):
        """strip_chrome works on the single-ticker fixture (decoded literal-\\n file)."""
        body = strip_chrome(SINGLE_RAW)
        assert "Home\n" not in body
        assert "Related posts" not in body
        assert "Get more out of every post" not in body

    def test_title_preserved(self):
        """The post title line must survive chrome stripping."""
        body = strip_chrome(MULTI_RAW)
        assert "AAOI" in body or "$AAOI" in body


# ---------------------------------------------------------------------------
# TestExtractPostMetadata
# ---------------------------------------------------------------------------

MULTI_TITLE = (
    "TIER 3 -Top 4 Bullish Photonics Stocks- $AAOI, $LITE, $COHR, $CIEN "
    "(1 New Red Candle), with Dr Cat's Video Insights on $AAOI and $LITE "
    "(April 7, 2026-daily)"
)
SINGLE_TITLE = "$PLTR (April 11, 2026-daily and weekly charts)"
WEEKLY_TITLE = "Weekly Insights Part 1: S&P 500 Bull and Bear Markets: The Stairs vs. The Elevator (April 6, 2026)"


class TestExtractPostMetadata:

    def test_extracts_date(self):
        meta = extract_post_metadata(MULTI_TITLE)
        assert meta["date"] == "2026-04-07"

    def test_extracts_tickers(self):
        meta = extract_post_metadata(MULTI_TITLE)
        assert set(meta["tickers"]) == {"AAOI", "LITE", "COHR", "CIEN"}

    def test_extracts_tier(self):
        meta = extract_post_metadata(MULTI_TITLE)
        assert meta["tier"] == 3

    def test_extracts_timeframe_daily(self):
        meta = extract_post_metadata(MULTI_TITLE)
        assert "daily" in meta["timeframes"]

    def test_extracts_timeframe_weekly(self):
        meta = extract_post_metadata(SINGLE_TITLE)
        assert "weekly" in meta["timeframes"]

    def test_extracts_timeframe_daily_and_weekly(self):
        meta = extract_post_metadata(SINGLE_TITLE)
        assert "daily" in meta["timeframes"]
        assert "weekly" in meta["timeframes"]

    def test_no_date_returns_none(self):
        meta = extract_post_metadata("Some post with no date")
        assert meta["date"] is None

    def test_no_tier_returns_none(self):
        meta = extract_post_metadata(SINGLE_TITLE)
        assert meta["tier"] is None

    def test_single_ticker_extracted(self):
        meta = extract_post_metadata(SINGLE_TITLE)
        assert "PLTR" in meta["tickers"]

    def test_weekly_insights_no_tickers(self):
        meta = extract_post_metadata(WEEKLY_TITLE)
        # Commentary title — no $TICKER tokens
        assert meta["tickers"] == []


# ---------------------------------------------------------------------------
# TestSplitTickerBlocks
# ---------------------------------------------------------------------------

MULTI_BODY = strip_chrome(MULTI_RAW)
SINGLE_BODY = strip_chrome(SINGLE_RAW)


class TestSplitTickerBlocks:

    def test_numbered_blocks(self):
        """multi_ticker body should yield exactly 4 blocks."""
        blocks = split_ticker_blocks(MULTI_BODY)
        assert len(blocks) == 4

    def test_block_ticker_hints(self):
        hints = [b["ticker_hint"] for b in split_ticker_blocks(MULTI_BODY)]
        assert hints == ["AAOI", "LITE", "COHR", "CIEN"]

    def test_block_text_contains_data(self):
        blocks = split_ticker_blocks(MULTI_BODY)
        assert "107.45" in blocks[0]["text"]
        assert "772.29" in blocks[1]["text"]

    def test_single_ticker_no_number(self):
        """Single-ticker post returns one block with ticker_hint=None."""
        blocks = split_ticker_blocks(SINGLE_BODY)
        assert len(blocks) == 1
        assert blocks[0]["ticker_hint"] is None

    def test_single_block_text_contains_data(self):
        blocks = split_ticker_blocks(SINGLE_BODY)
        assert "128.06" in blocks[0]["text"]


# ---------------------------------------------------------------------------
# TestExtractTickerFields
# ---------------------------------------------------------------------------

# Use the raw block text as it appears in the fixture (after strip_chrome)
AAOI_TEXT = split_ticker_blocks(MULTI_BODY)[0]["text"]
LITE_TEXT = split_ticker_blocks(MULTI_BODY)[1]["text"]
COHR_TEXT = split_ticker_blocks(MULTI_BODY)[2]["text"]
CIEN_TEXT = split_ticker_blocks(MULTI_BODY)[3]["text"]
PLTR_TEXT = split_ticker_blocks(SINGLE_BODY)[0]["text"]


class TestExtractTickerFields:

    # --- Closing price ---

    def test_closing_price(self):
        f = extract_ticker_fields(AAOI_TEXT)
        assert f["closing_price"] == pytest.approx(107.45)

    def test_closing_price_pltr(self):
        f = extract_ticker_fields(PLTR_TEXT)
        assert f["closing_price"] == pytest.approx(128.06)

    # --- Support levels ---

    def test_support_levels(self):
        f = extract_ticker_fields(AAOI_TEXT)
        # Raw string like "$83, $94, $102, $105"
        assert "83" in f["support"]
        assert "105" in f["support"]

    def test_support_levels_pltr(self):
        f = extract_ticker_fields(PLTR_TEXT)
        assert "107" in f["support"]
        assert "123" in f["support"]

    # --- Resistance levels ---

    def test_resistance_levels(self):
        f = extract_ticker_fields(AAOI_TEXT)
        assert "115" in f["resistance"]
        assert "129" in f["resistance"]

    def test_resistance_levels_pltr(self):
        f = extract_ticker_fields(PLTR_TEXT)
        assert "131" in f["resistance"]
        assert "140" in f["resistance"]

    # --- Whale accumulation ---

    def test_whale_accumulation_increased(self):
        f = extract_ticker_fields(AAOI_TEXT)
        assert f["whale_pct"] == pytest.approx(87.08)
        assert f["whale_direction"] == "increased"

    def test_whale_accumulation_decreased(self):
        f = extract_ticker_fields(PLTR_TEXT)
        assert f["whale_pct"] == pytest.approx(58.25)
        assert f["whale_direction"] == "decreased"

    def test_whale_accumulation_steady(self):
        f = extract_ticker_fields(CIEN_TEXT)
        assert f["whale_pct"] == pytest.approx(96.5)
        assert f["whale_direction"] == "steady"

    def test_whale_invisible(self):
        text = "Whale Accumulation: Invisible\nClosing Price: $50.00\n"
        f = extract_ticker_fields(text)
        assert f["whale_pct"] == 0.0
        assert f["needs_review"] is True

    # --- Technical indicators ---

    def test_technical_indicators(self):
        f = extract_ticker_fields(PLTR_TEXT)
        assert f["macd_rsi"] is not None
        assert "curling down" in f["macd_rsi"].lower()

    def test_technical_indicators_utf8_artifact(self):
        """The Â (0xC2) artifact before 'Technical Indicators:' must be stripped."""
        f = extract_ticker_fields(AAOI_TEXT)
        assert f["macd_rsi"] is not None
        assert "\xc2" not in f["macd_rsi"]
        assert "Â" not in f["macd_rsi"]

    def test_macd_rsi_length_limit(self):
        f = extract_ticker_fields(AAOI_TEXT)
        assert len(f["macd_rsi"]) <= FIELD_LIMITS["macd_rsi"]

    # --- Candle signals ---

    def test_red_candle_detected(self):
        """AAOI text explicitly says 'bullish red candle today'."""
        f = extract_ticker_fields(AAOI_TEXT)
        assert f["red_daily"] is True

    def test_weekly_red_candle_detected(self):
        text = (
            "Closing Price: $100.00\n"
            "Support Levels: $90\n"
            "Resistance Levels: $110\n"
            "Whale Accumulation: increased to 70.0%\n"
            "Technical Indicators: MACD is flat.\n"
            "The red candle on the weekly chart remains valid.\n"
        )
        f = extract_ticker_fields(text)
        assert f["red_weekly"] is True

    def test_yellow_candle_detected(self):
        """PLTR fixture has 'yellow candle' on weekly chart."""
        f = extract_ticker_fields(PLTR_TEXT)
        assert f["yellow_weekly"] is True

    def test_golden_cross_detected(self):
        text = (
            "Closing Price: $200.00\n"
            "Support Levels: $190\n"
            "Resistance Levels: $210\n"
            "Whale Accumulation: increased to 80.0%\n"
            "Technical Indicators: A golden cross formed on the daily chart.\n"
        )
        f = extract_ticker_fields(text)
        assert f["golden_cross"] is True

    def test_golden_cross_not_detected_when_absent(self):
        f = extract_ticker_fields(AAOI_TEXT)
        assert f["golden_cross"] is False

    # --- Invalidation level ---

    def test_invalidation_level(self):
        """AAOI text: 'closing below $105.1 would invalidate the bullish setup'."""
        f = extract_ticker_fields(AAOI_TEXT)
        assert f["invalidation"] is not None
        assert "105.1" in f["invalidation"]

    def test_invalidation_absent_returns_none(self):
        text = (
            "Closing Price: $128.06\n"
            "Support Levels: $107, $118, $123\n"
            "Resistance Levels: $131, $135, $140\n"
            "Whale Accumulation: decreased to 58.25%\n"
            "Technical Indicators: MACD and RSI are curling down.\n"
        )
        f = extract_ticker_fields(text)
        assert f["invalidation"] is None

    # --- needs_review flag ---

    def test_missing_whale_sets_needs_review(self):
        text = "Closing Price: $50.00\nSupport Levels: $40\nResistance Levels: $60\n"
        f = extract_ticker_fields(text)
        assert f["needs_review"] is True

    def test_missing_price_sets_needs_review(self):
        text = (
            "Support Levels: $40\nResistance Levels: $60\n"
            "Whale Accumulation: increased to 70.0%\n"
        )
        f = extract_ticker_fields(text)
        assert f["needs_review"] is True

    def test_complete_fields_no_review(self):
        text = (
            "Closing Price: $107.45\n"
            "Support Levels: $83, $94\n"
            "Resistance Levels: $115, $129\n"
            "Whale Accumulation: increased to 87.08%\n"
            "Technical Indicators: MACD and RSI are flattening.\n"
        )
        f = extract_ticker_fields(text)
        assert f["needs_review"] is False


# ---------------------------------------------------------------------------
# TestParseRawPost
# ---------------------------------------------------------------------------

class TestParseRawPost:

    def test_multi_ticker_file(self):
        result = parse_raw_post(MULTI_RAW, post_id="154978919")
        assert result["post_id"] == "154978919"
        assert result["skipped_reason"] is None
        assert len(result["observations"]) == 4
        symbols = [o["symbol"] for o in result["observations"]]
        assert "AAOI" in symbols
        assert "CIEN" in symbols

    def test_multi_ticker_closing_prices(self):
        result = parse_raw_post(MULTI_RAW, post_id="154978919")
        by_sym = {o["symbol"]: o for o in result["observations"]}
        assert by_sym["AAOI"]["closing_price"] == pytest.approx(107.45)
        assert by_sym["LITE"]["closing_price"] == pytest.approx(772.29)
        assert by_sym["COHR"]["closing_price"] == pytest.approx(253.22)
        assert by_sym["CIEN"]["closing_price"] == pytest.approx(434.26)

    def test_single_ticker_file(self):
        result = parse_raw_post(SINGLE_RAW, post_id="155338136")
        assert result["post_id"] == "155338136"
        assert result["skipped_reason"] is None
        assert len(result["observations"]) == 1
        obs = result["observations"][0]
        assert obs["symbol"] == "PLTR"
        assert obs["closing_price"] == pytest.approx(128.06)

    def test_no_ticker_file(self):
        result = parse_raw_post(NO_TICKER_RAW, post_id="weekly_insights_001")
        assert result["skipped_reason"] == "no_ticker_data"
        assert result["observations"] == []

    def test_no_navigation_chrome_in_output(self):
        """Observations must not contain Patreon nav strings."""
        result = parse_raw_post(MULTI_RAW, post_id="154978919")
        for obs in result["observations"]:
            for v in obs.values():
                if isinstance(v, str):
                    assert "Related posts" not in v
                    assert "Get more out of every post" not in v

    def test_no_boilerplate_in_output(self):
        """No BOILERPLATE_PHRASES should appear anywhere in observation string fields."""
        result = parse_raw_post(MULTI_RAW, post_id="154978919")
        for obs in result["observations"]:
            for phrase in BOILERPLATE_PHRASES:
                for v in obs.values():
                    if isinstance(v, str):
                        assert phrase not in v

    def test_date_extracted(self):
        result = parse_raw_post(MULTI_RAW, post_id="154978919")
        assert result["date"] == "2026-04-07"

    def test_single_ticker_date(self):
        result = parse_raw_post(SINGLE_RAW, post_id="155338136")
        assert result["date"] == "2026-04-11"

    def test_symbol_length_limit(self):
        result = parse_raw_post(MULTI_RAW, post_id="154978919")
        for obs in result["observations"]:
            assert len(obs["symbol"]) <= FIELD_LIMITS["symbol"]

    def test_macd_rsi_length_limit_in_observations(self):
        result = parse_raw_post(MULTI_RAW, post_id="154978919")
        for obs in result["observations"]:
            if obs.get("macd_rsi"):
                assert len(obs["macd_rsi"]) <= FIELD_LIMITS["macd_rsi"]


# ---------------------------------------------------------------------------
# Constants smoke tests
# ---------------------------------------------------------------------------

class TestConstants:

    def test_boilerplate_phrases_defined(self):
        assert isinstance(BOILERPLATE_PHRASES, list)
        assert len(BOILERPLATE_PHRASES) >= 2
        assert "Get more out of every post" in BOILERPLATE_PHRASES

    def test_field_limits_defined(self):
        for key in ("symbol", "sector", "signal", "macd_rsi"):
            assert key in FIELD_LIMITS
            assert isinstance(FIELD_LIMITS[key], int)

    def test_max_cell_length_defined(self):
        assert MAX_CELL_LENGTH == 500


# ---------------------------------------------------------------------------
# Task 3: Batch Structured Markdown Writer
# ---------------------------------------------------------------------------

_SAMPLE_OBS = {
    "symbol": "AAOI",
    "date": "2026-04-07",
    "post_id": "154978919",
    "closing_price": 107.45,
    "support": "$83, $94, $102, $105",
    "resistance": "$115, $129",
    "whale_pct": 87.08,
    "whale_direction": "increased",
    "macd_rsi": "MACD and RSI are flattening",
    "red_daily": True,
    "red_weekly": False,
    "red_monthly": False,
    "yellow_daily": False,
    "yellow_weekly": False,
    "golden_cross": False,
    "invalidation": "$105.1",
    "needs_review": False,
}

_SAMPLE_TITLE = "TIER 3 title here"


class TestFormatBatchEntry:

    def test_single_observation_format(self):
        """Output must contain the section header and the table row."""
        md = format_batch_entry(_SAMPLE_OBS, _SAMPLE_TITLE)
        assert "## 2026-04-07" in md
        assert "$AAOI" in md
        assert "154978919" in md
        assert "$107.45" in md
        assert "87.08%" in md

    def test_table_header_columns(self):
        """Exactly 7 columns: Ticker, Close, Support, Resistance, Whale Accum, MACD/RSI, Signal."""
        md = format_batch_entry(_SAMPLE_OBS, _SAMPLE_TITLE)
        assert "| Ticker | Close | Support | Resistance | Whale Accum | MACD/RSI | Signal |" in md

    def test_no_cell_exceeds_500_chars(self):
        """No table cell in the output should exceed 500 chars."""
        obs = dict(_SAMPLE_OBS)
        obs["macd_rsi"] = "X" * 600
        obs["support"] = "Y" * 600
        md = format_batch_entry(obs, _SAMPLE_TITLE)
        for line in md.split("\n"):
            if not line.startswith("|"):
                continue
            cells = line.split("|")[1:-1]
            for cell in cells:
                assert len(cell.strip()) <= MAX_CELL_LENGTH

    def test_signal_summary_max_120_chars(self):
        """The Signal Summary line must be ≤ 120 chars of signal text."""
        obs = dict(_SAMPLE_OBS)
        obs["signal"] = "A" * 200
        md = format_batch_entry(obs, _SAMPLE_TITLE)
        for line in md.split("\n"):
            if line.startswith("**Signal Summary:**"):
                summary_text = line[len("**Signal Summary:** "):]
                assert len(summary_text) <= 120


class TestWriteBatchFile:

    def test_writes_file(self, tmp_path):
        out = tmp_path / "batch.md"
        result = write_batch_file(
            [_SAMPLE_OBS],
            {"154978919": "TIER 3 title"},
            str(out),
            "2026-04-07",
        )
        assert result == str(out)
        assert out.exists()

    def test_file_contains_header(self, tmp_path):
        out = tmp_path / "batch.md"
        write_batch_file([_SAMPLE_OBS], {}, str(out), "2026-04-07")
        content = out.read_text()
        assert "2026-04-07" in content
        assert "AAOI" in content


# ---------------------------------------------------------------------------
# Task 4: Watchlist Reader / Writer / Merge
# ---------------------------------------------------------------------------

WATCHLIST_FIXTURE = FIXTURES / "watchlist_baseline.md"


class TestReadWatchlist:

    def test_reads_existing_watchlist(self):
        """Should return > 40 rows and SNDK should be first at 98.98%."""
        rows = read_watchlist(str(WATCHLIST_FIXTURE))
        assert len(rows) > 40
        first = rows[0]
        assert first["symbol"] == "SNDK"
        assert first["whale_pct"] == pytest.approx(98.98)

    def test_parses_all_columns(self):
        """Every row must have all required keys with non-None values for SNDK."""
        rows = read_watchlist(str(WATCHLIST_FIXTURE))
        sndk = next(r for r in rows if r["symbol"] == "SNDK")
        assert sndk["rank"] == 1
        assert sndk["sector"] == "Semiconductor/Storage"
        assert sndk["latest_close"] == pytest.approx(851.57)
        assert sndk["whale_pct"] == pytest.approx(98.98)
        assert sndk["macd_rsi"] is not None
        assert sndk["signal"] is not None
        assert sndk["trend"] is not None

    def test_parses_wkly_annotation(self):
        """'98.9% (wkly)' should parse to 98.9 (annotation stripped)."""
        rows = read_watchlist(str(WATCHLIST_FIXTURE))
        wulf = next(r for r in rows if r["symbol"] == "WULF")
        assert wulf["whale_pct"] == pytest.approx(98.9)

    def test_parses_invisible(self):
        """'Invisible' whale accum should parse to 0.0."""
        rows = read_watchlist(str(WATCHLIST_FIXTURE))
        shop = next(r for r in rows if r["symbol"] == "SHOP")
        assert shop["whale_pct"] == pytest.approx(0.0)


class TestMergeWatchlist:

    def _base(self):
        return [
            {"rank": 1, "symbol": "AAOI", "sector": "Photonics", "latest_close": 107.45,
             "whale_pct": 87.08, "macd_rsi": "Flattening", "signal": "Red candle",
             "trend": "Rising", "date": "2026-04-07"},
            {"rank": 2, "symbol": "PLTR", "sector": "AI/Software", "latest_close": 128.06,
             "whale_pct": 58.25, "macd_rsi": "Curling down", "signal": "Yellow candle",
             "trend": "Falling", "date": "2026-04-11"},
        ]

    def test_new_symbol_appended(self):
        existing = self._base()
        new_obs = [{"symbol": "NVDA", "closing_price": 200.0, "whale_pct": 90.0,
                    "macd_rsi": "Curling up", "date": "2026-04-12"}]
        result = merge_watchlist(existing, new_obs)
        symbols = [r["symbol"] for r in result]
        assert "NVDA" in symbols

    def test_existing_symbol_updated(self):
        existing = self._base()
        new_obs = [{"symbol": "AAOI", "closing_price": 133.30, "whale_pct": 95.9,
                    "macd_rsi": "Curling up", "date": "2026-04-11"}]
        result = merge_watchlist(existing, new_obs)
        aaoi = next(r for r in result if r["symbol"] == "AAOI")
        assert aaoi["latest_close"] == pytest.approx(133.30)
        assert aaoi["whale_pct"] == pytest.approx(95.9)

    def test_existing_symbol_preserves_sector(self):
        """When new obs has no sector, existing sector is preserved."""
        existing = self._base()
        new_obs = [{"symbol": "AAOI", "closing_price": 133.30, "whale_pct": 95.9,
                    "macd_rsi": "Curling up", "date": "2026-04-11"}]
        result = merge_watchlist(existing, new_obs)
        aaoi = next(r for r in result if r["symbol"] == "AAOI")
        assert aaoi["sector"] == "Photonics"

    def test_uncovered_symbols_preserved(self):
        """Symbols in existing not touched by new_obs must remain in output."""
        existing = self._base()
        new_obs = [{"symbol": "NVDA", "closing_price": 200.0, "whale_pct": 90.0,
                    "macd_rsi": "Curling up", "date": "2026-04-12"}]
        result = merge_watchlist(existing, new_obs)
        symbols = [r["symbol"] for r in result]
        assert "AAOI" in symbols
        assert "PLTR" in symbols

    def test_sorted_by_whale_pct_descending(self):
        existing = self._base()
        new_obs = [{"symbol": "NVDA", "closing_price": 200.0, "whale_pct": 99.0,
                    "macd_rsi": "Curling up", "date": "2026-04-12"}]
        result = merge_watchlist(existing, new_obs)
        pcts = [r["whale_pct"] for r in result if r.get("whale_pct") is not None]
        assert pcts == sorted(pcts, reverse=True)


class TestWriteWatchlistNext:

    def test_writes_valid_markdown(self, tmp_path):
        rows = read_watchlist(str(WATCHLIST_FIXTURE))
        out = tmp_path / "WATCHLIST_AND_TIMELINE.next.md"
        result = write_watchlist_next(rows, str(out), "April 16, 2026")
        assert result == str(out)
        content = out.read_text()
        # Must have the standard header row
        assert "| Rank | Ticker | Sector | Latest Close | Whale Accum | MACD/RSI | Latest Signal | Trend (5-day) |" in content
        # Must contain at least SNDK
        assert "SNDK" in content

    def test_writes_generated_date(self, tmp_path):
        rows = read_watchlist(str(WATCHLIST_FIXTURE))
        out = tmp_path / "watchlist_next.md"
        write_watchlist_next(rows, str(out), "April 16, 2026")
        content = out.read_text()
        assert "April 16, 2026" in content


# ---------------------------------------------------------------------------
# Task 8: Golden File + Determinism Tests
# ---------------------------------------------------------------------------

class TestGoldenWatchlist:
    def test_watchlist_golden_match(self):
        """Re-reading and re-writing the baseline watchlist produces the golden file."""
        rows = read_watchlist(str(FIXTURES / "watchlist_baseline.md"))
        merged = merge_watchlist(rows, [])
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            tmp_path = f.name
        write_watchlist_next(merged, tmp_path, "April 11, 2026")
        golden = (Path(__file__).parent / "golden" / "WATCHLIST_AND_TIMELINE.expected.md").read_text()
        actual = Path(tmp_path).read_text()
        Path(tmp_path).unlink()
        assert actual == golden, "Watchlist output does not match golden file"


class TestDeterminism:
    def test_parser_deterministic(self):
        """Same input → identical output on two runs."""
        raw = (FIXTURES / "multi_ticker.txt").read_text()
        result1 = parse_raw_post(raw, post_id="154978919")
        result2 = parse_raw_post(raw, post_id="154978919")
        assert result1 == result2


# ---------------------------------------------------------------------------
# Task 9: End-to-End Integration Test
# ---------------------------------------------------------------------------

import json
import shutil


class TestEndToEnd:
    def test_full_parse_pipeline(self, tmp_path):
        """Full pipeline: raw files → batch + watchlist + report."""
        # Set up a mini data tree
        raw_dir = tmp_path / "data" / "raw"
        structured_dir = tmp_path / "data" / "structured"
        raw_dir.mkdir(parents=True)
        structured_dir.mkdir(parents=True)

        # Copy test fixtures as raw files
        shutil.copy(FIXTURES / "multi_ticker.txt", raw_dir / "154978919.txt")
        shutil.copy(FIXTURES / "single_ticker.txt", raw_dir / "post_155338136.txt")
        shutil.copy(FIXTURES / "no_ticker.txt", raw_dir / "154703740.txt")

        # Copy baseline watchlist
        shutil.copy(FIXTURES / "watchlist_baseline.md",
                     structured_dir / "WATCHLIST_AND_TIMELINE.md")

        # Run parse
        from raw_to_structured import run_parse
        exit_code = run_parse(str(tmp_path))

        assert exit_code == 0, f"Parse failed with exit code {exit_code}"

        # Verify outputs exist
        batch_files = list(structured_dir.glob("batch*_structured*.md"))
        assert len(batch_files) >= 1, f"Expected batch file, got {len(batch_files)}"

        next_file = structured_dir / "WATCHLIST_AND_TIMELINE.next.md"
        assert next_file.exists(), ".next.md not created"

        # Report is written to {data_root}/reports/
        reports_dir = tmp_path / "reports"
        report_files = list(reports_dir.glob("parse_report_*.json"))
        assert len(report_files) == 1, f"Expected 1 report, got {len(report_files)}"

        # Verify report content
        report = json.loads(report_files[0].read_text())
        assert report["observations_count"] > 0
        assert report["needs_review_rate"] < 0.50
        assert report["watchlist_next_sha256"] is not None

        # Verify no boilerplate in batch file
        batch_content = batch_files[0].read_text()
        for phrase in ["Get more out of every post", "Related posts", "Join now"]:
            assert phrase not in batch_content, f"Boilerplate '{phrase}' in batch file"

        # Verify no cell > 500 chars
        for line in batch_content.split("\n"):
            if line.startswith("|") and "---" not in line:
                cells = [c.strip() for c in line.split("|")[1:-1]]
                for cell in cells:
                    assert len(cell) <= 500, f"Cell too long: {len(cell)}"
