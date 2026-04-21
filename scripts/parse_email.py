#!/usr/bin/env python3
"""
parse_email.py — Parse DannyTrades Patreon notification emails into structured data.

Alternative to Playwright scraping. Works on forwarded email plaintext bodies.
Reuses the same regex extraction engine as raw_to_structured.py.

Usage:
    # Parse from a file:
    python parse_email.py --file /path/to/email_body.txt

    # Parse from stdin (pipe from Gmail API, etc.):
    echo "..." | python parse_email.py --stdin

    # Parse and import to PG:
    python parse_email.py --file email.txt --import

DIR-T89-DANNYTRADES-QUOTE-001
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Add parent dir for imports
sys.path.insert(0, str(Path(__file__).parent))

from raw_to_structured import (
    extract_post_metadata,
    extract_ticker_fields,
    _BLOCK_HEADER_RE,
)

# ---------------------------------------------------------------------------
# Email-specific cleaners
# ---------------------------------------------------------------------------

# Patreon email boilerplate patterns
_EMAIL_BOILERPLATE = [
    r"Did you like this post\?.*",
    r"Share this post with someone.*",
    r"© \d{4} DannyTrades.*",
    r"Privacy policy.*",
    r"Terms of use.*",
    r"600 Townsend Street.*",
    r"San Francisco, CA.*",
    r"Email was sent to.*",
    r"Unsubscribe.*",
    r"Manage your email settings.*",
    r"Download the app.*",
    r"Google Play.*",
    r"App Store.*",
    r"View in app.*",
    r"\[image:.*?\]",
]

# Forwarded message header
_FWD_HEADER_RE = re.compile(
    r"-+\s*Forwarded message\s*-+.*?(?=\n\n|\n\*?\d+[.\)])",
    re.DOTALL | re.IGNORECASE,
)

# Dr Cat sections to exclude
_DR_CAT_RE = re.compile(
    r"Dr\s+Cat'?s?\s+Video\s+Insights?\s+on\s+\w+.*?(?=\n\*?\d+[.\)]\s*[A-Z]|\Z)",
    re.DOTALL | re.IGNORECASE,
)

# URL patterns (Patreon links in email)
_URL_RE = re.compile(r"https?://\S+")

# "for viewing only" filter
_VIEWING_ONLY_RE = re.compile(r"for viewing only", re.IGNORECASE)


def clean_email_body(raw: str) -> tuple[str, str]:
    """Clean email body, return (title, body).

    Extracts the subject/title from the forwarded message header,
    then strips all email boilerplate and Patreon chrome.
    """
    # Extract title from Subject line in forwarded header
    title = ""
    subject_match = re.search(r"Subject:\s*(.+?)(?:\n|$)", raw)
    if subject_match:
        title = subject_match.group(1).strip()
        # Remove "Fwd: " prefix
        title = re.sub(r"^(?:Fwd?|Re):\s*", "", title, flags=re.IGNORECASE)

    # Remove forwarded message header block
    body = _FWD_HEADER_RE.sub("", raw)

    # Remove all URLs
    body = _URL_RE.sub("", body)

    # Remove [image: ...] tags
    body = re.sub(r"\[image:\s*\w+\]", "", body)

    # Remove email boilerplate
    for pattern in _EMAIL_BOILERPLATE:
        body = re.sub(pattern, "", body, flags=re.DOTALL | re.IGNORECASE)

    # Remove Dr Cat video insight sections (keep the stock analysis)
    body = re.sub(
        r"Dr\s+Cat'?s?\s+Video\s+Insights?\s+on\s+\w+\s*\n?",
        "",
        body,
        flags=re.IGNORECASE,
    )
    # Remove YouTube links (Dr Cat videos)
    body = re.sub(r"https?://(?:www\.)?youtube\.com/\S+", "", body)

    # Collapse multiple blank lines
    body = re.sub(r"\n{3,}", "\n\n", body)

    return title.strip(), body.strip()


def parse_email(raw_text: str) -> dict:
    """Parse a DannyTrades email body into structured data.

    Returns:
        {
            "post_type": "analysis" | "editorial" | "viewing_only",
            "title": str,
            "metadata": { date, tickers, tier, timeframes },
            "observations": [ { symbol, price, support, resistance, whale_pct, ... } ],
            "raw_cleaned": str,
        }
    """
    # Check for "for viewing only"
    if _VIEWING_ONLY_RE.search(raw_text):
        return {
            "post_type": "viewing_only",
            "title": "",
            "metadata": {},
            "observations": [],
            "raw_cleaned": "",
        }

    title, body = clean_email_body(raw_text)

    # Extract metadata from title
    metadata = extract_post_metadata(title) if title else {}

    # Check if this is an editorial (no numbered stock analysis blocks)
    blocks = list(_BLOCK_HEADER_RE.finditer(body))
    if not blocks:
        return {
            "post_type": "editorial",
            "title": title,
            "metadata": metadata,
            "observations": [],
            "raw_cleaned": body,
        }

    # Parse each numbered stock analysis block
    observations = []
    for i, match in enumerate(blocks):
        symbol = match.group(2).upper()

        # Skip Dr Cat entries
        if "DR CAT" in symbol.upper() or "DRCAT" in symbol.upper():
            continue

        # Extract block text (from this header to next header or end)
        start = match.end()
        end = blocks[i + 1].start() if i + 1 < len(blocks) else len(body)
        block_text = body[start:end]

        # Skip if block mentions "Dr Cat" prominently
        if re.search(r"Dr\s+Cat'?s?\s+(?:Analysis|Video|Insights)", block_text, re.IGNORECASE):
            # Only skip if the ENTIRE block is Dr Cat's — check if there's
            # still stock analysis data (price, whale, support)
            has_price = re.search(r"Closing Price|Close[d]?\s+at", block_text, re.IGNORECASE)
            has_whale = re.search(r"Whale\s+Accumulation", block_text, re.IGNORECASE)
            if not has_price and not has_whale:
                continue

        # Use the existing field extractor
        fields = extract_ticker_fields(block_text)
        fields["symbol"] = symbol
        fields["block_number"] = int(match.group(1))
        observations.append(fields)

    return {
        "post_type": "analysis",
        "title": title,
        "metadata": metadata,
        "observations": observations,
        "raw_cleaned": body,
    }


def format_report(result: dict) -> str:
    """Format parsed result as a human-readable report."""
    lines = []
    lines.append(f"Post Type: {result['post_type']}")
    lines.append(f"Title: {result['title']}")

    if result['metadata']:
        m = result['metadata']
        lines.append(f"Date: {m.get('date', '—')}")
        lines.append(f"Tickers in title: {', '.join(m.get('tickers', []))}")
        lines.append(f"Tier: {m.get('tier', '—')}")
        lines.append(f"Timeframes: {', '.join(m.get('timeframes', []))}")

    if result['observations']:
        lines.append(f"\n{'='*70}")
        lines.append(f"Observations: {len(result['observations'])}")
        lines.append(f"{'='*70}")
        for obs in result['observations']:
            lines.append(f"\n  [{obs.get('block_number', '?')}] {obs['symbol']}")
            lines.append(f"      Price:      ${obs.get('closing_price', '—')}")
            lines.append(f"      Support:    {obs.get('support', '—')}")
            lines.append(f"      Resistance: {obs.get('resistance', '—')}")
            lines.append(f"      Whale %:    {obs.get('whale_pct', '—')}%  ({obs.get('whale_direction', '—')})")
            lines.append(f"      Red Daily:  {obs.get('red_daily', False)}")
            lines.append(f"      Red Weekly: {obs.get('red_weekly', False)}")
            lines.append(f"      Golden X:   {obs.get('golden_cross', False)}")
            lines.append(f"      Technicals: {obs.get('macd_rsi', '—')}")
    else:
        lines.append("\nNo stock observations found (editorial or viewing-only post)")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Parse DannyTrades email")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", type=str, help="Path to email body text file")
    group.add_argument("--stdin", action="store_true", help="Read from stdin")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    if args.stdin:
        raw = sys.stdin.read()
    else:
        raw = Path(args.file).read_text()

    result = parse_email(raw)

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(format_report(result))


if __name__ == "__main__":
    main()
