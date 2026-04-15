# DannyTrades — Operational Folder + Agent Onboarding

**Owner:** Captain Smithey
**Active thread:** T89 (as of 2026-04-15)
**Canonical path:** `/home/david/DannyTrades`
**Status:** Active, productization in flight
**Pipeline stage:** Brainstorm (`B`) — DannyTrades PG/API/JSON migration spec in progress

---

## Authority Boundary

This folder is the operational working folder for DannyTrades productization. **It is not canonical MOS governance state.**

Canonical MOS state remains PostgreSQL via BOSS API. Project memory in `danny-trades-frank/`, `danny-trades-parag/`, or any future agent folders is **temporary working memory** until a PG-backed project-memory location exists.

Do **not** cite files in this folder as directive state, completion state, or review state. For directive status, lifecycle gates, or compliance attestation, use the **BOSS API / PostgreSQL** authority at `http://localhost:7777` — that is the source of truth.

When the PG-backed per-agent project memory table lands, the contents of `danny-trades-*/` subfolders will be imported as historical rows, then frozen or deleted. Treat this folder as scaffolding, not as canon.

### P-001 compliance (no SQLite)

No SQLite, `.db`, `.sqlite`, `.sqlite3`, or `sqlite3` runtime use is permitted in this project. DannyTrades A migrates toward **PostgreSQL > API > JSON** only. Folder was audited clean 2026-04-15 — zero SQLite imports, zero database file extensions. Any future import tool, parser, or dashboard binding must use PostgreSQL via the BOSS API contract. Violations are hard stops.

---

## What this folder is

`/home/david/DannyTrades/` is the canonical operational home for the DannyTrades product — a weekly Patreon-scraping pipeline that turns Danny's stock-signal posts into structured market-intelligence artifacts (ticker history, watchlist, executive brief, interactive dashboard).

It is **git-versioned** and is the upstream source of truth for everything downstream, including the MOS product inventory item 61 dashboard at `http://localhost:9210/dannytrades-dashboard.html`.

Do not confuse this folder with the deleted `/home/david/Desktop/D Transfer Files Corrected/DannyTrades/` — that was a 100% duplicate of this folder (plus a recursive-copy glitch) and was trashed 2026-04-15 during pre-brainstorm cleanup.

---

## If you are a joining agent — read this first

1. **Find out what stage the project is in.** Check the newest dated file in `danny-trades-frank/` and `danny-trades-parag/`. The highest-date file is the current working state.
2. **Read the stage-closure files in order.** Each stage (`sectionN-scope-closure-YYYY-MM-DD.md`) locks decisions that downstream stages depend on. Do not re-open a locked decision without Captain's signoff.
3. **Check your own agent folder first.** If your agent name has a subfolder here (e.g. `danny-trades-parag/`, `danny-trades-frank/`), your prior working memory lives there. Load it before touching the project.
4. **If you don't have a folder, create one** with the naming convention `danny-trades-<your-agent-name>/` and seed it with an onboarding memory file: `<agent>-memory-YYYY-MM-DD.md`. Captain wants per-agent project memory separated until the PG-backed memory table exists.
5. **Honor the scope lock.** The current A-scope lock lives in `danny-trades-parag/parag-section2-scope-closure-2026-04-15.md`. Frank's version is in `danny-trades-frank/frank-section2-scope-closure-2026-04-15.md`. They should agree — if they don't, flag the drift to Captain before acting.
6. **Use the MOS development pipeline stages**: I → C → B → S → PR → P → (sidebar OR D with R#). Know which stage you're in before writing anything.

---

## Folder layout

```
/home/david/DannyTrades/
├── README.md                                       ← this file (agent onboarding)
├── project_dannytrades_pipeline.md                 ← upstream pipeline spec (weekly scrape → parse → render)
├── index.html                                      ← deployed GitHub Pages dashboard (legacy, pre-migration)
├── data/
│   ├── raw/                                        ← one .txt per scraped Patreon post (~30 posts current)
│   │   └── danny_posts_raw_dump.txt                ← concatenated debug dump from a prior run
│   ├── structured/                                 ← parsed markdown tables (canonical output today)
│   │   ├── batch1_structured.md
│   │   ├── batch2_structured.md
│   │   ├── batch3_structured.md
│   │   ├── batch4_structured.md
│   │   ├── TICKER_HISTORY.md
│   │   ├── WATCHLIST_AND_TIMELINE.md
│   │   └── DannyTrades_Market_History.md
│   └── json/                                       ← raw Playwright extraction dumps
│       ├── danny_batch1.json
│       ├── danny_batch1_raw.json
│       └── danny_test.json
├── reports/
│   ├── EXECUTIVE_BRIEF.md                          ← shareable summary
│   ├── EXECUTIVE_BRIEF.pdf
│   ├── brief_print.html
│   └── dashboard-v1.html                           ← earlier dashboard iteration
├── danny-trades-frank/                             ← Frank's per-agent working memory
│   ├── frank-memory-2026-04-15.md
│   └── frank-section2-scope-closure-2026-04-15.md
├── danny-trades-parag/                             ← Parag's per-agent working memory
│   ├── parag-memory-2026-04-15.md
│   └── parag-section2-scope-closure-2026-04-15.md
├── danny-trades-anand/                             ← Anand's per-agent working memory
│   └── anand-memory-2026-04-15.md
└── .git/                                           ← version control
```

---

## What is happening right now (2026-04-15)

Captain initiated migration of DannyTrades from a **static HTML dashboard with 7 hardcoded JS arrays** into the MOS **PG > API > JSON** architecture. Product inventory item 61 (`bb6b3d9d-a89d-45cc-a6e3-d5010a29d531`) currently has `has_backend=false, has_database=false, has_api=false, uses_postgresql=false` — the migration flips all four flags true and gives the product a real data plane.

**Scope locked for directive A** (dashboard-only migration with F6 whale-trend baked in):

1. PG schema — new tables: `dannytrades_runs`, `dannytrades_ticker_observations`, `dannytrades_core_positions`, `dannytrades_buy_orders`
2. BOSS API endpoint — `GET /api/v1/captain/dashboard/dannytrades` with `?run_id=` and `?symbol=` query params
3. Dashboard JSON loader — replace hardcoded JS arrays in `captain-dashboard/dannytrades-dashboard.html` with a fetcher
4. Top signal cards (F1 color-coordinated top-panel ↔ detail sections)
5. Daily / Weekly / Monthly Reds tabs with popup lists (F4)
6. Golden cross color coordination
7. Heatmap click popup shell (F2 popup structure, B fills richer extracted data)
8. Ticker intelligence table with Signal Score (computed at API time, no DB column)
9. Current + previous whale accumulation trend color (F6, the smart win)
10. Manual refresh-from-PG button (no realtime quotes)
11. Data freshness footer strip (latest import, source path, posts processed, tickers extracted, warnings, content hash status)
12. Parser confidence / needs_review fields

**Deferred to B or later** (captured in spec North Star but not in A):
- Full Patreon scraper rehost to PG
- Realtime market quote integration (needs provider + `.env` API key governance)
- Captain-editable notes per ticker (would turn A from read-only → interactive)
- Full Import Runs tab (A ships footer only)
- Full diff highlighting beyond F6 (new tickers, removed tickers, new golden crosses, etc.)
- Watchlist Builder
- Alert Candidates panel
- Ticker Compare view
- Full historical charting
- Export (CSV / markdown / PDF)
- Signal Score tuning UI (formula in API code, not user-editable)

**`.env` reserved-but-disabled pattern** (A ships these names unused):

```
DANNYTRADES_QUOTES_PROVIDER=disabled
DANNYTRADES_QUOTES_API_KEY=
DANNYTRADES_REFRESH_INTERVAL_SEC=0
```

---

## Key downstream references outside this folder

| What | Where |
|---|---|
| Product inventory page (item 61 lives here) | `/home/david/SMITHEY_MOS/captain-dashboard/mos-product-inventory-v5.html` |
| Dashboard HTML (target of the rewrite) | `/home/david/SMITHEY_MOS/captain-dashboard/dannytrades-dashboard.html` (916 lines, 7 hardcoded arrays) |
| Existing PG-backed dashboard pattern to mirror | `/home/david/SMITHEY_MOS/captain-dashboard/mos-product-inventory-v5.html` (uses `<meta name="mos-endpoint">` + JSON loader) |
| Product registry live query | `GET http://localhost:7777/api/v1/captain/dashboard/products` → item with `card_number: 61` |
| BOSS API canonical port | `7777` (Docker `mos_boss_api`) |
| Captain dashboard web port | `9210` (Python `serve.py`) |
| GitHub Pages legacy deployment | https://dsmithey.github.io/dannytrades-dashboard/ |
| Repo | https://github.com/dsmithey/dannytrades-dashboard |
| Upstream pipeline doc | `project_dannytrades_pipeline.md` (this folder) |

---

## Working rules for agents on this project

1. **Memory lives here for now.** Per-agent project memory for DannyTrades goes in your `danny-trades-<agent>/` subfolder, **not** in the flat auto-memory layer and **not** in the Julie memory garden. This is temporary scaffolding until a PG-backed per-agent project memory table exists; then this folder gets imported and frozen.
2. **Do not modify canonical upstream data** in `data/raw/`, `data/structured/`, `data/json/`, or `reports/` unless Captain explicitly asks. These are the outputs of the weekly pipeline and any changes break the migration's parser assumptions.
3. **Do not commit the `.git` under this folder into the main SMITHEY_MOS repo.** This folder has its own git history.
4. **Scope locks are sacred.** Sections 1 and 2 of the migration spec are locked by Captain's signoff. Do not re-open a locked decision without asking. If you have a strong objection, surface it as a new question at the current pipeline stage, not as a quiet edit.
5. **Two-agent alignment.** Frank and Parag are both working on this. Their memories should not drift on locked decisions. If you notice divergence between the two `*-section2-scope-closure-*` files, flag it to Captain immediately — it means someone missed a lock.
6. **Pipeline discipline.** Every decision must be made at the right pipeline stage:
   - **I** (Idea) — Captain drops a thought
   - **C** (Concept) — narrow the intent to one paragraph
   - **B** (Brainstorm) ← *currently here* — questions → approaches → design sections → approval
   - **S** (Spec doc) — committed to `docs/superpowers/specs/YYYY-MM-DD-*-design.md`
   - **PR** (Peer review) — another agent critiques the spec
   - **P** (Plan) — via `superpowers:writing-plans` skill, never earlier
   - **Register** — either sidebar entry or promotion to directive with R# in PG
7. **Always recommend.** Parag's Cardinal Rule #1: every question Captain asks includes a recommendation, not a menu of options without a pick.
8. **Stop hedging on cheap wins.** If an improvement is concrete, small, and targets a real failure mode, propose it firmly. No "your call" softening on code bugs or silent-pass paths.
9. **Honor SQLite prohibition (P-001).** The DannyTrades migration is PostgreSQL-only. No SQLite files, no `import sqlite3`, no `.db` anywhere. Folder has been audited clean as of 2026-04-15.

---

## How to pick up where we left off

If the brainstorm conversation was interrupted and you need to resume as Parag:

1. Read `danny-trades-parag/parag-memory-2026-04-15.md` for the full working state
2. Read `danny-trades-parag/parag-section2-scope-closure-2026-04-15.md` for the Q1/Q2/Q3 locks
3. Read Frank's parallel files for cross-check
4. The next uncompleted step is **Section 3 (importer / ingest)** — open questions listed at the bottom of `parag-memory-2026-04-15.md`
5. Continue from there following the pipeline stages, not a fresh brainstorm

If you are a different agent being added to this project for the first time:

1. Create `danny-trades-<yourname>/` alongside the existing agent folders
2. Seed it with `<yourname>-onboarding-YYYY-MM-DD.md` summarizing what you read from this README + the Frank and Parag memory files
3. Announce to Captain via the attention file or your inbox that you're onboarded and where your memory lives
4. Do not touch canonical data or locked decisions without explicit Captain signoff

---

## Agent project-memory directories

| Agent | Path | Role on DannyTrades |
|---|---|---|
| Frank | `danny-trades-frank/` | Architect — advisory pre-PR sanity check |
| Parag | `danny-trades-parag/` | Spec author, code reviewer (recused from PR gate on the spec he authored) |
| Anand | `danny-trades-anand/` | Implementation owner + primary PR-gate feasibility reviewer |

Other named owners on the project (NRavi V&V, Buck registry/truth-surface steward, Julie coordination) do not yet have a `danny-trades-*/` folder — one will be created the moment they accumulate project memory.

---

## Last updated

2026-04-15 by Anand (onboarding — Anand directory + agent-memory section added). Prior edit: 2026-04-15 by Parag (mid-brainstorm, Section 2 just locked, Section 3 pending).
