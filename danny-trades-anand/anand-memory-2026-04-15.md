<!-- ANAND WORKING MEMORY - NOT CANONICAL. Source of truth for MOS state is BOSS API / PostgreSQL at http://localhost:7777. -->

# Anand Project Memory — DannyTrades PG/API/JSON Migration

**Agent:** Anand (Primary Execution / Lead Developer, canonical_agent_uid `b182aef8-64e3-4b32-8daa-4bc103e761f5`)
**Thread:** T89
**Session:** 2026-04-15 (headless, Claude Code CLI, HEADLESS attestation, boot ONLINE_VERIFIED)
**Role on this project:** Implementation owner + primary PR-gate feasibility reviewer for the spec
**Pipeline stage on arrival:** `S` (Spec Doc) — post-brainstorm, pre-peer-review
**Parallel agents:**
- Frank — `/home/david/DannyTrades/danny-trades-frank/` (Architect, advisory pre-PR)
- Parag — `/home/david/DannyTrades/danny-trades-parag/` (Spec author; recused from PR gate per Fix 1)
- NRavi — secondary PR reviewer after Plan stage (V&V angle)
- Buck — product registry + dashboard truth-surface steward
- Julie — coordination / memory / directive drafting

---

## Why this folder exists

Per Captain's directive 2026-04-15 and Frank's dispatch message `52e73e51-15b9-4ba3-890e-5691ca045de3`: per-agent DannyTrades project memory lives in `danny-trades-<agent>/` subfolders inside the operational repo, mirrored from Frank and Parag's pattern. This is **temporary scaffolding** until the PG-backed per-agent project memory table exists, at which point the contents get imported and frozen. It is not canonical MOS governance state; BOSS API / PostgreSQL remains the source of truth.

---

## What I read on onboarding

1. `/home/david/DannyTrades/README.md` — operational context, agent onboarding rules, folder layout, scope lock for A, pipeline-stage discipline, P-001 compliance note, how-to-pick-up-where-we-left-off.
2. `/home/david/SMITHEY_MOS/docs/superpowers/specs/2026-04-15-dannytrades-pg-api-json-migration-design.md` — full 1147-line spec v1.0.0, all sections end-to-end.
3. Parag's `parag-memory-2026-04-15.md` (head) — brainstorm provenance and Section 2 shape lock.
4. Frank's `frank-memory-2026-04-15.md` (head) — architect framing and Option A rationale.
5. Frank's inbox message `52e73e51-15b9-4ba3-890e-5691ca045de3` — the instruction to onboard + BAKE-ASSESS hold posture + current spec status.

Carry-forward from Frank's message, not yet applied in the spec:

- **Fix 1 (APPLIED by Parag):** PR gate no longer has Parag self-reviewing. Anand is primary feasibility reviewer; NRavi secondary after Plan.
- **Fix 2 (PENDING):** Importer exit-code semantics. Exit 1 must be pre-PG validation / source-path only. File-level parse failure after a run row or failure-audit row exists must exit 3.
- **Fix 3 (PENDING):** `product_registry` item 61 flag flip must be decoupled from the table-creation Alembic migration. Tables land in Alembic; item 61 flag flip moves to a separate post-import/deployment step gated on (a) a successful `complete` run exists, (b) dashboard cutover verified, (c) Buck signoff.
- **Fix 4 (PENDING):** Clarify that `run.current.imported_at` in the API envelope is an alias for `dannytrades_runs.completed_at`.

---

## My assigned gate role

Per the spec's §Agent Roles & Pipeline Gates (Fix 1 applied):

> **PR gate — primary reviewer: Anand (implementation-feasibility angle).** Will the spec as written actually build cleanly against the real codebase, alembic conventions, and BOSS API patterns?

And §Agent Roles table:

> **Anand** — Implementation: importer, API, schema, dashboard wiring.

I own the primary implementation path once the Plan stage clears. No parallel parser writers until the data contract stabilizes.

---

## Spec posture assessment (pre-PR, informal — not the PR gate output yet)

I am holding the formal feasibility review until Parag applies Fixes 2-4 and the spec reaches PR stage cleanly. Posting partial verdicts against a mid-edit spec creates churn. Locked-in first impressions from my read-through:

**Builds cleanly — high confidence**
- 4-table schema, `public` schema, UUID PKs, indexes all map to standard Alembic conventions already used in `control_plane_v2/db/alembic/versions/`.
- FastAPI router pattern under `control_plane_v2/mosboss/api/` + thin wrapper over a `control_plane_v2/services/dannytrades_api_service.py` builder matches existing BOSS API patterns (e.g. `captain_dashboard.py`).
- CLI importer entrypoint under `control_plane_v2/scripts/import_dannytrades.py` fits the existing `scripts/` pattern.
- `dashboard-loader.js` declarative binding pattern already exists and is already used by `mos-product-inventory-v5.html` — the cutover is a true drop-in, not a new framework.
- `market_quote_snapshots`, enrichment table, RAG, and hypervisor registration all explicitly deferred — A stays a modular monolith, consistent with BOSS API's existing shape.

**Feasibility concerns to raise at PR gate**
1. **Exit-code table is internally inconsistent with §Error handling split** (→ Fix 2 from Frank). The Exit Codes table conflates pre-PG argv/source-path failures with post-PG file-level parse failures under exit 1, but §Error handling split already says file-level parse failure → failure-audit row + exit 3. The table must agree with the split. I will flag this as a blocking edit.
2. **Migration bundles schema + item-61 flag flip** (→ Fix 3 from Frank). Alembic doubles as both schema authority and product-registry mutation. Decoupling is correct: (a) tables land via alembic; (b) item 61 flags and `primary_port=7777` flip in a separate post-deploy step after Buck signs off and the deployment gate's first `complete` run is proven. Otherwise a failed rollout leaves the flags on with nothing behind them. I will also flag this as blocking.
3. **Envelope field naming is slightly ambiguous** (→ Fix 4 from Frank). `run.current.imported_at` is not explicitly aliased in the spec's data-model or API-contract sections. It needs one line: *"`imported_at` is an API-envelope alias for `dannytrades_runs.completed_at`; no new column."* Non-blocking wording fix.
4. **Signal Score computed in Python at query time** — fine for ~52 rows, but spec should state the bound (*"Python compute is acceptable up to N=10,000 observations; revisit as materialized view past that"*). Non-blocking wording fix.
5. **Content-hash manifest includes `data/raw/*.txt`** — idempotency check treats raw post text as part of the signal surface. If Captain re-dumps a raw .txt file during debug without touching the structured markdown, the hash changes and a re-import is triggered even though no structured data moved. Non-blocking — flag for discussion, not necessarily a fix.
6. **Retired-run fallback + "previous" pointer math** — the `run.previous` field in the API envelope is documented as the second-latest `complete` non-test run. If the latest is retired via `retire_dannytrades_run.py`, the second-latest becomes current and the logic for `previous` must re-resolve. Spec implies this via the filter `status='complete' AND source_label NOT LIKE 'test-%'` but never names the tie-break explicitly. Non-blocking wording fix.
7. **Parser version vs spec version** — spec is v1.0.0 and `parser_version='1.0.0'` at initial import. The two versions drift independently (parser patches won't always bump product version). Spec says this, but the Alembic default column value couples them at write time. Needs a `server_default='1.0.0'` not hardcoded — keep implementation free to bump. Non-blocking.

**Nothing I'm blocking on (contrarian check)**
- Modular monolith inside BOSS API is the right call. Pulling the importer into a service now would burn B stage prematurely. I endorse the "split workers first, never split the API" rule.
- Empty-state shell as part of the dashboard rewrite is the honest answer for the degraded case. Agree.
- `--force-review` intentionally omitted so a >50% needs-review run cannot become `complete`. Correct call; prevents a silent quality cliff.

---

## BAKE-ASSESS hold posture (what I am NOT doing)

Per Frank's message + Captain's acknowledged holding decision:

- Do **not** execute the close path for `DIR-T89-S37-PHASE1-BAKE-ASSESS-001`.
- Do **not** POST the Anand dispatch or submit/replace a TCR for it.
- Do **not** call `/api/directives/{id}/complete`.
- Do **not** restart Ollama, touch RAG / R-21 / knowledge_query — NO-LLM banner still active.
- `mos_ollama` stays Exited. `mos_rag_gateway_service` stays container-healthy / app-degraded.

I acknowledge S-37 passive bake is being accepted as **BASELINE_SOAK_COMPLETE / ACCEPT_WITH_LIMITATION**, not full S-37 behavioral validation. Limitation and carry-forward (controlled active validation gate before Phase 2) will be preserved whenever Captain finally authorizes the close.

Current bake math: start `2026-04-14T04:16:45Z`, 48h target `2026-04-16T04:16Z`. As of boot at `2026-04-15T15:08Z` ~35h elapsed, ~13h remaining. Captain holds the call on whether to close early on baseline-soak-complete basis or wait for the natural 48h window.

---

## Environment + dirty-tree note

- Working tree has pre-existing unrelated dirty files from Captain's in-flight work on other threads (captain-dashboard diagrams, DECISION-LOG-Test-Competition, MultiAgent/issues/2-agent-mind-meld-folder/3-part-harmony, `.claude/scheduled_tasks.lock`). **Not mine. Do not touch.** Per prior Anand session lesson: `git stash push -u -m "dvi-certify-temp-<dir>" -- <paths>` + `git stash pop` around any DVI certify call.
- Boot attestation minted from `.env`-sourced `MOS_HEADLESS_ATTESTATION_SECRET`; `PYTHONPATH=/home/david/SMITHEY_MOS` is required to run `control_plane_v2/scripts/mint_headless_attestation.py` as a script. Captured as a prior-session lesson but re-surfaced this session.
- Directive drift check: 20 `db_only` directives / 0 unregistered folders. Expected post-DIR-T57 (PG is canonical for directive state); not real drift. Noted as PASS-with-note.

---

## Next step when Captain un-pauses me

1. Wait for Parag to land spec Fixes 2, 3, 4 (or receive explicit instruction to apply them myself).
2. Run the formal PR-gate feasibility review against spec v1.0.1+ with Fixes 2-4 applied.
3. Surface the non-blocking wording items (#3-#7 above) as cleanup suggestions, not blockers.
4. If PR clears, wait for the Plan stage (via `superpowers:writing-plans`). I do not pre-plan.
5. Implementation starts only after Plan + Plan sanity check (Frank/Parag lightweight) + Captain acceptance of the Plan.

---

## Open questions I'm holding for Captain

None blocking. The spec is substantially complete and my feasibility concerns are captured above. When Parag's Fixes 2-4 land, I'll deliver the PR-gate verdict.

---

## Changelog

| Date | Author | Change |
|---|---|---|
| 2026-04-15 | anand | Initial onboarding memory after reading README + spec v1.0.0 + Frank/Parag memory heads. |
