"""Unit tests for scripts/parse_email.py.

Covers both email source shapes we actually see in the wild:
  - Native Patreon notifications from dannytrades@creator.patreon.com
    (Julie's inbox via the IMAP scraper) — the subject comes from
    the email header, the body has a single unnumbered "TICKER Analysis:"
    heading followed by the analysis fields.
  - Legacy forwarded emails (Julie → David) — contain a
    "---- Forwarded message ----" header block with an inline Subject: line.

The native-email path is the primary production path going forward.
The forwarded path is preserved for backward compatibility.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import pytest
from parse_email import parse_email, clean_email_body

FIXTURES = Path(__file__).parent / "fixtures" / "patreon_email"


# --- Native Patreon notification ---------------------------------------------


class TestNativePatreonEmail:
    """dannytrades@creator.patreon.com single-ticker notifications."""

    @pytest.fixture
    def shop_body(self):
        return (FIXTURES / "shop_2026_04_22_daily.txt").read_text()

    def test_explicit_subject_beats_body_extraction(self, shop_body):
        """When called with subject kwarg, native-email path must be taken."""
        result = parse_email(shop_body, subject="$SHOP (April 22, 2026-daily)")
        assert result["title"] == "$SHOP (April 22, 2026-daily)"
        assert result["post_type"] == "analysis"

    def test_metadata_extracts_from_subject(self, shop_body):
        result = parse_email(shop_body, subject="$SHOP (April 22, 2026-daily)")
        assert result["metadata"]["tickers"] == ["SHOP"]
        assert result["metadata"]["date"] == "2026-04-22"

    def test_single_ticker_produces_one_observation(self, shop_body):
        result = parse_email(shop_body, subject="$SHOP (April 22, 2026-daily)")
        assert len(result["observations"]) == 1
        assert result["observations"][0]["symbol"] == "SHOP"

    def test_all_fields_extracted(self, shop_body):
        result = parse_email(shop_body, subject="$SHOP (April 22, 2026-daily)")
        obs = result["observations"][0]
        assert obs["closing_price"] == 131.13
        assert obs["support"] == "$118, $129"
        assert obs["resistance"] == "$137, $145"
        assert obs["whale_pct"] == 53.1
        assert obs["whale_direction"] == "decreased"
        assert obs["invalidation"] == "$109.32"
        assert "MACD" in obs["macd_rsi"]

    def test_analysis_content_survives_clean(self, shop_body):
        """Regression guard for the DOTALL bug: clean_email_body previously
        ate the entire analysis because "View in app.*" matched through the
        end of body. This test fails if that regression returns."""
        _, cleaned = clean_email_body(shop_body)
        assert "Analysis:" in cleaned
        assert "Closing price" in cleaned
        assert "Whale Accumulation" in cleaned
        assert "131.13" in cleaned

    def test_footer_stripped(self, shop_body):
        _, cleaned = clean_email_body(shop_body)
        # These boilerplate lines should be stripped
        assert "Did you like this post?" not in cleaned
        assert "© 2026 DannyTrades" not in cleaned
        assert "Unsubscribe" not in cleaned


# --- Legacy forwarded-email backward compat ---------------------------------


class TestForwardedEmailBackwardCompat:
    """Legacy path — emails forwarded from Julie to David with a
    ---- Forwarded message ---- block and an inline Subject: line."""

    def test_forwarded_block_header_extracts_title(self):
        body = (
            "---------- Forwarded message ----------\n"
            "From: Patreon <no-reply@patreon.com>\n"
            "Subject: Fwd: $AMD Analysis\n"
            "\n"
            "1. AMD Analysis:\n"
            "\n"
            "Closing Price: $274.95\n"
            "Support Levels: $260, $250\n"
            "Resistance Levels: $290, $310\n"
            "Whale Accumulation: increased to 94.5%\n"
        )
        result = parse_email(body)
        assert result["title"] == "$AMD Analysis"
        assert result["post_type"] == "analysis"
        assert len(result["observations"]) == 1
        obs = result["observations"][0]
        assert obs["symbol"] == "AMD"
        assert obs["closing_price"] == 274.95
        assert obs["whale_pct"] == 94.5

    def test_numbered_multi_ticker_blocks(self):
        """Multi-ticker posts use `1. TICKER Analysis:` / `2. TICKER Analysis:`."""
        body = (
            "Subject: $AAOI, $LITE (April 7, 2026-daily)\n"
            "\n"
            "1. AAOI Analysis:\n"
            "Closing Price: $107.45\n"
            "Whale Accumulation: steady at 95.8%\n"
            "\n"
            "2. LITE Analysis:\n"
            "Closing Price: $772.29\n"
            "Whale Accumulation: increased to 95.0%\n"
        )
        result = parse_email(body)
        syms = sorted(o["symbol"] for o in result["observations"])
        assert syms == ["AAOI", "LITE"]
