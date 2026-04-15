# Parag — Section 2 Scope Closure Lock

**Date:** 2026-04-15
**Agent:** Parag
**Thread:** T89
**Pipeline stage:** Brainstorm (`B`)
**Status:** LOCKED by Captain

This file records the three scope-closure decisions Captain made at the end of Section 2 of the DannyTrades PG/API/JSON migration brainstorm. These decisions shape the spec doc and the implementation plan. They are not subject to drift.

---

## Q1 — Signal Score: **in-A, computed at API time**

**Decision:** Include Signal Score in A, but compute it at API query time. **No DB column.** The formula lives in the API layer (Python), adjustable in code. Frontend displays it and sorts by it but does not own the formula.

**Captain's phrasing:**
> "The API computes signal_score from observation fields and returns it in the payload. Frontend displays it and sorts by it, but does not own the formula. This gives us useful triage without creating schema churn every time Captain wants to tune scoring."

**Baseline formula** (from Captain's top-vision section, subject to tuning):

```
+3 monthly_red / triple_red
+2 weekly_red / double_red
+1 daily_red
+2 golden_cross present
+1 whale_accumulation_pct >= some_threshold
+2 whale_accumulation_trend = 'increasing'
+1 recent mention (observation_as_of within N days)
-2 invalidation_level triggered OR price below key level
```

**Rationale for in-A:**
- Useful triage unlocked without schema churn
- Formula is a single Python function, trivial to tune
- Sorting the ticker table by Signal Score gives the dashboard its "what should I look at first?" answer in under 10 seconds — Captain's stated UX goal

**Rationale for computed-at-API-time (not a stored column):**
- No schema migration every time formula changes
- No risk of stale scores when the formula updates but old rows don't recompute
- Single source of truth lives in code, not in 52 rows × N runs of stored integers

---

## Q2 — Import Runs tab: **out-A as a full tab. Footer-only in A.**

**Decision:** A ships with a **data freshness footer/strip only** at the bottom of the main dashboard page. The full Import Runs tab is deferred to a later directive.

**Captain's phrasing:**
> "A should include the data freshness footer/strip only: Latest import, source path, posts processed, tickers extracted, warnings/needs-review count, content hash status. Full Import Runs tab is deferred. The API can already return the data envelope, so later work is mostly rendering, not architecture."

**Footer content (A scope):**

- Latest import timestamp (from `run.current.imported_at`)
- Source path (from `run.current.source_label` + `source_path` if exposed)
- Posts processed (from `run.current.observation_count` or a dedicated field)
- Tickers extracted (from `run.current.observation_count`)
- Warnings / needs-review count (from `run.current.needs_review_count`)
- Content hash status (clean / duplicate-candidate / new — from the idempotency check)

**Deferred to later directive:**
- Full Import Runs tab view
- Run history list with clickable rows
- Per-run drilldown page
- Parser warning detail view
- Manual run invalidation / delete / replay

**Rationale for footer-only:**
- API envelope already carries the data — no backend work blocked
- Single DOM strip, no tab-routing code, no per-run view rendering
- Gives Captain operational confidence without turning A into a multi-view app
- When/if Captain wants the full tab later, it's pure rendering work on top of existing API

---

## Q3 — Change Since Last Run: **modify. F6 only (whale accumulation trend color).**

**Decision:** A includes only the whale accumulation trend color as the "change since last run" signal. This is F6, already locked as the smart win. All other diff highlighting is deferred.

**Captain's phrasing:**
> "A should include only the whale accumulation trend color, because F6 is already the smart win and it uses the current + previous observation model. Defer these from A: new tickers, removed tickers, new golden crosses, new daily/weekly/monthly reds, full diff highlighting. Those are good features, but they turn A into a broader comparison UI. Keep A focused."

**In-A (F6 only):**

- Whale accumulation trend color per ticker:
  - `green` = increasing (`whale_accumulation_trend = 'increasing'`)
  - `yellow` = unchanged (`whale_accumulation_trend = 'same'`)
  - `red` = decreasing (`whale_accumulation_trend = 'decreasing'`)
- Delta value displayed alongside: *"89.09% (was 87.40%, +1.69)"*

**Deferred from A:**

- "New ticker" highlighting (ticker appeared in current run, not in previous)
- "Removed ticker" highlighting (ticker present in previous run, absent in current)
- "New golden cross" badge (golden_cross string changed from NULL to non-NULL)
- "New daily/weekly/monthly red" badges (red boolean flipped false → true)
- Full diff view / comparison page
- Side-by-side run comparison
- Multi-run regression charts

**Rationale for F6-only:**
- F6 is already locked and proves the current + previous schema is doing useful work
- Adding 5 more diff types turns the dashboard into a comparison UI, different product
- The data is already captured (every run has a previous); later directive can add rendering
- Keep A focused on "can the dashboard breathe data from PG?" — that's the migration proof

---

## Combined scope lock

| Item | Decision | Source |
|---|---|---|
| Q1 Signal Score | **in-A, computed at API time, no DB column** | Captain 2026-04-15 |
| Q2 Import Runs full tab | **out-A, footer-only in A** | Captain 2026-04-15 |
| Q3 Change Since Last Run | **F6 whale trend color only; all other diffs deferred** | Captain 2026-04-15 |

**Downstream impact:**

- Section 3 (importer/ingest) proceeds with these locks in place
- Section 4 (dashboard rewrite) renders footer (not tab), F6 color (not full diff), Signal Score sort column (computed at API)
- Spec doc's "Scope" section uses Captain's verbatim Section 1 scope-exclusion language:
  > "This directive migrates DannyTrades dashboard data into MOS-owned PG/API/JSON authority. It does not rehost the Patreon scraping pipeline. It does not introduce realtime market-data provider integration. It prepares schema and UI slots for richer extraction in a later B-stage directive."

---

## Cross-reference

- **Full session memory:** `parag-memory-2026-04-15.md` in the same folder
- **Frank's parallel scope-closure:** `/home/david/DannyTrades/danny-trades-frank/frank-section2-scope-closure-2026-04-15.md`
- **README for joining agents:** `README.md` in the same folder
