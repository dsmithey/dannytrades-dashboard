"""
raw_to_structured.py — Deterministic regex parser for DannyTrades Patreon post dumps.
NO LLM.  All extraction via regex + string operations.
"""
from __future__ import annotations

import hashlib
import json
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


# ---------------------------------------------------------------------------
# Task 3: Batch Structured Markdown Writer
# ---------------------------------------------------------------------------

def _fmt_price(val) -> str:
    """Format a price value as '$X.XX' or 'N/A'."""
    if val is None:
        return "N/A"
    try:
        return f"${float(val):.2f}"
    except (TypeError, ValueError):
        return "N/A"


def _fmt_whale(val) -> str:
    """Format a whale accumulation value as 'X.XX%' or 'N/A'."""
    if val is None:
        return "N/A"
    try:
        return f"{float(val):.2f}%"
    except (TypeError, ValueError):
        return "N/A"


def _trunc(s, limit: int) -> str:
    """Truncate string to limit chars; return 'N/A' for None."""
    if s is None:
        return "N/A"
    s = str(s)
    return s[:limit]


def _cell(s, limit: int = MAX_CELL_LENGTH) -> str:
    """Ensure cell content does not exceed MAX_CELL_LENGTH."""
    if s is None:
        return "N/A"
    s = str(s)
    return s[:limit]


def format_batch_entry(obs: dict, title: str) -> str:
    """
    Format a single observation as a markdown section matching the
    parse_batch_structured format.

    Returns a multi-line string:
        ## {date} — ${ticker} ({title}) — Post {post_id}
        | ... table ... |
        **Signal Summary:** ...
    """
    date = obs.get("date") or "N/A"
    symbol = obs.get("symbol") or "UNKNOWN"
    post_id = obs.get("post_id") or "N/A"

    price_str = _fmt_price(obs.get("closing_price"))
    support_str = _cell(obs.get("support") or "N/A")
    resistance_str = _cell(obs.get("resistance") or "N/A")
    whale_str = _cell(_fmt_whale(obs.get("whale_pct")))
    macd_str = _cell(_trunc(obs.get("macd_rsi"), 120))
    signal_raw = obs.get("signal") or obs.get("macd_rsi") or "N/A"
    signal_str = _cell(_trunc(signal_raw, 120))

    # Build signal from candle flags if explicit "signal" key absent
    if "signal" not in obs:
        parts = []
        if obs.get("red_daily"):
            parts.append("Red candle (daily)")
        if obs.get("red_weekly"):
            parts.append("Red candle (weekly)")
        if obs.get("red_monthly"):
            parts.append("Red candle (monthly)")
        if obs.get("yellow_daily"):
            parts.append("Yellow candle (daily)")
        if obs.get("yellow_weekly"):
            parts.append("Yellow candle (weekly)")
        if obs.get("golden_cross"):
            parts.append("MACD golden cross")
        if obs.get("invalidation"):
            parts.append(f"Invalidated below {obs['invalidation']}")
        if parts:
            signal_str = _cell(_trunc("; ".join(parts), 120))

    header = f"## {date} — ${symbol} ({title}) — Post {post_id}"
    table_header = (
        "| Ticker | Close | Support | Resistance | Whale Accum | MACD/RSI | Signal |"
    )
    separator = "|--------|-------|---------|------------|-------------|----------|--------|"
    row = (
        f"| {_cell(symbol)} | {_cell(price_str)} | {_cell(support_str)} "
        f"| {_cell(resistance_str)} | {_cell(whale_str)} | {_cell(macd_str)} "
        f"| {_cell(signal_str)} |"
    )

    signal_summary = _trunc(signal_str, 120)

    return "\n".join([
        header,
        "",
        table_header,
        separator,
        row,
        "",
        f"**Signal Summary:** {signal_summary}",
    ])


def write_batch_file(
    observations: list,
    titles: dict,
    output_path: str,
    run_date: str,
) -> str:
    """
    Write all observations as a batch structured markdown file.

    observations: list of obs dicts (each must have 'symbol', 'post_id', 'date', etc.)
    titles: dict mapping post_id -> tier title string
    output_path: file path to write
    run_date: ISO date string for file header

    Returns output_path.
    """
    lines = [
        f"# DannyTrades Batch Structured Output",
        f"**Run date:** {run_date}",
        "",
        "---",
        "",
    ]
    for obs in observations:
        post_id = obs.get("post_id") or "N/A"
        title = titles.get(post_id, "")
        lines.append(format_batch_entry(obs, title))
        lines.append("")
        lines.append("---")
        lines.append("")

    content = "\n".join(lines)
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(content)
    return output_path


# ---------------------------------------------------------------------------
# Task 4: Watchlist Reader / Writer / Merge
# ---------------------------------------------------------------------------

_WATCHLIST_ROW_RE = re.compile(
    r"^\|\s*(\d+)\s*\|"          # rank
    r"\s*([A-Z0-9]+)\s*\|"       # ticker
    r"\s*(.+?)\s*\|"             # sector
    r"\s*(\S+)\s*\|"             # latest_close
    r"\s*(.+?)\s*\|"             # whale_accum
    r"\s*(.+?)\s*\|"             # macd_rsi
    r"\s*(.+?)\s*\|"             # latest_signal
    r"\s*(.+?)\s*\|"             # trend
    r"\s*$"
)


def _parse_whale_cell(raw: str):
    """
    Parse a whale accumulation cell.
    Handles: "98.98%", "98.9% (wkly)", "Invisible", "N/A".
    Strips parenthetical notes; returns float or None.
    """
    raw = raw.strip()
    if raw.lower() in ("n/a", "", "-"):
        return None
    if raw.lower() == "invisible":
        return 0.0
    # Strip parenthetical: "98.9% (wkly)" -> "98.9%"
    raw = re.sub(r"\s*\(.*?\)", "", raw).strip()
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*%", raw)
    if m:
        return float(m.group(1))
    return None


def _parse_close_cell(raw: str):
    """Parse '$123.45' or 'N/A' into float or None."""
    raw = raw.strip()
    if raw.lower() in ("n/a", "", "-"):
        return None
    m = re.search(r"\$?([0-9]+(?:\.[0-9]+)?)", raw)
    if m:
        return float(m.group(1))
    return None


def read_watchlist(path: str) -> list:
    """
    Parse an existing WATCHLIST_AND_TIMELINE.md file.
    Returns list of dicts with keys:
        rank, symbol, sector, latest_close, whale_pct, macd_rsi, signal, trend, date
    Only the main ranked table rows are returned (not index-fund rows).
    """
    rows = []
    with open(path, encoding="utf-8") as fh:
        content = fh.read()

    # Find the generated date if present
    gen_date = None
    dm = re.search(r"\*\*Generated:\s*([^\*]+)\*\*", content)
    if dm:
        gen_date = dm.group(1).strip()

    # Parse each table row that matches the 8-column watchlist format
    for line in content.split("\n"):
        m = _WATCHLIST_ROW_RE.match(line)
        if not m:
            continue
        rank_str, ticker, sector, close_raw, whale_raw, macd_rsi, signal, trend = (
            m.group(1), m.group(2), m.group(3), m.group(4),
            m.group(5), m.group(6), m.group(7), m.group(8),
        )
        rows.append({
            "rank": int(rank_str),
            "symbol": ticker.strip(),
            "sector": sector.strip(),
            "latest_close": _parse_close_cell(close_raw),
            "whale_pct": _parse_whale_cell(whale_raw),
            "macd_rsi": macd_rsi.strip(),
            "signal": signal.strip(),
            "trend": trend.strip(),
            "date": gen_date,
        })
    return rows


def merge_watchlist(existing: list, new_observations: list) -> list:
    """
    Merge new observations into existing watchlist rows.

    Rules:
    - New symbol (not in existing) → append
    - Existing symbol with newer/updated data → replace (preserve sector
      from existing if new obs lacks it)
    - Existing symbol not in new observations → preserve unchanged
    - Final list sorted by whale_pct descending (None/0 at bottom)
    """
    existing_by_sym = {r["symbol"]: dict(r) for r in existing}

    for obs in new_observations:
        sym = obs.get("symbol", "UNKNOWN")
        new_row = {
            "symbol": sym,
            "sector": obs.get("sector") or existing_by_sym.get(sym, {}).get("sector") or "N/A",
            "latest_close": obs.get("closing_price"),
            "whale_pct": obs.get("whale_pct"),
            "macd_rsi": obs.get("macd_rsi") or "N/A",
            "signal": obs.get("signal") or "N/A",
            "trend": obs.get("trend") or "N/A",
            "date": obs.get("date"),
            "rank": existing_by_sym.get(sym, {}).get("rank", 9999),
        }
        existing_by_sym[sym] = new_row

    merged = list(existing_by_sym.values())

    def _sort_key(row):
        wp = row.get("whale_pct")
        if wp is None:
            return -1.0
        return float(wp)

    merged.sort(key=_sort_key, reverse=True)

    # Re-assign ranks
    for i, row in enumerate(merged):
        row["rank"] = i + 1

    return merged


def write_watchlist_next(rows: list, output_path: str, generated_date: str) -> str:
    """
    Write a WATCHLIST_AND_TIMELINE.next.md matching existing format.
    Returns output_path.
    """
    lines = [
        "# DannyTrades Watchlist Summary & Chronological View",
        f"**Generated: {generated_date}**",
        "",
        "---",
        "",
        "# SECTION 1: WATCHLIST SUMMARY",
        "",
        "Ranked by most recent whale accumulation percentage (highest to lowest).",
        "",
        "| Rank | Ticker | Sector | Latest Close | Whale Accum | MACD/RSI | Latest Signal | Trend (5-day) |",
        "|------|--------|--------|-------------|-------------|----------|---------------|---------------|",
    ]

    for row in rows:
        rank = row.get("rank", "")
        sym = row.get("symbol", "")
        sector = row.get("sector") or "N/A"
        close_val = row.get("latest_close")
        close_str = _fmt_price(close_val) if close_val is not None else "N/A"
        whale_val = row.get("whale_pct")
        whale_str = _fmt_whale(whale_val) if whale_val is not None else "N/A"
        macd = row.get("macd_rsi") or "N/A"
        signal = row.get("signal") or "N/A"
        trend = row.get("trend") or "N/A"
        lines.append(
            f"| {rank} | {sym} | {sector} | {close_str} | {whale_str} "
            f"| {macd} | {signal} | {trend} |"
        )

    lines.append("")
    lines.append("---")
    lines.append("")

    content = "\n".join(lines)
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(content)
    return output_path


# ---------------------------------------------------------------------------
# Task 5: Review Gate + Parse Report
# ---------------------------------------------------------------------------

def check_needs_review_rate(observations, threshold: float = 0.50):
    """
    Returns (passed: bool, rate: float).
    'passed' is True when the needs_review rate is BELOW threshold.
    Empty list → (False, 1.0) — treat as 100% needs review (abort).
    """
    if not observations:
        return (False, 1.0)
    total = len(observations)
    flagged = sum(1 for o in observations if o.get("needs_review", False))
    rate = flagged / total
    passed = rate < threshold
    return (passed, rate)


def check_field_lengths(observations) -> list:
    """
    Validate that symbol ≤ 12, signal ≤ 120, macd_rsi ≤ 120.
    Returns list of error message strings (empty = all pass).
    """
    errors = []
    limits = {
        "symbol": 12,
        "signal": 120,
        "macd_rsi": 120,
    }
    for i, obs in enumerate(observations):
        for field, limit in limits.items():
            val = obs.get(field)
            if val is not None and len(str(val)) > limit:
                errors.append(
                    f"obs[{i}] {obs.get('symbol','?')}: field '{field}' "
                    f"exceeds {limit} chars (got {len(str(val))})"
                )
    return errors


def check_boilerplate(observations) -> list:
    """
    Check all string fields in each observation for BOILERPLATE_PHRASES.
    Returns list of error message strings (empty = all pass).
    """
    errors = []
    for i, obs in enumerate(observations):
        for field, val in obs.items():
            if not isinstance(val, str):
                continue
            for phrase in BOILERPLATE_PHRASES:
                if phrase.lower() in val.lower():
                    errors.append(
                        f"obs[{i}] {obs.get('symbol','?')}: field '{field}' "
                        f"contains boilerplate phrase '{phrase}'"
                    )
    return errors


def check_cell_lengths(md_content: str) -> list:
    """
    Scan markdown table rows and verify no cell exceeds MAX_CELL_LENGTH.
    Separator rows (containing only dashes, pipes, spaces) are skipped.
    Returns list of error message strings.
    """
    errors = []
    _separator_re = re.compile(r"^\|[\s\-|]+\|$")
    for lineno, line in enumerate(md_content.split("\n"), start=1):
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        if _separator_re.match(stripped):
            continue
        # Split on '|' and skip first/last empty segments
        cells = stripped.split("|")[1:-1]
        for col_idx, cell in enumerate(cells):
            cell_stripped = cell.strip()
            if len(cell_stripped) > MAX_CELL_LENGTH:
                errors.append(
                    f"line {lineno}, col {col_idx + 1}: cell length "
                    f"{len(cell_stripped)} exceeds {MAX_CELL_LENGTH}"
                )
    return errors


def reconcile_manifest(
    manifest_scraped: list,
    processed: list,
    skipped_no_ticker: list,
    failed: list,
) -> dict:
    """
    Reconcile post IDs across pipeline buckets.

    manifest_scraped: list of post IDs from the scrape manifest
    processed: list of post IDs that produced observations
    skipped_no_ticker: list of post IDs skipped (no ticker data)
    failed: list of post IDs that failed parsing

    Returns:
        {
            "all_reconciled": bool,
            "abort": bool,
            "not_in_manifest": list,   # IDs in processed/skipped not in manifest
            "unreconciled": list,      # manifest IDs not in any bucket
        }
    """
    manifest_set = set(manifest_scraped)
    all_buckets = set(processed) | set(skipped_no_ticker) | set(failed)

    not_in_manifest = [pid for pid in (processed + skipped_no_ticker + failed)
                       if pid not in manifest_set]
    unreconciled = [pid for pid in manifest_scraped if pid not in all_buckets]

    abort = bool(not_in_manifest) or bool(unreconciled)
    all_reconciled = not abort

    return {
        "all_reconciled": all_reconciled,
        "abort": abort,
        "not_in_manifest": not_in_manifest,
        "unreconciled": unreconciled,
    }


def build_parse_report(
    run_date: str,
    raw_files_processed: int,
    raw_files_skipped_no_ticker: int,
    batch_file: str,
    watchlist_next_path: str,
    observations: list,
    prior_run_count: int,
    post_ids_processed: list,
    post_ids_skipped_no_ticker: list,
    post_ids_from_manifest: list,
    existing_symbols: list,
) -> dict:
    """
    Build the parse_report JSON dict.
    Hashes the watchlist_next_path content with SHA-256.
    """
    # Hash the watchlist_next file
    try:
        with open(watchlist_next_path, "rb") as fh:
            watchlist_hash = hashlib.sha256(fh.read()).hexdigest()
    except OSError:
        watchlist_hash = None

    new_symbols = [
        o.get("symbol") for o in observations
        if o.get("symbol") and o.get("symbol") not in set(existing_symbols)
    ]

    # needs_review rate
    _, nr_rate = check_needs_review_rate(observations)

    # field / boilerplate checks
    field_errors = check_field_lengths(observations)
    boilerplate_errors = check_boilerplate(observations)

    reconcile = reconcile_manifest(
        post_ids_from_manifest,
        post_ids_processed,
        post_ids_skipped_no_ticker,
        [],
    )

    return {
        "run_date": run_date,
        "raw_files_processed": raw_files_processed,
        "raw_files_skipped_no_ticker": raw_files_skipped_no_ticker,
        "observations_count": len(observations),
        "prior_run_count": prior_run_count,
        "batch_file": batch_file,
        "watchlist_next_path": watchlist_next_path,
        "watchlist_next_sha256": watchlist_hash,
        "new_symbols": new_symbols,
        "needs_review_rate": nr_rate,
        "field_errors": field_errors,
        "boilerplate_errors": boilerplate_errors,
        "reconcile": reconcile,
        "post_ids_processed": post_ids_processed,
        "post_ids_skipped_no_ticker": post_ids_skipped_no_ticker,
        "post_ids_from_manifest": post_ids_from_manifest,
    }
