"""Unit tests for scripts/scrape_julie_gmail_patreon.py.

No network. All IMAP interactions are mocked. End-to-end IMAP verification
against the real Gmail account is F8 (integration) and requires
JULIE_GMAIL_APP_PW at runtime.
"""
import json
import sys
from email.message import EmailMessage
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from scrape_julie_gmail_patreon import (
    _safe_slug,
    extract_plain_text,
    load_state,
    save_state,
    process_one,
    search_new_uids,
)

FIXTURES = Path(__file__).parent / "fixtures" / "patreon_email"


# ---------------------------------------------------------------------------
# _safe_slug
# ---------------------------------------------------------------------------

class TestSafeSlug:
    def test_preserves_alphanumeric(self):
        assert _safe_slug("ABC123") == "ABC123"

    def test_collapses_unsafe_chars(self):
        # Leading/trailing dashes stripped; inner runs collapsed to single dash.
        assert _safe_slug("$SHOP (April 22, 2026-daily)") == "SHOP-April-22-2026-daily"

    def test_caps_length(self):
        long = "a" * 200
        assert len(_safe_slug(long, cap=50)) == 50

    def test_empty_input_returns_untitled(self):
        assert _safe_slug("") == "untitled"
        assert _safe_slug("!!!") == "untitled"


# ---------------------------------------------------------------------------
# extract_plain_text
# ---------------------------------------------------------------------------

class TestExtractPlainText:
    def _multipart_fixture(self, plain: str = "plain body", html: str = "<p>html body</p>"):
        msg = EmailMessage()
        msg["From"] = "dannytrades@creator.patreon.com"
        msg["To"] = "julievilla2002@gmail.com"
        msg["Subject"] = "$SHOP (April 22, 2026-daily)"
        msg.set_content(plain)
        msg.add_alternative(html, subtype="html")
        return msg

    def test_singlepart_plain(self):
        msg = EmailMessage()
        msg["Subject"] = "test"
        msg.set_content("hello world")
        assert "hello world" in extract_plain_text(msg)

    def test_multipart_prefers_plain(self):
        msg = self._multipart_fixture(plain="THE PLAIN PART", html="<p>THE HTML PART</p>")
        text = extract_plain_text(msg)
        assert "THE PLAIN PART" in text
        assert "THE HTML PART" not in text

    def test_html_fallback_strips_tags(self):
        msg = EmailMessage()
        msg["Subject"] = "test"
        # Force html-only by direct construction
        msg.set_content("placeholder")
        msg.clear_content()
        msg.set_type("multipart/alternative")
        msg.add_alternative("<p>one</p><p>two &amp; three</p>", subtype="html")
        text = extract_plain_text(msg)
        assert "<p>" not in text
        assert "one" in text
        assert "two & three" in text  # &amp; decoded

    def test_empty_message_returns_empty(self):
        msg = EmailMessage()
        msg["Subject"] = "empty"
        assert extract_plain_text(msg) == ""


# ---------------------------------------------------------------------------
# State checkpoint
# ---------------------------------------------------------------------------

class TestStateCheckpoint:
    def test_load_missing_returns_zeroed(self, tmp_path):
        state = load_state(tmp_path / "missing.json")
        assert state["last_uid"] == 0
        assert state["uidvalidity"] is None

    def test_round_trip(self, tmp_path):
        path = tmp_path / "state.json"
        save_state(path, 1234567890, 42)
        state = load_state(path)
        assert state["uidvalidity"] == 1234567890
        assert state["last_uid"] == 42
        assert state["last_run_at"] is not None

    def test_corrupt_state_recovers(self, tmp_path):
        path = tmp_path / "state.json"
        path.write_text("not-valid-json{{{")
        state = load_state(path)
        assert state["last_uid"] == 0


# ---------------------------------------------------------------------------
# search_new_uids — IMAP protocol shape
# ---------------------------------------------------------------------------

class TestSearchNewUids:
    def test_empty_response(self):
        imap = MagicMock()
        imap.uid.return_value = ("OK", [b""])
        assert search_new_uids(imap, "x@y.com", last_uid=0, since=None) == []

    def test_returns_sorted_unique_uids(self):
        imap = MagicMock()
        imap.uid.return_value = ("OK", [b"12 5 100 100 42"])
        assert search_new_uids(imap, "x@y.com", last_uid=0, since=None) == [5, 12, 42, 100]

    def test_filters_below_last_uid(self):
        imap = MagicMock()
        # Gmail often echoes the anchor UID when querying N:*
        imap.uid.return_value = ("OK", [b"50 51 52 53"])
        assert search_new_uids(imap, "x@y.com", last_uid=50, since=None) == [51, 52, 53]

    def test_raises_on_nonok_status(self):
        imap = MagicMock()
        imap.uid.return_value = ("NO", [b"permission denied"])
        with pytest.raises(RuntimeError, match="UID SEARCH failed"):
            search_new_uids(imap, "x@y.com", last_uid=0, since=None)


# ---------------------------------------------------------------------------
# process_one — full per-message path
# ---------------------------------------------------------------------------

class TestProcessOne:
    @pytest.fixture
    def shop_message(self) -> EmailMessage:
        """A multipart email whose plain-text part is the real $SHOP body."""
        body = (FIXTURES / "shop_2026_04_22_daily.txt").read_text()
        msg = EmailMessage()
        msg["From"] = "DannyTrades <dannytrades@creator.patreon.com>"
        msg["To"] = "julievilla2002@gmail.com"
        msg["Subject"] = "$SHOP (April 22, 2026-daily)"
        msg["Date"] = "Tue, 22 Apr 2026 05:10:00 +0000"
        msg.set_content(body)
        msg.add_alternative("<html><body>" + body + "</body></html>", subtype="html")
        return msg

    def test_writes_raw_and_obs_files(self, shop_message, tmp_path):
        result = process_one(shop_message, uid=42, out_root=tmp_path, dry_run=False)
        assert result.uid == 42
        assert result.post_type == "analysis"
        assert result.observations_count == 1
        raw = Path(result.raw_path)
        obs = Path(result.obs_path)
        assert raw.exists() and raw.suffix == ".eml"
        assert obs.exists() and obs.suffix == ".json"

    def test_dry_run_writes_nothing(self, shop_message, tmp_path):
        result = process_one(shop_message, uid=42, out_root=tmp_path, dry_run=True)
        assert result.post_type == "analysis"
        assert result.observations_count == 1
        assert result.raw_path is None
        assert result.obs_path is None
        # Nothing written to disk
        assert list(tmp_path.rglob("*.eml")) == []
        assert list(tmp_path.rglob("*.json")) == []

    def test_obs_json_schema(self, shop_message, tmp_path):
        result = process_one(shop_message, uid=99, out_root=tmp_path, dry_run=False)
        payload = json.loads(Path(result.obs_path).read_text())
        # Must carry every field the downstream importer needs
        for k in ("uid", "subject", "date_header", "email_date",
                  "post_type", "title", "metadata", "observations"):
            assert k in payload, f"missing key {k}"
        assert payload["uid"] == 99
        assert payload["post_type"] == "analysis"
        assert payload["metadata"]["tickers"] == ["SHOP"]
        obs = payload["observations"][0]
        assert obs["symbol"] == "SHOP"
        assert obs["closing_price"] == 131.13
        assert obs["whale_pct"] == 53.1

    def test_output_layout_by_year_month(self, shop_message, tmp_path):
        result = process_one(shop_message, uid=7, out_root=tmp_path, dry_run=False)
        # Apr 22, 2026 → 2026-04
        assert "/2026-04/" in result.raw_path
        assert "/2026-04/" in result.obs_path
        # Filename carries zero-padded UID + slug
        assert "00000007_" in Path(result.raw_path).name

    def test_undated_message_goes_to_undated_dir(self, tmp_path):
        msg = EmailMessage()
        msg["From"] = "dannytrades@creator.patreon.com"
        msg["Subject"] = "$FOO (hi)"
        msg.set_content("analysis body")
        result = process_one(msg, uid=1, out_root=tmp_path, dry_run=False)
        assert "/undated/" in result.raw_path
