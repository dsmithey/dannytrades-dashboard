<!-- FRANK WORKING MEMORY - NOT CANONICAL. Source of truth for MOS state is PG/API once the proper DannyTrades PG location exists. -->

# DannyTrades Frank Memory

Date: 2026-04-15
Agent: Frank / MOS Architect
Project: DannyTrades Dashboard productization

## Current Location

Active operational folder:

`/home/david/DannyTrades`

Requested temporary Frank memory folder:

`/home/david/DannyTrades/danny-trades-frank`

Purpose: hold Frank's DannyTrades project memories locally until MOS has the proper PostgreSQL-backed memory/product knowledge location.

## Productization Direction

Captain wants DannyTrades Product Inventory item 61 moved from a static dashboard/product into the MOS PG > API > JSON product architecture.

Current dashboard target:

`http://localhost:9210/dannytrades-dashboard.html`

Product inventory reference:

`http://localhost:9210/mos-product-inventory-v5.html`

Item 61 current character:

- DannyTrades Dashboard
- Running static product
- frontend exists
- backend/database/API flags should flip as part of productization

## Pipeline Stage

Current process stage is Brainstorm.

Captain's pipeline:

Idea -> Concept -> Brainstorm -> Spec Doc -> PR peer review -> Plan -> Register as sidebar or Directive with R# value.

This work should not jump straight to implementation. The brainstorm output should become a spec document, then peer review, then plan, then registration/promotion.

## Architecture Recommendation

Use Option A first: dashboard-only PG/API/JSON migration, not full pipeline rehost.

Important refinement: Option A should not be a dumb mirror of hardcoded JavaScript arrays. It should be a durable product data contract:

- PG-backed run model
- current + previous ticker observations
- API endpoint for dashboard JSON
- dashboard loader replaces hardcoded arrays
- schema placeholders for richer Danny signals
- manual refresh from MOS API
- no realtime market quote provider in A unless Captain separately chooses provider/API key policy

Option B later:

- rehost scraper and parser
- raw posts written to PG
- parser writes structured facts to PG
- markdown becomes export, not canonical operational data

## Feature Recommendations

A-stage include:

- top signal panels with semantic color keys
- golden cross color coordination
- Daily Reds, Weekly Reds, Monthly Reds tabs
- popup stock lists for red tabs
- heatmap click popup shell
- ticker summary popup fields for support, resistance, bullish thesis, invalidation, volatility holes
- unified ticker table/graph with price, day change, red status, golden cross, support/resistance, whale accumulation
- whale accumulation trend color using current + previous observations
- latest import run metadata
- parser confidence and needs-review fields
- manual refresh from PG/API

Defer:

- realtime quote integration
- external quote provider API keys
- full scraper rehost
- automatic parser rewrite
- writeback Captain notes
- alert engine
- full historical charting

## Open Decisions Signed Off By Frank

1. `color_key` pattern accepted with constraint:
   - API emits semantic keys.
   - Frontend owns actual CSS values.
   - Do not store raw hex colors as product truth.

2. Include previous whale accumulation details in API payload:
   - `previous_whale_accumulation_pct`
   - `whale_accumulation_delta`
   - `whale_accumulation_trend`

3. Use separate curated-list tables:
   - `dannytrades_core_positions`
   - `dannytrades_buy_orders`
   These are Captain-curated product views, not observation flags.

4. Support query params from day one:
   - default: latest run, all tickers
   - `?run_id=<uuid>`: specified run
   - `?symbol=NVDA`: latest run, one ticker
   - both together: specified run, one ticker

5. Importer should be CLI script first, API wrapper later:
   - `python scripts/import_dannytrades.py --from /home/david/DannyTrades --label weekly-YYYY-MM-DD`
   - Later wrap same importer behind POST endpoint if remote trigger is needed.

6. Importer should be idempotent by content hash:
   - same source files should no-op or create an explicit duplicate candidate.
   - do not silently create confusing duplicate runs.

## Draft Schema Direction

Core tables:

- `dannytrades_runs`
- `dannytrades_ticker_observations`
- `dannytrades_core_positions`
- `dannytrades_buy_orders`

Observation table should be append-friendly so Option B can evolve into full time-series without table rewrite.

## API Direction

Primary endpoint:

`GET /api/v1/captain/dashboard/dannytrades`

Response should include:

- run metadata
- summary
- top panels
- heatmap
- red tabs
- ticker observations
- curated core positions
- curated buy orders

## Environment Direction

Realtime quotes should remain disabled in A unless Captain separately chooses provider, key handling, and refresh policy.

Reserved `.env` names:

```text
DANNYTRADES_QUOTES_PROVIDER=disabled
DANNYTRADES_QUOTES_API_KEY=
DANNYTRADES_REFRESH_INTERVAL_SEC=0
```

## Design Principle

Make the dashboard answer:

1. What should I look at first?
2. Why?
3. What invalidates the setup?

Target interaction:

- under 10 seconds to identify priority symbols
- one click to understand the setup

## Status

Temporary local Frank memory created pending proper PG memory/product knowledge location.
