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
