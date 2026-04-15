# Parag Project Memory — DannyTrades PG/API/JSON Migration

**Agent:** Parag (Code Reviewer, canonical_agent_uid `194b0b2a-5ed8-4838-9e81-b3f2c55c73d2`)
**Thread:** T89
**Session:** 2026-04-15 (headless, Claude Code CLI)
**Topic:** Migrate DannyTrades dashboard from static HTML + hardcoded JS arrays to PG>API>JSON data plane. Product inventory item 61.
**Parallel agent:** Frank — `/home/david/DannyTrades/danny-trades-frank/` holds Frank's working memory for the same project.
**Pipeline stage:** Brainstorm (`B`) per Captain's MOS development pipeline (I → C → B → S → PR → P → sidebar/D).
**Memory status:** Temporary. Captain will migrate agent project memories to a PG location once the schema exists. Until then, every project memory note goes in this folder.

---

## Why this folder exists

Captain's directive 2026-04-15: keep per-agent project memories for DannyTrades out of the flat auto-memory layer and out of the main memory garden. Mirror Frank's folder pattern (`danny-trades-frank/`) with `danny-trades-parag/` sitting next to it in the operational repo. Each agent accumulates working memory in their own subfolder until a proper PG-backed per-agent project memory table exists.

This is **scaffolding**, not canon. When PG migration of agent memories lands, this folder gets imported as historical rows and then frozen or deleted.

---

## Session working state as of 2026-04-15 ~01:30 CDT

### What was accomplished pre-brainstorm in this session

1. Parag boot to T89 — ONLINE, compliance ALL CLEAR. Inbox: 6 messages queued.
2. **Memory-garden cleanup:** Julie auto-memory reference `reference_seedance_2_0.md` updated earlier but session learnings were ultimately routed to `media-Seedance 2.0/LEARNINGS.md` per Captain's clarification ("special folder location" = that folder, not garden and not auto-memory).
3. **fal.ai session** (prior task): Seedance 2.0 image-to-video + Nano Banana Pro edit experiments on a Soul Steward infographic. Spend ~$6.19 of $30 credit. Learnings captured at `/home/david/SMITHEY_MOS/media-Seedance 2.0/LEARNINGS.md` (Seedance 720p cap, native audio default, flat-infographic anti-pattern, Nano Banana Pro edit-endpoint source-preservation bias, Ken Burns ffmpeg canonical form, absolute-paths-in-background-bash lesson). Not directly related to DannyTrades but part of the same session context.
4. **Nano Banana Pro image delivery:** two PNGs copied to `~/Downloads/`, Gmail MCP draft created (`r-4189164025009596867`) for Captain to attach-and-send manually (MCP tool lacks attachment support — important known limitation).
5. **DannyTrades folder audit** (just before brainstorm): SQLite scan clean, diff between `/home/david/DannyTrades` and `/home/david/Desktop/D Transfer Files Corrected/DannyTrades` showed B is a 100% duplicate superset of A with a `raw_posts/raw_posts/` recursive-copy glitch. Trashed B + 4 loose markdown mirrors via `gio trash` (reversible). Canonical `/home/david/DannyTrades` untouched, 47 files intact.

### Brainstorm pipeline decisions so far

Captain formally invoked the pipeline structure: **I → C → B → S → PR → P → sidebar-or-D(R#)**. We are in B.

**Scope decision locked:** A (dashboard-only migration) + F6 option-(b) (current + previous observations for whale-accumulation trend color). See `parag-section2-scope-closure-2026-04-15.md` for the full Q1/Q2/Q3 lock.

**Product vision** (Captain's full "signal intelligence cockpit" North Star) captured separately as the spec's `## Product North Star (full vision, multi-stage)` section. This is multi-stage vision, NOT A scope. A scope is explicitly smaller and fits the 12-item list Captain wrote at the bottom of the cockpit-vision message.

### Schema shape locked in Section 1

**New tables:**

- `dannytrades_runs` — one row per import. Columns: `id UUID PK, source_label TEXT, source_path TEXT, imported_at TIMESTAMPTZ, imported_by TEXT, observation_count INT, parse_notes TEXT, needs_review_count INT`.
- `dannytrades_ticker_observations` — one row per ticker per run. Columns: `id, run_id FK, symbol VARCHAR(10), company_name, sector, price_snapshot NUMERIC(12,4), day_change_pct NUMERIC(6,3), whale_accumulation_pct NUMERIC(6,3) NOT NULL, whale_accumulation_trend VARCHAR(10) CHECK IN (increasing,same,decreasing), golden_cross TEXT, red_daily BOOL, red_weekly BOOL, red_monthly BOOL, support_area TEXT, resistance_area TEXT, bullish_thesis TEXT, invalidation_level TEXT, volatility_holes JSONB, source_post_refs TEXT[], observation_as_of DATE NOT NULL, extraction_confidence VARCHAR(6) CHECK IN (high,medium,low), needs_review BOOL DEFAULT FALSE, parse_notes TEXT, created_at TIMESTAMPTZ DEFAULT NOW()`.
- `dannytrades_core_positions` — Captain-curated. Columns: `id, symbol, range_text, thesis, active, sort_order, source_note, created_at, updated_at`.
- `dannytrades_buy_orders` — Captain-curated. Columns: `id, symbol, range_text, order_type, active, sort_order, source_note, created_at, updated_at`.

**Key decisions on schema:**

- `observation_as_of DATE` added (not in Captain's original draft) because trend math must compare same-ticker across real-world signal dates, not import timestamps. Prevents trend corruption if a re-import happens.
- `whale_accumulation_trend` stored, not computed — captured at import time for auditability.
- `golden_cross` is TEXT not BOOL because current data has strings like *"Forming on weekly"*, *"Confirmed Apr 7"*.
- `volatility_holes` is JSONB for structured-but-variable shape.
- **No DELETE policy in A.** Table grows; API query picks top-2 per symbol via `DISTINCT ON`. Disk cost ~1.6 MB/year — negligible.
- Indexes: `(run_id, symbol) UNIQUE`, `(symbol, observation_as_of DESC)` hot path for F6, `(run_id)`, `(whale_accumulation_pct DESC)`.

### API contract shape locked in Section 2

**Endpoint:** `GET /api/v1/captain/dashboard/dannytrades`

**Envelope:**

```
{
  "run": { "current": {...}, "previous": {...}, "data_freshness_hours": N },
  "summary": { "total_tickers", "avg_whale_accumulation_pct", "golden_cross_count", "red_daily_count", "red_weekly_count", "red_monthly_count", "trending_up_count", "trending_down_count", "needs_review_count" },
  "topPanels": {
    "core_positions": { "title", "color_key", "items": [] },
    "golden_crosses": { "title", "color_key": "gold", "items": [] },
    "buy_orders": { "title", "color_key": "green", "items": [] },
    "bearish": { "title", "color_key": "red", "items": [] }
  },
  "heatmap": [ { "symbol", "whale_pct", "trend", "heat_bucket" } ],
  "redTabs": { "daily": {count,items}, "weekly": {count,items}, "monthly": {count,items} },
  "tickerObservations": [ full observation rows, each with: symbol, company_name, sector, observation_as_of, price_snapshot, day_change_pct, whale_accumulation_pct, whale_accumulation_trend, previous_whale_accumulation_pct, whale_accumulation_delta, golden_cross, red_daily, red_weekly, red_monthly, support_area, resistance_area, bullish_thesis, invalidation_level, volatility_holes, source_post_refs, extraction_confidence, needs_review, parse_notes, signal_score (computed at API time) ]
}
```

**Color-key vocabulary locked (Captain's exact names):** `golden_cross`, `daily_red`, `weekly_red`, `monthly_red`, `whale_up`, `whale_flat`, `whale_down`, `neutral`, `risk`. API owns semantic; CSS owns hex.

**Query params:**
- `?run_id=<uuid>` — specific historical run
- `?symbol=NVDA` — single ticker (case-insensitive, API normalizes to uppercase in response)
- Combinations allowed; default = latest run + all tickers

**Frontend business-logic rule:** API returns `whale_accumulation_delta` + `whale_accumulation_trend` + `previous_whale_accumulation_pct` as pre-computed fields. Frontend renders, does not compute.

### Importer decisions (partial; Section 3 starts next)

- **CLI script first:** `python scripts/import_dannytrades.py --from /home/david/DannyTrades --label weekly-2026-04-15`
- **Idempotency by content hash:** same source files → no-op OR marked duplicate candidate, never silent duplicate (Captain's explicit refinement).
- **No API endpoint for import in A.** POST wrapper deferred to B.
- Open Section 3 questions: markdown parser brittleness, first-run F6 backfill story, run label convention, error handling on garbage rows, transaction granularity.

### Deferred from A (recorded for B stage and beyond)

- Realtime market quote integration (needs provider + .env key + rate-limit policy)
- Automatic Patreon scraper rehost (B territory)
- Captain-editable notes per ticker (changes product from read-only to interactive)
- Full "Import Runs" tab (A ships footer-only data-freshness strip)
- Full diff highlighting beyond whale trend (new tickers, removed tickers, new golden crosses, etc.)
- Signal Score tuning UI (formula is in API code, not user-editable in A)
- Watchlist Builder
- Alert Candidates panel
- Ticker Compare view
- Full historical charting
- Export (CSV / markdown / PDF)

### `.env` reserved-but-disabled pattern (Captain's instruction)

A ships with these env var names reserved but unused:

```
DANNYTRADES_QUOTES_PROVIDER=disabled
DANNYTRADES_QUOTES_API_KEY=
DANNYTRADES_REFRESH_INTERVAL_SEC=0
```

Prevents A from leaking into API-key/rate-limit/cost decisions while keeping the naming contract stable.

### Product registry row update (part of A)

Item 61 in `product_registry` (id `bb6b3d9d-a89d-45cc-a6e3-d5010a29d531`) flips from:

```
has_backend=false, has_database=false, has_api=false, uses_postgresql=false
primary_port=null, sqlite_violation=false
```

to:

```
has_backend=true, has_database=true, has_api=true, uses_postgresql=true
primary_port=7777
api_endpoint=/api/v1/captain/dashboard/dannytrades
source_repo_path=/home/david/DannyTrades
next_stage_directive="B: full pipeline rehost (ingest directly to PG)"
```

**Open question for Section 4:** does `product_registry` already have a `metadata JSONB` column? If yes, `api_endpoint` / `source_repo_path` / `next_stage_directive` go there instead of new columns.

---

## What's still open (as of this memory write)

- **Section 3 (importer / ingest)** — idempotency implementation, parser format assumption, first-run F6 backfill, run label convention, error handling, transaction granularity. **Not yet presented to Captain.**
- **Section 4 (dashboard rewrite + registry update)** — ripping out the 7 hardcoded JS arrays, integrating `dashboard-loader.js` or a custom fetcher, top-panel CSS color-key mapping, product_registry metadata-column question. **Not yet presented to Captain.**
- **Spec doc** (S stage) — written after Sections 3 and 4 are locked.
- **Spec self-review** — placeholder scan, contradiction check, scope check, ambiguity check.
- **PR stage** — peer review. Captain's newly-added stage. Target reviewer unclear — probably Anand or NRavi.
- **Plan stage** — via `superpowers:writing-plans` only after PR passes.
- **Register as sidebar OR promote to Directive** — final registration decision.

---

## References and related files

- **Frank's parallel memory:** `/home/david/DannyTrades/danny-trades-frank/frank-memory-2026-04-15.md` + `frank-section2-scope-closure-2026-04-15.md`
- **Canonical DannyTrades repo:** `/home/david/DannyTrades/` (git-versioned)
- **Dashboard HTML (target of rewrite):** `/home/david/SMITHEY_MOS/captain-dashboard/dannytrades-dashboard.html` (916 lines, 7 hardcoded JS arrays to rip out)
- **Inventory page (item 61 host):** `/home/david/SMITHEY_MOS/captain-dashboard/mos-product-inventory-v5.html`
- **Pattern to mirror (PG-backed dashboard):** same `mos-product-inventory-v5.html`, uses `<meta name="mos-endpoint">` + fetch-and-render loader
- **Pipeline doc (upstream truth about how DannyTrades data gets made):** `/home/david/DannyTrades/project_dannytrades_pipeline.md`
- **Parag auto-memory index:** `/home/david/.claude/projects/-home-david-SMITHEY-MOS/memory/MEMORY.md`
- **Parag feedback rule — always recommend:** `feedback_always_recommend.md`
- **Parag feedback rule — stop hedging on cheap wins:** `feedback_stop_hedging_cheap_wins.md`
- **Parag feedback rule — never bulk-modify without Captain's plan:** `feedback_bulk_file_ops.md` (honored this session via `gio trash` + explicit plan preview before execution)
