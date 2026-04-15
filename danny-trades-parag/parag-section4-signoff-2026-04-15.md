# Parag — Section 4 Scope Closure Lock (Dashboard Rewrite + Realtime Querying + Quote Provider Boundary)

**Date:** 2026-04-15
**Agent:** Parag
**Thread:** T89
**Pipeline stage:** Brainstorm (`B`) — **final brainstorm section**
**Status:** LOCKED by Captain. Proceeding to Spec Doc (`S`) stage.

This file records Section 4 decisions plus the two brainstorm additions (realtime dashboard querying, quote provider boundary). Pairs with `parag-section2-scope-closure-2026-04-15.md` and `parag-section3-scope-closure-2026-04-15.md`.

---

## Section 4 — 9 decisions

| # | Topic | Decision |
|---|---|---|
| 1 | In-place HTML rewrite | **YES.** Same file, same URL: `captain-dashboard/dannytrades-dashboard.html`. No duplicate dashboard. |
| 2 | Declarative-first loader integration | **YES.** `dashboard-loader.js` handles `data-bind` / `data-bind-list` for most of the page. Custom `mos-data-loaded` event handler only for heatmap, popup, F1 color-key binding, sorting, red tabs. |
| 3 | CSS custom properties + `data-color-key` | **YES.** Semantic key from API (`golden_cross`, `daily_red`, etc.) → `data-color-key` attribute → CSS `var(--color-*)`. Preserves Section 2 color_key lock. |
| 4 | `.env` reserved names | **MODIFY.** Put reserved names in `.env.example` and spec/config docs. **Do not mutate live `/home/david/SMITHEY_MOS/.env`** in A. Reason: live `.env` is runtime state; A doesn't read these values yet. |
| 5 | Footer freshness strip | **YES.** Absolute + relative `imported_at`, `source_label`, `observation_count`, `needs_review_count`, short hash display. |
| 6 | `product_registry` item 61 update | **YES — option (c) flag flip only.** Set `has_backend/has_database/has_api/uses_postgresql=true`, `primary_port=7777`. Defer `metadata JSONB` column and `api_endpoint`/`source_repo_path`/`next_stage_directive` to a separate follow-up directive. Do not widen A's blast radius into shared-table schema. |
| 7 | Testing matrix | **YES + additions.** Added: (a) P-001 guardrail test — no SQLite imports or `.db`/`.sqlite`/`.sqlite3` artifacts introduced; (b) Empty-state dashboard test — no `complete` run → honest empty/error state; (c) Retired-run fallback test — retire latest run → previous `complete` run becomes current; (d) Query filter tests beyond `run_id`/`symbol`: red status, golden cross, whale trend, signal score. |
| 8 | Cutover, no parallel old/new | **YES + deployment gate.** Agreed on single-commit cutover. **Require at least one successful `complete` import before production cutover removes hardcoded arrays.** PR can include empty-state behavior, but operational cutover proves at least one complete run exists. |
| 9 | File inventory | **MODIFY.** Corrections: (a) Alembic path is `control_plane_v2/db/alembic/versions/...`, NOT `control_plane_v2/alembic/versions/...`. (b) Do NOT modify live `.env`; update `.env.example` or docs. (c) Keep `MultiAgent/Memory/julie/INDEX.md` OUT of A unless a memory directive is active — optional and unrelated to the product migration. |

---

## Addition 1 — Realtime dashboard querying (IN A, with bounds)

Rich query surface on `GET /api/v1/captain/dashboard/dannytrades` from day one.

| Param | Effect |
|---|---|
| `run_id=<uuid>` | Specific historical run, default = latest |
| `symbol=<text>` | Single ticker drilldown (case-insensitive; API returns normalized uppercase) |
| `include_test=true` | Unlock `test-*` runs for debug/admin (not used by A UI) |
| `red=daily\|weekly\|monthly` | Filter to red class |
| `golden_cross=true` | Filter to tickers with any `golden_cross` text |
| `whale_trend=increasing\|same\|decreasing` | Filter by F6 trend |
| `needs_review=true` | Filter to parser-flagged rows |
| `sector=<text>` | Case-insensitive substring match |
| `min_signal_score=<int>` | Filter by computed Signal Score |
| `limit=<int>` | **Bounded: default 100, max 500. No unbounded query path.** |
| `sort=signal_score_desc\|whale_pct_desc\|symbol_asc` | Result ordering |

**Semantics:** AND across params. Default response = latest complete non-test run + all tickers + limit 100.

**Sector resolution (Captain-approved):** import-time cross-reference from the curated sector groups in the source markdown. If sector cannot be resolved for a ticker, store `sector=NULL` — do not invent.

**Signal Score (from Section 2 Q1):** computed in Python at API time, no stored column. For current scale (~52 rows) Python filter+sort is free. Stored column / materialized view is a B-stage concern if dataset grows 10K+.

---

## Addition 2 — Quote provider boundary (ARCHITECTURE ONLY in A)

**IN A:**
- API envelope reserves optional `"quote": null` field on observation rows
- UI footer and ticker table render *"Quotes: Not connected"*
- `.env.example` reserves `DANNYTRADES_QUOTES_PROVIDER=disabled`, `DANNYTRADES_QUOTES_DELAY_MINUTES=0`, `DANNYTRADES_QUOTES_API_KEY=`
- Spec documents the future provider boundary: abstract `MarketQuoteProvider` base class; future concrete classes `YahooDelayedProvider` and `TradingViewProvider`
- Spec notes shared-concern `market_quote_snapshots` table intended for cross-product reuse when that directive lands

**NOT IN A:**
- `market_quote_snapshots` table creation
- Yahoo fetcher implementation
- Quote adapter implementation
- Quote snapshot ingestion
- Quote-provider tests beyond null/envelope rendering
- Live `.env` mutation

**Rationale (Captain):** "A was cleanly scoped as DannyTrades signal productization. The quote layer is a separate shared subsystem and should not sneak in through this spec." Quote subsystem gets its own small directive so it lands once for all MOS products, not as a DannyTrades sidecar.

---

## Frontend stack decision — captain-dashboard static, not React (for A)

**Locked for A:** captain-dashboard static HTML + `dashboard-loader.js` + BOSS API endpoint + PostgreSQL-backed JSON.

**Promotion trigger (deferred, documented in spec "Later stages"):** Promote DannyTrades UI to React when any of: (a) `dannytrades-dashboard.html` exceeds ~1500 lines of vanilla JS, (b) a feature requires proper client state management, (c) the cockpit vision's ticker compare / watchlist builder / alert candidates panel lands.

**Promotion target (when it happens):** Next.js `ui/` (port 3060, React 19), NOT Vite `mos-dashboard/` (React 18, older/separate). Consolidation win.

---

## Combined final A scope (brainstorm-locked)

### Backend
- 4 new tables: `dannytrades_runs`, `dannytrades_ticker_observations`, `dannytrades_core_positions`, `dannytrades_buy_orders`
- Schema migration via alembic at `control_plane_v2/db/alembic/versions/`
- 1 `product_registry` row UPDATE for item 61 (flag flip only, no schema change)
- Importer CLI: `control_plane_v2/scripts/import_dannytrades.py`
- Retire tool CLI: `control_plane_v2/scripts/retire_dannytrades_run.py`
- Importer service: `control_plane_v2/services/dannytrades_importer.py`
- API service: `control_plane_v2/services/dannytrades_api_service.py`
- FastAPI router: `control_plane_v2/mosboss/api/dannytrades.py`
- Unit + integration + contract tests

### Frontend
- Rewrite `captain-dashboard/dannytrades-dashboard.html` in place
- Add `<meta name="mos-endpoint">` + `<script src="dashboard-loader.js">`
- Rip out 7 hardcoded JS arrays
- Add declarative `data-bind` / `data-bind-list` / `<template>` markup
- Add custom `mos-data-loaded` handler for heatmap, popup, sort, color-key binding, red tabs
- Add CSS custom properties for color_key mapping
- Add empty-state shell + error banner
- Add footer freshness strip

### Docs / config
- `.env.example` reserved DannyTrades + quote-provider names
- `docs/superpowers/specs/2026-04-15-dannytrades-pg-api-json-migration-design.md` — the spec
- Spec cross-references to `/home/david/DannyTrades/danny-trades-parag/` and `danny-trades-frank/` closure files

### Deferred (captured in spec North Star, not in A)
- Full Patreon scraper rehost (B)
- Realtime market quote integration + Yahoo adapter + TradingView swap (separate directive)
- `market_quote_snapshots` shared table (separate directive)
- `product_registry.metadata JSONB` column (separate directive)
- `--force-review` importer flag (separate directive if ever needed)
- Full Import Runs tab UI (separate directive)
- Diff highlighting beyond F6 (separate directive)
- Signal Score tuning UI (formula in API code, no user-editable surface)
- Watchlist Builder, Alert Candidates, Ticker Compare, full historical charting, Export CSV/MD/PDF
- React/Next.js frontend promotion (concrete trigger documented, deferred directive)
- Captain-editable notes per ticker (would convert A from read-only → interactive)

---

## Next steps

1. **Write spec doc** → `docs/superpowers/specs/2026-04-15-dannytrades-pg-api-json-migration-design.md`
2. **Spec self-review** (placeholder scan, contradiction check, scope check, ambiguity check) — fixes inline
3. **User review gate** — Captain reviews the spec file, requests changes or approves
4. **PR stage** — Captain's newly-added peer review step; another agent critiques the spec (likely Anand or NRavi)
5. **Plan stage** — `superpowers:writing-plans` skill only after PR + user approval
6. **Register** — sidebar entry OR promote to directive with R# in PG
