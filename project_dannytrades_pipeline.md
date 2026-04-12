---
name: DannyTrades Market Ingestion Pipeline
description: Patreon scraping pipeline for DannyTrades stock analysis — speed ingestion via Playwright, parallel parsing, structured output
type: project
originSessionId: 059c1cbc-93bb-4fbf-aa9d-c777db8609b3
---
Desktop folder: `Danny Trades/`
GitHub Pages: https://dsmithey.github.io/dannytrades-dashboard/
Repo: https://github.com/dsmithey/dannytrades-dashboard

**Pipeline steps:**
1. Navigate Playwright to patreon.com/notifications?mode=user, log in
2. Extract all DannyTrades post links via JS querySelectorAll('a[href*="/posts/"]')
3. Use `browser_run_code` to batch-navigate posts (10-25 per batch), extract `main.innerText`, return JSON
4. Dispatch parallel agents (one per date-range batch) to parse raw text into structured markdown tables
5. Build three views: Ticker History (day-by-day), Watchlist Summary (ranked by whale accum), Executive Brief

**Key technical lessons:**
- Must use `www.patreon.com` not `patreon.com` for fetch — CORS issue
- Static HTML fetch + DOMParser does NOT work — Patreon is a SPA, must navigate and extract rendered content
- `browser_run_code` is the fastest batch method — runs full Playwright scripts with page.goto() in a loop
- Use `waitUntil: 'domcontentloaded'` + 2s wait for dynamic content rendering
- Snapshot output can exceed token limits — use depth parameter or JS extraction instead

**Files in Danny Trades/:**
- EXECUTIVE_BRIEF.md/.pdf — Shareable executive summary
- TICKER_HISTORY.md — Day-by-day per ticker
- WATCHLIST_AND_TIMELINE.md — Ranked watchlist + chronological post index  
- APPROACH.md — Full methodology documentation
- dashboard.html — Interactive visual dashboard (also deployed to GitHub Pages)
- batch1-4_structured.md — Raw structured data by date range

**Why:** David wants ongoing market analysis tracking from DannyTrades' proprietary signals (whale accumulation, red/yellow candles, golden crosses). Data used for investment decision support.

**How to apply:** When David asks to update or re-run the Danny analysis, follow this pipeline. Can be repeated weekly.
