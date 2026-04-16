"""
scrape_patreon.py — Playwright MCP helper for DannyTrades Patreon scraping.

This module does NOT import playwright or launch a browser.  It provides
utility functions that an agent with Playwright MCP access calls to:
  - extract post IDs from URLs
  - write raw post files with YAML metadata headers
  - write scrape manifests
  - build JS snippets for use with browser_evaluate

Invoke via:  python3 scripts/scrape_patreon.py  (prints usage)
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


# ---------------------------------------------------------------------------
# extract_post_id
# ---------------------------------------------------------------------------

def extract_post_id(url: str) -> str | None:
    """
    Extract the numeric post ID from a Patreon post URL.

    Handles:
      https://www.patreon.com/posts/title-slug-155338136
      https://www.patreon.com/posts/155338136
      https://www.patreon.com/posts/slug-155338136?utm=x
      https://www.patreon.com/posts/slug-155338136/

    Returns the trailing digit sequence (6+ chars) or None if not found.
    """
    path = urlparse(url).path.rstrip("/")
    match = re.search(r"(\d+)$", path)
    return match.group(1) if match else None


# ---------------------------------------------------------------------------
# write_raw_file
# ---------------------------------------------------------------------------

def write_raw_file(
    post_id: str,
    url: str,
    title: str,
    raw_text: str,
    source_mode: str,
    output_dir: str,
) -> dict:
    """
    Write a raw post file with YAML metadata header.

    File format:
        ---
        post_id: <post_id>
        url: <url>
        title: <title>
        source_mode: <source_mode>
        scraped_at: <ISO UTC timestamp>
        body_sha256: <sha256 of raw_text>
        ---
        <raw_text>

    The hash covers the body text only (not the YAML header).

    Returns a manifest entry dict:
        {
            "post_id": str,
            "url": str,
            "title": str,
            "file": str,           # absolute path written
            "body_sha256": str,
            "scraped_at": str,
        }
    """
    scraped_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    body_hash = hashlib.sha256(raw_text.encode("utf-8", errors="replace")).hexdigest()

    yaml_header = "\n".join([
        "---",
        f"post_id: {post_id}",
        f"url: {url}",
        f"title: {_yaml_escape(title)}",
        f"source_mode: {source_mode}",
        f"scraped_at: {scraped_at}",
        f"body_sha256: {body_hash}",
        "---",
        "",
    ])

    content = yaml_header + raw_text

    out_path = Path(output_dir) / f"{post_id}.txt"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")

    return {
        "post_id": post_id,
        "url": url,
        "title": title,
        "file": str(out_path),
        "body_sha256": body_hash,
        "scraped_at": scraped_at,
    }


def _yaml_escape(s: str) -> str:
    """Minimal YAML escaping: wrap in double-quotes and escape inner quotes."""
    return '"' + s.replace('"', '\\"') + '"'


# ---------------------------------------------------------------------------
# write_manifest
# ---------------------------------------------------------------------------

def write_manifest(
    scraped: list,
    skipped_existing: list,
    failed: list,
    source_mode: str,
    batch_size: int,
    delay_ms: int,
    limit: int | None,
    output_dir: str,
) -> str:
    """
    Write scrape_manifest_{date}.json to output_dir.

    scraped: list of manifest entry dicts (from write_raw_file)
    skipped_existing: list of post_id strings that were skipped (already saved)
    failed: list of dicts with keys post_id, url, error
    source_mode: e.g. "playwright_mcp"
    batch_size: how many posts per page batch
    delay_ms: inter-request delay in milliseconds
    limit: max posts requested (None = unlimited)
    output_dir: directory to write manifest into

    Returns absolute path of written manifest file.
    """
    run_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    date_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

    manifest = {
        "run_at": run_at,
        "source_mode": source_mode,
        "batch_size": batch_size,
        "delay_ms": delay_ms,
        "limit": limit,
        "counts": {
            "scraped": len(scraped),
            "skipped_existing": len(skipped_existing),
            "failed": len(failed),
        },
        "scraped": scraped,
        "skipped_existing": skipped_existing,
        "failed": failed,
    }

    out_path = Path(output_dir) / f"scrape_manifest_{date_str}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return str(out_path)


# ---------------------------------------------------------------------------
# get_existing_post_ids
# ---------------------------------------------------------------------------

def get_existing_post_ids(raw_dir: str) -> set:
    """
    Return a set of post ID strings already saved as raw .txt files.

    Extracts the 6+ digit numeric stem from each filename.
    """
    _id_re = re.compile(r"(\d{6,})")
    found: set = set()
    for f in Path(raw_dir).glob("*.txt"):
        m = _id_re.search(f.stem)
        if m:
            found.add(m.group(1))
    return found


# ---------------------------------------------------------------------------
# JS snippets
# ---------------------------------------------------------------------------

def js_extract_post_links() -> str:
    """
    Return a JavaScript string that extracts all Patreon post links from the
    current page and returns them as a JSON array of {url, title} objects.

    Designed for use with browser_evaluate / page.evaluate().
    """
    return r"""
(function() {
    const links = [];
    const seen = new Set();
    // Patreon post anchors typically have href matching /posts/
    document.querySelectorAll('a[href*="/posts/"]').forEach(function(el) {
        const href = el.href;
        if (!href || seen.has(href)) return;
        // Only include post links (must have numeric suffix)
        if (!/\/posts\/.*\d+/.test(href)) return;
        seen.add(href);
        links.push({
            url: href,
            title: (el.textContent || el.getAttribute('aria-label') || '').trim()
        });
    });
    return JSON.stringify(links);
})();
""".strip()


def js_extract_post_content() -> str:
    """
    Return a JavaScript string that extracts the post title and body text
    from the current Patreon post page.

    Returns a JSON object: {title: str, body: str}
    Designed for use with browser_evaluate / page.evaluate().
    """
    return r"""
(function() {
    // Title: try h1, then og:title meta, then document.title
    let title = '';
    const h1 = document.querySelector('h1');
    if (h1) {
        title = h1.textContent.trim();
    } else {
        const og = document.querySelector('meta[property="og:title"]');
        if (og) title = og.getAttribute('content') || '';
    }
    if (!title) title = document.title || '';

    // Body: grab innerText of the main post content container.
    // Patreon uses several possible containers — try in priority order.
    let body = '';
    const selectors = [
        '[data-tag="post-body"]',
        '[class*="post-content"]',
        'article',
        'main',
    ];
    for (const sel of selectors) {
        const el = document.querySelector(sel);
        if (el) {
            body = el.innerText || el.textContent || '';
            if (body.trim().length > 50) break;
        }
    }
    // Fallback: full body text
    if (!body.trim()) {
        body = document.body.innerText || document.body.textContent || '';
    }

    return JSON.stringify({title: title.trim(), body: body.trim()});
})();
""".strip()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    print("""
scrape_patreon.py — Playwright MCP helper module

USAGE
-----
This script is a utility module, not a standalone scraper.
An agent with Playwright MCP access calls the functions here to:

  1. Navigate to the Patreon creator page via browser_navigate
  2. Extract post links using:
       js = js_extract_post_links()
       result = browser_evaluate(js)
  3. For each new post (check get_existing_post_ids first):
       browser_navigate(url)
       js = js_extract_post_content()
       data = browser_evaluate(js)   → {title, body}
       entry = write_raw_file(post_id, url, data['title'], data['body'],
                              source_mode='playwright_mcp',
                              output_dir='/home/david/DannyTrades/data/raw')
  4. After all posts:
       manifest_path = write_manifest(scraped, skipped_existing, failed,
                                      source_mode='playwright_mcp',
                                      batch_size=10, delay_ms=1500, limit=None,
                                      output_dir='/home/david/DannyTrades/data')
  5. Run the parse pipeline:
       python3 scripts/raw_to_structured.py
       python3 scripts/raw_to_structured.py --approve --report <parse_report_path>

FUNCTIONS
---------
  extract_post_id(url)              → str | None
  write_raw_file(...)               → dict (manifest entry)
  write_manifest(...)               → str (path)
  get_existing_post_ids(raw_dir)    → set[str]
  js_extract_post_links()           → str (JS)
  js_extract_post_content()         → str (JS)
""")


if __name__ == "__main__":
    main()
