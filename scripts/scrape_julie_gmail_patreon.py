#!/usr/bin/env python3
"""
scrape_julie_gmail_patreon.py — Pull DannyTrades Patreon notifications from
Julie's Gmail via IMAP, feed each body through parse_email.py, and persist
results to disk for downstream ingest.

This replaces the Playwright Patreon scraper for email-delivered posts.
Julie is the Patreon subscriber; her inbox receives native notifications
from `dannytrades@creator.patreon.com` every time Danny posts a ticker
analysis. We pull those, parse them, and drop structured observations
on disk where the DannyTrades importer (or a follow-up pipeline step)
can ingest them.

Configuration via environment variables
---------------------------------------
Required:
  JULIE_GMAIL_ADDR      Julie's Gmail address (e.g. julievilla2002@gmail.com)
  JULIE_GMAIL_APP_PW    Gmail app password — 16-char, 2FA required on account.
                        Generate at https://myaccount.google.com/apppasswords.

Optional:
  DT_EMAIL_SCRAPE_DIR   Output root (default: <repo>/raw/patreon_email/)
  DT_EMAIL_STATE_FILE   Checkpoint path (default: <repo>/.state/gmail_scrape_state.json)
  DT_EMAIL_FROM         Sender filter (default: dannytrades@creator.patreon.com)
  DT_IMAP_HOST          IMAP host (default: imap.gmail.com)
  DT_IMAP_PORT          IMAP port (default: 993)

Usage
-----
  # Incremental pull (default; respects the checkpoint state)
  python scripts/scrape_julie_gmail_patreon.py

  # First-run backfill — ignore checkpoint, pull all Patreon history
  python scripts/scrape_julie_gmail_patreon.py --backfill

  # Dry-run — verify IMAP auth + message count without writing anything
  python scripts/scrape_julie_gmail_patreon.py --dry-run

  # Date-bounded backfill
  python scripts/scrape_julie_gmail_patreon.py --backfill --since 2026-04-01

  # Cap new messages
  python scripts/scrape_julie_gmail_patreon.py --limit 5

State file shape
----------------
  {"uidvalidity": <int>, "last_uid": <int>, "last_run_at": "<iso>"}

If UIDVALIDITY changes (rare — usually means mailbox moved), the script logs
a warning and resets `last_uid` to 0. Re-run with --backfill to recover.

Output layout
-------------
  <OUTDIR>/<YYYY-MM>/<UID>_<safe-subject-slug>.eml        raw RFC822 message
  <OUTDIR>/<YYYY-MM>/<UID>_<safe-subject-slug>.obs.json   parsed observations

Exit codes
----------
  0: success (includes "no new messages")
  1: transient network/IMAP error — safe to retry
  2: configuration error (missing env, bad state file)
  3: parser error on one or more messages (details in log)

DIR-T89-DANNYTRADES-QUOTE-001 companion — email-lane backfill
"""
from __future__ import annotations

import argparse
import email
import imaplib
import json
import logging
import os
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from email.message import Message
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Optional

# Let parse_email + raw_to_structured resolve from sibling scripts dir.
sys.path.insert(0, str(Path(__file__).parent))

from parse_email import parse_email  # noqa: E402

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent

_DEFAULT_IMAP_HOST = "imap.gmail.com"
_DEFAULT_IMAP_PORT = 993
_DEFAULT_FROM = "dannytrades@creator.patreon.com"
_DEFAULT_SCRAPE_DIR = _REPO_ROOT / "raw" / "patreon_email"
_DEFAULT_STATE_FILE = _REPO_ROOT / ".state" / "gmail_scrape_state.json"

# Filename slug: keep [A-Za-z0-9._-], collapse runs, cap length.
_SLUG_BAD_RE = re.compile(r"[^A-Za-z0-9._-]+")


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class ProcessResult:
    uid: int
    subject: str
    date_header: Optional[str]
    post_type: str
    observations_count: int
    raw_path: Optional[str]
    obs_path: Optional[str]
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_slug(raw: str, cap: int = 50) -> str:
    slug = _SLUG_BAD_RE.sub("-", raw).strip("-")
    return (slug or "untitled")[:cap]


def _imap_date(dt: datetime) -> str:
    """IMAP SEARCH SINCE wants DD-Mon-YYYY."""
    return dt.strftime("%d-%b-%Y")


def extract_plain_text(msg: Message) -> str:
    """Extract the plain-text representation of an email message.

    Rules:
      1. If message is not multipart, decode its payload with the declared
         charset (fall back utf-8 + errors=replace).
      2. If multipart, prefer the first text/plain part anywhere in the tree.
      3. If no text/plain found, fall back to the first text/html with tags
         crudely stripped. Not HTML-perfect, but Patreon emails are simple
         enough that this works for ticker field extraction.
      4. If neither found, return "".
    """
    if not msg.is_multipart():
        payload = msg.get_payload(decode=True) or b""
        charset = msg.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")

    plain: Optional[str] = None
    html: Optional[str] = None
    for part in msg.walk():
        if part.is_multipart():
            continue
        ctype = part.get_content_type()
        if ctype not in ("text/plain", "text/html"):
            continue
        payload = part.get_payload(decode=True) or b""
        charset = part.get_content_charset() or "utf-8"
        text = payload.decode(charset, errors="replace")
        if ctype == "text/plain" and plain is None:
            plain = text
        elif ctype == "text/html" and html is None:
            html = text
    if plain:
        return plain
    if html:
        # Crude tag strip. Enough for Patreon's simple emails; upgrade to
        # BeautifulSoup later if we see a structured content we miss.
        stripped = re.sub(r"<[^>]+>", " ", html)
        stripped = re.sub(r"&nbsp;", " ", stripped)
        stripped = re.sub(r"&amp;", "&", stripped)
        stripped = re.sub(r"&lt;", "<", stripped)
        stripped = re.sub(r"&gt;", ">", stripped)
        stripped = re.sub(r"\n{3,}", "\n\n", stripped)
        return stripped
    return ""


# ---------------------------------------------------------------------------
# State checkpoint
# ---------------------------------------------------------------------------

def load_state(path: Path) -> dict:
    if not path.exists():
        return {"uidvalidity": None, "last_uid": 0, "last_run_at": None}
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("state file %s unreadable (%s) — starting fresh", path, e)
        return {"uidvalidity": None, "last_uid": 0, "last_run_at": None}


def save_state(path: Path, uidvalidity: int, last_uid: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "uidvalidity": uidvalidity,
        "last_uid": last_uid,
        "last_run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }, indent=2))


# ---------------------------------------------------------------------------
# IMAP
# ---------------------------------------------------------------------------

def connect(addr: str, pw: str, host: str, port: int) -> imaplib.IMAP4_SSL:
    logger.info("IMAP connect %s:%d as %s", host, port, addr)
    imap = imaplib.IMAP4_SSL(host, port)
    imap.login(addr, pw)
    return imap


def select_inbox(imap: imaplib.IMAP4_SSL) -> int:
    """Select INBOX and return its UIDVALIDITY."""
    status, _ = imap.select("INBOX", readonly=True)
    if status != "OK":
        raise RuntimeError(f"IMAP SELECT INBOX failed: {status}")
    status, resp = imap.response("UIDVALIDITY")
    if status != "OK" or not resp:
        raise RuntimeError(f"UIDVALIDITY not available: status={status} resp={resp}")
    # resp is a list of bytes; take the last entry
    return int(resp[-1])


def search_new_uids(
    imap: imaplib.IMAP4_SSL,
    from_addr: str,
    last_uid: int,
    since: Optional[datetime],
) -> list[int]:
    """UID-SEARCH for messages from `from_addr`, newer than last_uid, since date."""
    criteria: list[str] = ["FROM", f'"{from_addr}"']
    if since:
        criteria += ["SINCE", _imap_date(since)]
    if last_uid > 0:
        criteria += ["UID", f"{last_uid + 1}:*"]
    status, data = imap.uid("SEARCH", None, *criteria)
    if status != "OK":
        raise RuntimeError(f"UID SEARCH failed: {status} {data}")
    raw = (data[0] or b"").decode().strip()
    if not raw:
        return []
    # Filter out <=last_uid (Gmail's `UID N:*` often returns the anchor UID too)
    # + dedup (rare but harmless; sorted+set is cheap at these volumes).
    return sorted({int(u) for u in raw.split() if int(u) > last_uid})


def fetch_message(imap: imaplib.IMAP4_SSL, uid: int) -> Optional[Message]:
    status, data = imap.uid("FETCH", str(uid).encode(), "(RFC822)")
    if status != "OK" or not data or not isinstance(data[0], tuple):
        logger.warning("FETCH uid=%d failed: status=%s data=%r", uid, status, data)
        return None
    return email.message_from_bytes(data[0][1])


# ---------------------------------------------------------------------------
# Per-message processing
# ---------------------------------------------------------------------------

def process_one(msg: Message, uid: int, out_root: Path, dry_run: bool) -> ProcessResult:
    subject = (msg.get("Subject") or "").strip()
    date_hdr = msg.get("Date")
    try:
        email_date = parsedate_to_datetime(date_hdr) if date_hdr else None
    except (TypeError, ValueError):
        email_date = None
    ym = email_date.strftime("%Y-%m") if email_date else "undated"
    slug = _safe_slug(subject)

    out_dir = out_root / ym
    raw_path = out_dir / f"{uid:08d}_{slug}.eml"
    obs_path = out_dir / f"{uid:08d}_{slug}.obs.json"

    if not dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)
        raw_path.write_bytes(msg.as_bytes())

    body_text = extract_plain_text(msg)
    try:
        parsed = parse_email(body_text, subject=subject)
    except Exception as exc:  # pragma: no cover — parser robustness
        logger.exception("parse_email failed for uid=%d subject=%r", uid, subject)
        return ProcessResult(
            uid=uid, subject=subject, date_header=date_hdr,
            post_type="error", observations_count=0,
            raw_path=str(raw_path) if not dry_run else None,
            obs_path=None, error=str(exc),
        )

    if not dry_run:
        # Write only the slice we care about downstream — the importer doesn't
        # need the raw email again, it needs the structured observations.
        obs_path.write_text(json.dumps({
            "uid": uid,
            "subject": subject,
            "date_header": date_hdr,
            "email_date": email_date.isoformat() if email_date else None,
            "post_type": parsed["post_type"],
            "title": parsed["title"],
            "metadata": parsed["metadata"],
            "observations": parsed["observations"],
        }, indent=2, default=str))

    return ProcessResult(
        uid=uid, subject=subject, date_header=date_hdr,
        post_type=parsed["post_type"],
        observations_count=len(parsed["observations"]),
        raw_path=str(raw_path) if not dry_run else None,
        obs_path=str(obs_path) if not dry_run else None,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _get_env(name: str, required: bool = True, default: Optional[str] = None) -> Optional[str]:
    val = os.environ.get(name, default)
    if required and not val:
        logger.error("Missing required env var: %s", name)
        return None
    return val


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--dry-run", action="store_true",
                    help="verify auth + message count, write nothing")
    ap.add_argument("--backfill", action="store_true",
                    help="ignore checkpoint, pull all history (optionally bounded by --since)")
    ap.add_argument("--since", type=str, metavar="YYYY-MM-DD",
                    help="only fetch messages since this date (backfill)")
    ap.add_argument("--limit", type=int, default=None,
                    help="cap number of new messages to process")
    ap.add_argument("--from-addr", type=str, default=None,
                    help=f"override sender filter (default: {_DEFAULT_FROM})")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    addr = _get_env("JULIE_GMAIL_ADDR")
    pw = _get_env("JULIE_GMAIL_APP_PW")
    if not addr or not pw:
        return 2

    from_addr = args.from_addr or os.environ.get("DT_EMAIL_FROM", _DEFAULT_FROM)
    out_root = Path(os.environ.get("DT_EMAIL_SCRAPE_DIR", str(_DEFAULT_SCRAPE_DIR)))
    state_path = Path(os.environ.get("DT_EMAIL_STATE_FILE", str(_DEFAULT_STATE_FILE)))
    host = os.environ.get("DT_IMAP_HOST", _DEFAULT_IMAP_HOST)
    port = int(os.environ.get("DT_IMAP_PORT", _DEFAULT_IMAP_PORT))

    since: Optional[datetime] = None
    if args.since:
        try:
            since = datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            logger.error("invalid --since date %r (expected YYYY-MM-DD)", args.since)
            return 2

    # Load checkpoint
    state = load_state(state_path)
    last_uid = 0 if args.backfill else int(state.get("last_uid") or 0)

    try:
        imap = connect(addr, pw, host, port)
    except (imaplib.IMAP4.error, OSError) as exc:
        logger.error("IMAP connect/login failed: %s", exc)
        return 1

    try:
        uidvalidity = select_inbox(imap)
        if state.get("uidvalidity") not in (None, uidvalidity):
            logger.warning(
                "UIDVALIDITY changed (stored=%s, live=%d) — resetting last_uid. "
                "Re-run with --backfill to recover missed messages.",
                state.get("uidvalidity"), uidvalidity,
            )
            last_uid = 0

        uids = search_new_uids(imap, from_addr, last_uid, since)
        logger.info("search: from=%s last_uid=%d since=%s -> %d new uid(s)",
                    from_addr, last_uid, args.since, len(uids))
        if args.limit:
            uids = uids[: args.limit]

        results: list[ProcessResult] = []
        for uid in uids:
            msg = fetch_message(imap, uid)
            if msg is None:
                continue
            r = process_one(msg, uid, out_root, dry_run=args.dry_run)
            results.append(r)
            logger.info(
                "uid=%d %s obs=%d file=%s",
                r.uid, r.post_type, r.observations_count,
                r.obs_path or "(dry-run)",
            )

        new_last_uid = max([r.uid for r in results], default=last_uid)
        if not args.dry_run and new_last_uid > last_uid:
            save_state(state_path, uidvalidity, new_last_uid)
            logger.info("state saved: uidvalidity=%d last_uid=%d", uidvalidity, new_last_uid)

        any_parse_errors = any(r.error for r in results)
        logger.info(
            "run complete: processed=%d observations_total=%d errors=%d",
            len(results),
            sum(r.observations_count for r in results),
            sum(1 for r in results if r.error),
        )
        return 3 if any_parse_errors else 0
    finally:
        try:
            imap.logout()
        except Exception:  # pragma: no cover
            pass


if __name__ == "__main__":
    sys.exit(main())
