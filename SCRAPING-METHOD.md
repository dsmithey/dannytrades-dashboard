---
title: DannyTrades Patreon Scraping Method
description: How Patreon posts are scraped, extracted, and parsed for the DannyTrades dashboard pipeline
keywords:
  - patreon
  - scrape
  - scraper
  - scraping
  - playwright
  - mcp
  - browser automation
  - dannytrades
  - danny trades
  - danny
  - login
  - cookie
  - session
  - extraction
  - dom
  - javascript
  - querySelectorAll
  - ticker
  - whale accumulation
  - golden cross
  - signal
  - pipeline
  - raw text
  - parser
  - postgresql
  - importer
  - patreon.com
  - notifications
  - post links
  - batch navigation
  - html extraction
  - text extraction
  - structured data
  - markdown
  - ticker history
  - watchlist
  - batch structured
  - yfinance
  - yahoo finance
  - market data
  - stock
  - signal score
  - red candle
  - weekly red
  - monthly red
  - daily red
  - core positions
  - buy orders
  - sector
  - heatmap
  - dashboard
  - captain dashboard
  - boss api
  - fastapi
  - cli importer
  - content hash
  - idempotency
  - atomic transaction
  - run import
  - data authority
  - PG API JSON
tags:
  - scraping
  - patreon
  - playwright
  - dannytrades
  - pipeline
  - automation
  - data-acquisition
tech_stack:
  - Playwright MCP (Claude browser automation)
  - JavaScript DOM extraction
  - Python parsers
  - PostgreSQL
  - BOSS API (FastAPI)
not_used:
  - Selenium
  - BeautifulSoup
  - requests library
  - puppeteer
  - scrapy
  - curl
product: DannyTrades
thread: T89
created: 2026-04-16
updated: 2026-04-16
author: nravi
---

# DannyTrades Patreon Scraping Method

## How the data gets from Patreon to the dashboard

There is no standalone scraper script. The Patreon data extraction uses **Playwright MCP** (Claude's browser automation tool) in a Claude-assisted interactive workflow.

## Pipeline (5 steps)

```
Step 1: Playwright navigates to patreon.com/notifications?mode=user, logs in
Step 2: JavaScript querySelectorAll extracts post links from the page
Step 3: Playwright browser_run_code batch-navigates each post URL
Step 4: Raw text extracted from each post → saved as individual .txt files (one per post ID)
Step 5: Python parsers produce structured markdown → CLI importer loads into PostgreSQL
```

### Step 1 — Login

Playwright MCP opens `https://www.patreon.com/notifications?mode=user`. Login uses credentials stored in Claude's memory (not in code or .env). The Playwright session caches auth cookies in the MCP chrome profile.

### Step 2 — Extract post links

JavaScript runs in the browser context via `browser_run_code`:
```javascript
document.querySelectorAll('a[href*="/posts/"]')
```
Returns an array of post URLs for Danny's content.

### Step 3 — Batch navigate posts

Playwright navigates each post URL sequentially. Technical notes from the pipeline spec:
- CORS issues require in-browser navigation (not fetch)
- Patreon is a SPA — use `waitUntil: domcontentloaded`
- Each post's text content is extracted from the DOM

### Step 4 — Save raw text

Each post is saved as a `.txt` file named by Patreon post ID:
```
data/raw/154974647.txt
data/raw/154744601.txt
data/raw/154973712.txt
... (31 files total for current dataset)
```

A concatenated dump also exists: `data/raw/danny_posts_raw_dump.txt` (67 KB).

### Step 5 — Parse and import

Three Python parsers convert raw/structured markdown into observation dicts:

| Parser | Input | Output |
|---|---|---|
| `parse_ticker_history.py` | `data/structured/TICKER_HISTORY.md` | Per-ticker signal observations |
| `parse_watchlist.py` | `data/structured/WATCHLIST_AND_TIMELINE.md` | Ranked watchlist with sectors |
| `parse_batch_structured.py` | `data/structured/batch{1..4}_structured.md` | Per-post structured extractions |

The CLI importer (`scripts/import_dannytrades.py`) runs all 3 parsers, deduplicates by symbol, computes F6 whale trends, and atomically inserts into PostgreSQL via BOSS API's `get_connection()`.

## Credentials

| Item | Location |
|---|---|
| Patreon login (julievilla2002@gmail.com) | `~/.claude/projects/-home-david-SMITHEY-MOS/memory/kartra/credentials/reference_patreon_access.md` |
| Playwright cached session | `~/.cache/ms-playwright/mcp-chrome-*/Default/IndexedDB/https_www.patreon.com_0.indexeddb.leveldb/` |

Credentials are NOT in code, NOT in .env, NOT in any committed file.

## File inventory

### Raw data (from Patreon)
```
/home/david/DannyTrades/data/raw/*.txt              — 31 individual post extractions
/home/david/DannyTrades/data/raw/danny_posts_raw_dump.txt  — 67 KB concatenated dump
/home/david/DannyTrades/data/raw/brief_print.pdf    — 180 KB
```

### Structured data (parsed output)
```
/home/david/DannyTrades/data/structured/TICKER_HISTORY.md           — 39 KB
/home/david/DannyTrades/data/structured/WATCHLIST_AND_TIMELINE.md   — 21 KB
/home/david/DannyTrades/data/structured/batch1_structured.md        — 24 KB
/home/david/DannyTrades/data/structured/batch2_structured.md        — 18 KB
/home/david/DannyTrades/data/structured/batch3_structured.md        — 15 KB
/home/david/DannyTrades/data/structured/batch4_structured.md        — 25 KB
/home/david/DannyTrades/data/structured/DannyTrades_Market_History.md — 1.3 KB
```

### JSON extractions
```
/home/david/DannyTrades/data/json/danny_batch1.json
/home/david/DannyTrades/data/json/danny_batch1_raw.json
/home/david/DannyTrades/data/json/danny_test.json
```

### Python parsers (in SMITHEY_MOS)
```
control_plane_v2/services/dannytrades_parsers/parse_ticker_history.py
control_plane_v2/services/dannytrades_parsers/parse_watchlist.py
control_plane_v2/services/dannytrades_parsers/parse_batch_structured.py
control_plane_v2/services/dannytrades_importer.py        — main import orchestrator (697 lines)
control_plane_v2/services/dannytrades_api_service.py     — API envelope builder (725 lines)
control_plane_v2/scripts/import_dannytrades.py           — CLI entrypoint
control_plane_v2/scripts/retire_dannytrades_run.py       — run retirement
```

### Pipeline spec
```
/home/david/DannyTrades/project_dannytrades_pipeline.md  — original pipeline specification
```

### Deprecated copies (on Desktop, not canonical)
```
/home/david/Desktop/Transfer to D2/danny_posts_raw_dump.txt
/home/david/Desktop/D Transfer Files Corrected/danny_*.json
```

## Tech stack

**Used:**
- Playwright MCP (Claude's browser automation via Model Context Protocol)
- JavaScript DOM extraction (querySelectorAll, innerText)
- Python 3 parsers (regex-based markdown table parsing)
- PostgreSQL (4 dannytrades_* tables)
- BOSS API / FastAPI (JSON envelope endpoint)
- CLI importer with content-hash idempotency

**NOT used:**
- Selenium
- BeautifulSoup / bs4
- Python requests library
- Puppeteer
- Scrapy
- curl-based scraping
- Any headless browser other than Playwright

## Future: automated scraper (Stage B-5)

The current method is interactive (Claude + Playwright MCP). Stage B-5 of the DannyTrades roadmap plans a standalone Playwright Python script that:
1. Authenticates via env var credentials (`PATREON_EMAIL`, `PATREON_PASSWORD`)
2. Scrapes HTML DOM automatically
3. Parses ticker tables
4. Feeds `run_import()` directly
5. Runs on Captain's schedule via scheduler UI

Until B-5 ships, the scraping method is the interactive Playwright MCP workflow documented above.
