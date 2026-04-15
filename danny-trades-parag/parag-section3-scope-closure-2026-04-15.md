# Parag — Section 3 Scope Closure Lock (Importer / Ingest)

**Date:** 2026-04-15
**Agent:** Parag
**Thread:** T89
**Pipeline stage:** Brainstorm (`B`)
**Status:** LOCKED by Captain

This file records the Section 3 decisions for the DannyTrades PG/API/JSON migration brainstorm — the importer contract, idempotency, parser controls, error handling, transaction boundary, and import success threshold. Pairs with `parag-section2-scope-closure-2026-04-15.md`.

---

## 1. CLI importer contract — LOCKED with `--source-kind` addition

```bash
python scripts/import_dannytrades.py \
    --from /home/david/DannyTrades \
    --label weekly-2026-04-15 \
    [--dry-run] \
    [--force] \
    [--imported-by parag] \
    [--source-kind markdown]
```

| Flag | Required | Purpose |
|---|---|---|
| `--from` | yes | Absolute path to the DannyTrades repo root |
| `--label` | yes | Run label matching regex `^(weekly|backfill|test)-.*$|^[\w-]+$` |
| `--dry-run` | no | Parse + validate + threshold-check, no PG writes |
| `--force` | no | Override idempotency no-op, creates new run with `forced=true` |
| `--imported-by` | no | Agent/user name, defaults to `$USER` |
| `--source-kind` | no | Default `markdown`. Future values: `pg`, `raw-scraper`. Prevents contract rename when B lands. |

**Exit codes:** 0 ok | 1 validation fail | 2 idempotency no-op | 3 PG/parse fail | 4 invalid CLI args

**stdout:** one JSON log record per run with `run_id`, `status`, `observation_count`, `needs_review_count`, `content_hash`, `duration_ms`.

---

## 2. Content-hash idempotency — LOCKED with manifest

**Hash target:** concatenate sorted-by-name content of every source file under `<source>/data/structured/*.md` + `<source>/data/raw/*.txt`, SHA-256 the result.

**`dannytrades_runs` hash audit columns:**

| Column | Type | Purpose |
|---|---|---|
| `source_content_hash` | `VARCHAR(64) NOT NULL` | SHA-256 of sorted source content |
| `source_manifest` | `JSONB NOT NULL` | Array: `[{path, bytes, sha256}, ...]` — explainable idempotency |
| `source_file_count` | `INT NOT NULL` | Number of files contributing to the hash |
| `source_total_bytes` | `BIGINT NOT NULL` | Sum of source file bytes |
| `source_kind` | `VARCHAR(20) NOT NULL DEFAULT 'markdown'` | Matches `--source-kind` |
| `status` | `VARCHAR(10) NOT NULL CHECK IN ('pending','complete','failed','retired')` | Run lifecycle |
| `forced` | `BOOLEAN NOT NULL DEFAULT FALSE` | True when `--force` overrode idempotency |
| `started_at` | `TIMESTAMPTZ NOT NULL DEFAULT NOW()` | |
| `completed_at` | `TIMESTAMPTZ NULL` | Set on commit |
| `failed_at` | `TIMESTAMPTZ NULL` | Set on failure |
| `error_message` | `TEXT NULL` | Populated on FAILED |
| `parser_version` | `VARCHAR(20) NOT NULL` | Parser code version stamp |

**Index:** `CREATE INDEX ix_dtr_hash_status ON dannytrades_runs (source_content_hash, status);`

**Four outcome matrix:**

| Scenario | Behavior | Run row? | Exit |
|---|---|---|---|
| Hash matches existing `complete` run | No-op, log "duplicate" | No | 2 |
| Hash matches existing `failed` run | Retry allowed, new row inserted | Yes | 0 / 3 |
| New hash | Proceed | Yes | 0 / 3 |
| Hash match + `--force` | New row with `forced=true` | Yes | 0 / 3 |

---

## 3. Parser brittleness controls — LOCKED with source trace fields

**Design rules:**

1. One parser module per source file type — `parse_ticker_history.py`, `parse_watchlist.py`, `parse_batch_structured.py`
2. Column lookup by **header name, not position** — `row['Symbol']` not `row[0]`
3. Unknown columns preserved in `raw_extras JSONB` on each observation
4. Unparseable rows → `needs_review=TRUE`, `extraction_confidence='low'`, `parse_notes=<reason>`, **never silent drop**
5. `parser_version` stamp on every run row (semver string, e.g. `1.0.0`)

**`dannytrades_ticker_observations` trace columns (added for Section 3):**

| Column | Type | Purpose |
|---|---|---|
| `raw_extras` | `JSONB NULL` | Unknown markdown columns land here |
| `source_file` | `TEXT NULL` | Which file produced the row, e.g. `data/structured/TICKER_HISTORY.md` |
| `source_row_number` | `INT NULL` | Line index inside that file |

Together: a parser warning becomes `needs_review=TRUE for NVDA at data/structured/TICKER_HISTORY.md:42, reason: Whale Accum column missing`.

---

## 4. First-run F6 backfill — LOCKED at option (a)

**Accept NULL trend on first run.** F6 lights up from run #2 onward.

- No `--backfill-from-git` flag in A
- No synthesized "previous" from git history
- Dashboard renders `whale_accumulation_trend IS NULL` as neutral grey (semantic color_key: `neutral`)
- Honest about what the system knows

**Rationale (Captain):** "That introduces false confidence and parser variance."

---

## 5. Run label convention — LOCKED with regex + filter

**Regex:** `^(weekly|backfill|test)-.*$|^[\w-]+$`
**Warning path:** free-form labels accepted with a log warning, not rejected
**Default filter:** `test-*` labels excluded from dashboard queries
  - API query: `WHERE source_label NOT LIKE 'test-%'`
  - Override: `?include_test=true` (debug/admin use; **not exposed in A UI**)

---

## 6. Error handling split — LOCKED

| Failure mode | Behavior | Run status |
|---|---|---|
| CLI args invalid | Fail fast, no PG | N/A (exit 4) |
| Source path missing/unreadable | Fail fast, no PG | N/A (exit 1) |
| File-level parse failure (entire file unreadable) | Insert run row, `status='failed'`, no observations | FAILED (exit 3) |
| Row-level parse failure | Insert observation with `needs_review=TRUE`, continue | COMPLETE (if threshold passes) |
| PG connection dies mid-import | Transaction auto-rollback | Retry next run |
| Unique constraint violation | Fail loud, rollback, bug report | FAILED (exit 3) |

---

## 7. Transaction boundary — LOCKED (atomic per run)

```python
with conn.transaction():
    # 1. Idempotency check (content hash vs existing complete runs)
    # 2. Insert dannytrades_runs with status='pending'
    # 3. Parse source files, build observation dicts
    # 4. Batch INSERT all observations (executemany)
    # 5. Compute needs_review_count, observation_count
    # 6. Minimum viable threshold check (§8)
    # 7. UPDATE run: status='complete', completed_at=NOW(), observation_count, needs_review_count
    # 8. COMMIT
# Any exception → automatic ROLLBACK
# Failure audit happens in a SEPARATE short tx:
#   INSERT dannytrades_runs (status='failed', error_message=<msg>, failed_at=NOW(), source_content_hash=<hash>)
```

**Dashboard API latest-run filter is always:** `WHERE status = 'complete' AND source_label NOT LIKE 'test-%'`

**Never reads:** pending, failed, retired.

---

## 8. Minimum viable import success threshold — LOCKED (new in Section 3)

Hard check inside the transaction, immediately before `COMMIT`:

```python
if observation_count == 0:
    raise MinimumThresholdViolation("zero observations parsed")

if observation_count > 0 and (needs_review_count / observation_count) > 0.50:
    ratio_pct = (needs_review_count / observation_count) * 100
    raise MinimumThresholdViolation(
        f"{needs_review_count}/{observation_count} = {ratio_pct:.0f}% needs-review "
        f"(threshold 50%)"
    )
```

**Consequences when violated:**
- Main transaction rolls back — zero observations written
- Failure-audit tx inserts `status='failed'` run row with `error_message` naming the threshold
- Exit code 3
- Dashboard unchanged (still reads previous `complete` run)

**`--force-review` deliberately NOT in A.** A run with >50% needs-review cannot become `complete` — Captain must fix the parser or the source data and re-import. Deferred-item candidate for a later directive.

---

## 9. Retire-not-delete — LOCKED

Undoing a successful import:

```bash
python scripts/retire_dannytrades_run.py --run-id <uuid> --reason "<text>"
```

- Sets `status='retired'`, `retired_at=NOW()`, `retired_reason=<text>` on the run row
- Never DELETEs observations — they stay for audit, just become invisible to the dashboard
- `'retired'` added to the status check constraint
- Previous `complete` run becomes current

**Two additional `dannytrades_runs` columns:**

| Column | Type | Purpose |
|---|---|---|
| `retired_at` | `TIMESTAMPTZ NULL` | Set when retired |
| `retired_reason` | `TEXT NULL` | Required when retiring |

---

## Combined Section 3 lock

| # | Item | Decision |
|---|---|---|
| 1 | CLI shape | locked + `--source-kind markdown` |
| 2 | Content-hash idempotency | locked + manifest/file-count/bytes columns |
| 3 | Parser brittleness | locked + `source_file` + `source_row_number` |
| 4 | First-run F6 backfill | locked at option (a), no git backfill |
| 5 | Run label regex | locked, `test-*` filtered, `?include_test=true` debug flag exists but not in A UI |
| 6 | Error handling split | locked |
| 7 | Atomic transaction | locked, failure-audit in separate tx |
| 8 | Minimum viable threshold | locked, `--force-review` deferred from A |
| 9 | Retire-not-delete | locked |

Next pipeline step: Section 4 — dashboard rewrite + product_registry update + dashboard-loader.js integration. After Section 4 locks, spec doc writes to `docs/superpowers/specs/2026-04-15-dannytrades-pg-api-json-migration-design.md`, then self-review, then user review, then PR stage, then writing-plans skill.
