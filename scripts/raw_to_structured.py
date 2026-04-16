"""
raw_to_structured.py — Deterministic regex parser for DannyTrades Patreon post dumps.
NO LLM.  All extraction via regex + string operations.
"""
from __future__ import annotations

import re
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BOILERPLATE_PHRASES = [
    "Get more out of every post",
    "Related posts",
    "Join now",
    "Open app",
]

FIELD_LIMITS = {
    "symbol": 12,
    "sector": 80,
    "signal": 120,
    "macd_rsi": 120,
}

MAX_CELL_LENGTH = 500

# Nav items that appear at the top of every scraped Patreon page
_NAV_ITEMS = ["DannyTrades", "Home", "Posts", "Collections", "Shop",
              "Membership", "Recommendations", "Gift"]

# Month name → zero-padded month number
_MONTH_MAP = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
}

# Regex: "April 7, 2026" or "April 11, 2026"
_DATE_RE = re.compile(
    r"\((?P<month>[A-Za-z]+)\s+(?P<day>\d{1,2}),\s*(?P<year>\d{4})",
)

# Regex: "$TICKER" — captures tickers from title
_TICKER_TITLE_RE = re.compile(r"\$([A-Z]{1,6})")

# Regex: tier number
_TIER_RE = re.compile(r"\bTIER\s+(\d+)\b", re.IGNORECASE)

# Timeframe keywords
_TIMEFRAME_RE = re.compile(r"\b(daily|weekly|monthly)\b", re.IGNORECASE)

# Numbered ticker block header: "1.AAOI Analysis:" or "1. AAOI Analysis:"
_BLOCK_HEADER_RE = re.compile(
    r"(?m)^\s*(\d+)\s*[.)\-]\s*([A-Z]{1,6})\s+Analysis\s*:",
)

# Field regexes for extract_ticker_fields
_PRICE_RE = re.compile(r"Closing Price\s*:\s*\$([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)
_SUPPORT_RE = re.compile(r"Support (?:Levels?|Level)\s*:\s*(.+)", re.IGNORECASE)
_RESISTANCE_RE = re.compile(r"Resistance (?:Levels?|Level)\s*:\s*(.+)", re.IGNORECASE)

# Whale accumulation:
# "increased to 87.08%"  /  "decreased to 58.25% (weekly chart)"  /  "remained steady at 96.5%"
_WHALE_RE = re.compile(
    r"Whale\s+[Aa]ccumulation\s*:\s*"
    r"(?P<dir>increased to|decreased to|remained steady at|steady at|Invisible)?"
    r"\s*(?P<pct>[0-9]+(?:\.[0-9]+)?)?\s*%?",
    re.IGNORECASE,
)

# Technical indicators line — strip leading \xc2 (Â) artifact
_TECH_RE = re.compile(
    r"[\xc2\u00c2]*\s*[Tt]echnical\s+[Ii]ndicators\s*:?\s*[\xc2\u00c2]*\s*(.+)",
)

# Candle signals
_RED_DAILY_RE = re.compile(r"\bred\s+candle\b(?! on the weekly)(?! on the monthly)(?! on weekly)(?! on monthly)", re.IGNORECASE)
_RED_WEEKLY_RE = re.compile(r"\bred\s+candle\b.*?\b(weekly|on weekly|on the weekly)\b|\b(weekly|on the weekly)\b.*?\bred\s+candle\b", re.IGNORECASE)
_RED_MONTHLY_RE = re.compile(r"\bred\s+candle\b.*?\b(monthly|on monthly|on the monthly)\b|\b(monthly|on the monthly)\b.*?\bred\s+candle\b", re.IGNORECASE)

_YELLOW_DAILY_RE = re.compile(r"\byellow\s+candle\b(?!.*\b(weekly|monthly)\b)", re.IGNORECASE)
_YELLOW_WEEKLY_RE = re.compile(r"\byellow\s+candle\b.*?\b(weekly)\b|\b(weekly)\b.*?\byellow\s+candle\b", re.IGNORECASE)

_GOLDEN_CROSS_RE = re.compile(r"\bgolden\s+cross\b", re.IGNORECASE)

# Invalidation: "below $105.1 would invalidate" or "close below $105.1"
_INVALIDATION_RE = re.compile(
    r"(?:close\s+below|below)\s+\$([0-9]+(?:\.[0-9]+)?)\s+would\s+invalidate",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# strip_chrome
# ---------------------------------------------------------------------------

def strip_chrome(raw: str) -> str:
    """Remove Patreon navigation chrome from top and bottom of raw text."""
    lines = raw.split("\n")

    # --- Strip top nav ---
    # The nav block is: DannyTrades, Home, Posts, Collections, Shop, Membership,
    # Recommendations, Gift, followed by a post count digit and then the title.
    # Strategy: find the index where the actual title starts by skipping nav tokens
    # and any bare numeric lines / timestamps.

    nav_set = set(n.lower() for n in _NAV_ITEMS)
    # Patterns for lines we want to skip in the header zone
    _skip_header_re = re.compile(
        r"^\s*(?:\d+|new|\d+\s+hours?\s+ago|\d+\s+days?\s+ago|yesterday|just now|\d+\s+minutes?\s+ago)\s*$",
        re.IGNORECASE,
    )

    start_idx = 0
    # Skip lines that are navigation items or bare numbers/timestamps
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.lower() in nav_set:
            continue
        if _skip_header_re.match(stripped):
            continue
        if stripped == "":
            continue
        # First non-nav, non-empty line that isn't a bare number
        start_idx = i
        break

    # --- Strip bottom boilerplate ---
    # Cutoff patterns: "Related posts", "Get more out of every post",
    # or a comments section starting with "N comments" or comment usernames.
    _bottom_re = re.compile(
        r"^(?:Related posts|Get more out of every post|Open app"
        r"|\d+\s+comments?\s*$"
        r"|In collection)",
        re.IGNORECASE,
    )

    end_idx = len(lines)
    for i, line in enumerate(lines):
        if i < start_idx:
            continue
        if _bottom_re.match(line.strip()):
            end_idx = i
            break

    # Also clip at "DannyTrades\n\nAUTHOR" comment header which signals comments
    body = "\n".join(lines[start_idx:end_idx])
    # Remove comment sections: patterns like "\nN\nN\nDannyTrades\n\nAUTHOR"
    # or individual comment blocks that follow the Dr Cat link
    # Simpler: cut at first occurrence of "comments\n" if it appears after body
    author_comment_re = re.compile(r"\n\d+\s+comments?\n.*", re.DOTALL | re.IGNORECASE)
    body = author_comment_re.sub("", body)

    # Strip any boilerplate phrases that slipped through
    for phrase in BOILERPLATE_PHRASES:
        # Remove the line containing the phrase
        body = re.sub(rf"^.*{re.escape(phrase)}.*$\n?", "", body, flags=re.MULTILINE | re.IGNORECASE)

    return body.strip()


# ---------------------------------------------------------------------------
# extract_post_metadata
# ---------------------------------------------------------------------------

def extract_post_metadata(title: str) -> dict:
    """Extract date, tickers, tier, and timeframes from a post title string."""
    # Date
    date: Optional[str] = None
    m = _DATE_RE.search(title)
    if m:
        month_str = m.group("month").lower()
        month_num = _MONTH_MAP.get(month_str)
        if month_num:
            day = m.group("day").zfill(2)
            year = m.group("year")
            date = f"{year}-{month_num}-{day}"

    # Tickers
    tickers = _TICKER_TITLE_RE.findall(title)

    # Tier
    tier: Optional[int] = None
    tm = _TIER_RE.search(title)
    if tm:
        tier = int(tm.group(1))

    # Timeframes
    timeframes = list(dict.fromkeys(
        t.lower() for t in _TIMEFRAME_RE.findall(title)
    ))

    return {
        "date": date,
        "tickers": tickers,
        "tier": tier,
        "timeframes": timeframes,
    }


# ---------------------------------------------------------------------------
# split_ticker_blocks
# ---------------------------------------------------------------------------

def split_ticker_blocks(body: str) -> list[dict]:
    """
    Split post body at numbered entries like '1.AAOI Analysis:'.
    Returns list of {"ticker_hint": str | None, "text": str}.
    Single-ticker posts return one block with ticker_hint=None.
    """
    headers = list(_BLOCK_HEADER_RE.finditer(body))
    if not headers:
        return [{"ticker_hint": None, "text": body}]

    blocks = []
    for idx, match in enumerate(headers):
        ticker = match.group(2).upper()
        start = match.start()
        end = headers[idx + 1].start() if idx + 1 < len(headers) else len(body)
        text = body[start:end].strip()
        blocks.append({"ticker_hint": ticker, "text": text})
    return blocks


# ---------------------------------------------------------------------------
# extract_ticker_fields
# ---------------------------------------------------------------------------

def extract_ticker_fields(text: str) -> dict:
    """
    Regex-extract structured fields from one ticker block of text.
    """
    needs_review = False

    # --- closing_price ---
    closing_price: Optional[float] = None
    m = _PRICE_RE.search(text)
    if m:
        closing_price = float(m.group(1))
    else:
        needs_review = True

    # --- support ---
    support: Optional[str] = None
    m = _SUPPORT_RE.search(text)
    if m:
        support = m.group(1).strip().rstrip(".")

    # --- resistance ---
    resistance: Optional[str] = None
    m = _RESISTANCE_RE.search(text)
    if m:
        resistance = m.group(1).strip().rstrip(".")

    # --- whale_pct / whale_direction ---
    whale_pct: Optional[float] = None
    whale_direction: Optional[str] = None

    m = _WHALE_RE.search(text)
    if m:
        dir_raw = (m.group("dir") or "").lower().strip()
        pct_raw = m.group("pct")

        if "invisible" in dir_raw:
            whale_pct = 0.0
            whale_direction = None
            needs_review = True
        elif pct_raw:
            whale_pct = float(pct_raw)
            if "increased" in dir_raw:
                whale_direction = "increased"
            elif "decreased" in dir_raw:
                whale_direction = "decreased"
            elif "steady" in dir_raw:
                whale_direction = "steady"
        else:
            needs_review = True
    else:
        needs_review = True

    # --- macd_rsi ---
    macd_rsi: Optional[str] = None
    m = _TECH_RE.search(text)
    if m:
        raw_indicator = m.group(1).strip()
        # Strip UTF-8 artifacts (Â / \xc2)
        raw_indicator = raw_indicator.replace("\xc2", "").replace("Â", "").strip()
        macd_rsi = raw_indicator[: FIELD_LIMITS["macd_rsi"]]

    # --- candle signals ---
    # We need per-line context for candle signals to avoid cross-contamination
    # between different timeframe mentions within the same block.

    def _check_candle(pattern: re.Pattern, txt: str) -> bool:
        return bool(pattern.search(txt))

    # Red candle: check each sentence/line individually for context
    red_daily = False
    red_weekly = False
    red_monthly = False
    yellow_daily = False
    yellow_weekly = False

    for line in text.split("\n"):
        line_l = line.lower()
        if "red candle" in line_l:
            if "weekly" in line_l:
                red_weekly = True
            elif "monthly" in line_l:
                red_monthly = True
            else:
                red_daily = True
        if "yellow candle" in line_l:
            if "weekly" in line_l:
                yellow_weekly = True
            elif "monthly" in line_l:
                pass  # yellow_monthly not tracked
            else:
                yellow_daily = True

    # --- golden cross ---
    golden_cross = bool(_GOLDEN_CROSS_RE.search(text))

    # --- invalidation ---
    invalidation: Optional[str] = None
    m = _INVALIDATION_RE.search(text)
    if m:
        invalidation = f"${m.group(1)}"

    return {
        "closing_price": closing_price,
        "support": support,
        "resistance": resistance,
        "whale_pct": whale_pct,
        "whale_direction": whale_direction,
        "macd_rsi": macd_rsi,
        "red_daily": red_daily,
        "red_weekly": red_weekly,
        "red_monthly": red_monthly,
        "yellow_daily": yellow_daily,
        "yellow_weekly": yellow_weekly,
        "golden_cross": golden_cross,
        "invalidation": invalidation,
        "needs_review": needs_review,
    }


# ---------------------------------------------------------------------------
# parse_raw_post  (top-level)
# ---------------------------------------------------------------------------

def _find_title(body: str) -> str:
    """
    Heuristic: first non-empty line that contains a ticker ($TICKER) or
    a date pattern '(Month DD, YYYY' is the title.
    Falls back to the first non-empty line.
    """
    for line in body.split("\n"):
        line = line.strip()
        if not line:
            continue
        if _TICKER_TITLE_RE.search(line) or _DATE_RE.search(line):
            return line
    # Fallback: first non-empty line
    for line in body.split("\n"):
        line = line.strip()
        if line:
            return line
    return ""


def _has_ticker_data(body: str) -> bool:
    """Return True if body contains structured ticker data (Closing Price / Support etc.)."""
    return bool(
        re.search(r"Closing Price\s*:", body, re.IGNORECASE)
        or re.search(r"Support (?:Levels?|Level)\s*:", body, re.IGNORECASE)
        or re.search(r"Whale\s+Accumulation\s*:", body, re.IGNORECASE)
    )


def parse_raw_post(raw: str, post_id: str) -> dict:
    """
    Parse a full raw Patreon post dump.

    Returns:
        {
            "post_id": str,
            "title": str,
            "date": str | None,
            "observations": [{"symbol": str, ...}, ...],
            "skipped_reason": str | None,
        }
    """
    body = strip_chrome(raw)
    title = _find_title(body)
    meta = extract_post_metadata(title)

    if not _has_ticker_data(body):
        return {
            "post_id": post_id,
            "title": title,
            "date": meta["date"],
            "observations": [],
            "skipped_reason": "no_ticker_data",
        }

    blocks = split_ticker_blocks(body)
    ticker_list = meta["tickers"]  # from title

    observations = []
    for idx, block in enumerate(blocks):
        fields = extract_ticker_fields(block["text"])

        # Resolve symbol: prefer ticker_hint, fall back to title ticker list
        symbol = block["ticker_hint"]
        if symbol is None and idx < len(ticker_list):
            symbol = ticker_list[idx]
        if symbol is None:
            symbol = "UNKNOWN"

        # Enforce FIELD_LIMITS["symbol"]
        symbol = symbol[: FIELD_LIMITS["symbol"]]

        obs = {"symbol": symbol}
        obs.update(fields)
        observations.append(obs)

    return {
        "post_id": post_id,
        "title": title,
        "date": meta["date"],
        "observations": observations,
        "skipped_reason": None,
    }
