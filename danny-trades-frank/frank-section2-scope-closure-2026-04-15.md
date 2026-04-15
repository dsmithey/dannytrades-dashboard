<!-- FRANK WORKING MEMORY - NOT CANONICAL. Source of truth for MOS state is PG/API once the proper DannyTrades PG location exists. -->

# DannyTrades Section 2 Scope Closure

Date: 2026-04-15
Agent: Frank / MOS Architect
Project: DannyTrades Dashboard productization

## Section 2 Decisions

Q1 Signal Score:

In A, computed at API query time. No database column. Formula lives in one backend function and is returned in the ticker observation payload as `signal_score`. Frontend may display and sort by it, but does not compute it.

Q2 Import Runs tab:

Out of A as a full tab. A includes footer/data freshness strip only, sourced from the run envelope. Full Import Runs tab is deferred to a later directive because it is rendering complexity, not required for the PG/API/JSON migration.

Q3 Change Since Last Run highlighting:

Modify: A renders only the whale accumulation trend color from current + previous observations. Other diffs such as new tickers, removed tickers, new golden crosses, and new red statuses are deferred.

## Scope Rule

A should ship the durable data contract and the highest-signal UI improvements, without becoming the full cockpit. The Product North Star remains captured for multi-stage evolution, but A remains the PG/API/JSON dashboard migration.
