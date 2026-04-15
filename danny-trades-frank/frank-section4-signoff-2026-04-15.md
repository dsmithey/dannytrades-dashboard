<!-- FRANK WORKING MEMORY - NOT CANONICAL. Source of truth for MOS state is PG/API once the proper DannyTrades PG location exists. -->

# DannyTrades Section 4 Signoff

Date: 2026-04-15
Agent: Frank / MOS Architect
Project: DannyTrades Dashboard productization

## Section 4 Decisions

1. In-place dashboard rewrite: yes.
2. Declarative-first dashboard-loader integration with focused custom `mos-data-loaded` handler: yes.
3. CSS custom properties plus semantic `data-color-key` attributes: yes.
4. `.env` reserved quote names in `/home/david/SMITHEY_MOS/.env`: modify. Put the reserved names in `.env.example` and runtime config docs in A; do not edit live `.env` unless the implementation actually reads them or Captain explicitly asks.
5. Footer freshness strip with absolute and relative import time: yes.
6. Product registry item 61 update: yes to option (c), flag flip only. Defer metadata JSONB to a separate follow-up directive.
7. Testing matrix: yes, with additions for P-001 guardrail, empty-state dashboard, retired run fallback, and query filters beyond run_id/symbol.
8. Cutover with empty-state shell and no old/new parallel source of truth: yes, with deployment gate that first completed import exists before arrays are removed in production.
9. File inventory: modify. Use canonical Alembic path `control_plane_v2/db/alembic/versions/...`, avoid editing live `.env`, and keep optional memory index updates out of the A PR unless a memory directive is active.

## Architecture Lock

A remains the PG/API/JSON dashboard migration. It should not grow into quote-provider integration, full scraper rehost, or product_registry metadata schema work.
