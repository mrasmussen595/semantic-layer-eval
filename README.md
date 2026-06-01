# Governing the AI Analyst

> Operationalizing the thesis: **LLM analytics agents are dangerous because they invent
> or inconsistently compute metrics. The fix is a semantic layer the agent is forced
> through, plus an eval harness that catches wrong numbers before they reach a user.**

This repository is a single, end-to-end vertical slice that proves that thesis on
**real data**: audited financial figures from the SEC EDGAR filings (10-K) of 10 public
SaaS companies.

- A **governed semantic layer** (YAML) — every metric has exactly one definition.
- A **custom MCP server** that exposes *only* governed metrics. The agent cannot run
  arbitrary SQL.
- A **Claude agent** that answers analytics questions through that server and **refuses**
  ambiguous or out-of-scope questions instead of guessing.
- A **DeepEval harness** that proves correctness against independently-computed ground
  truth (anchored to the actual filings) and proves the agent refuses when it should —
  including a planted failure to show the harness catching a wrong number.

## Why financial filings

The thesis needs metrics whose definitions are *genuinely contested in the wild*. SaaS
financials are exactly that:

- **`gross_margin`** — GAAP vs. non-GAAP (does cost of revenue include stock-based comp?).
- **`rule_of_40`** — everyone agrees it is "growth % + profitability %", but the second
  term is genuinely disputed (FCF margin? operating margin? EBITDA margin?).
- **"revenue"** — total vs. subscription vs. product+service.

An ungoverned LLM picks one definition silently and inconsistently across companies and
quarters. The governed layer pins exactly one — and the eval proves it.

Ground truth is **audited and externally verifiable** against the filings, so the eval
cannot be waved away as "made-up data graded against a made-up answer."

## Architecture

```
SEC EDGAR (10-K XBRL facts)  →  ingest (Python)  →  raw.*        (DuckDB)
                                                      │  dbt: staging → marts
                                                      ▼
                                                   marts.fct_company_year
                                                      │
                            semantic_layer/metrics.yml  (single source of truth)
                                                      │
                              MCP server  (list / get / query / resolve — no raw SQL)
                                                      │
                                   Claude agent  (governed; refuses ambiguity)
                                                      │
                              DeepEval harness  vs.  independent ground-truth SQL
```

<!-- TODO(Phase 7): architecture diagram, demo recording/notebook, eval report, badges -->

## Companies covered

Salesforce (CRM), Snowflake (SNOW), Datadog (DDOG), CrowdStrike (CRWD),
ServiceNow (NOW), Workday (WDAY), HubSpot (HUBS), Atlassian (TEAM),
MongoDB (MDB), Cloudflare (NET). Deliberately mixed fiscal calendars.

## Quickstart

```bash
cp .env.example .env      # set SEC_USER_AGENT (required); ANTHROPIC_API_KEY for the agent
./init.sh                 # install uv, sync deps, ingest EDGAR, build dbt, run the demo
```

<!-- TODO(Phase 7): expand with demo walk-through and sample eval report -->

## Data source & license

Data is from SEC EDGAR, which is U.S. public-domain. A frozen raw snapshot is committed
under `fixtures/` so the build and CI are fully reproducible and offline. Code is MIT
(see `LICENSE`).

## Status

See `progress.txt` for the human-readable status and `progress.json` for the structured
phase tracker.
