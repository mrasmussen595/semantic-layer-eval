"""Pull 10-K XBRL financial facts from SEC EDGAR and land them in raw.* (DuckDB).

Source: SEC's companyfacts API, one JSON per company containing every XBRL-tagged
value the company has ever filed:

    https://data.sec.gov/api/xbrl/companyfacts/CIK{10-digit-zero-padded}.json

We do NOT parse 10-K HTML documents. We read structured facts, keep only the
us-gaap concepts our metrics need, filter to annual (form 10-K, full-year periods),
and land a long-format raw.facts table. XBRL tag normalization (e.g. Revenues vs
RevenueFromContractWithCustomerExcludingAssessedTax) happens downstream in dbt
staging, so here we pull ALL candidate tags and let staging coalesce.

SEC constraints (verified against EDGAR API docs):
  - Descriptive User-Agent header is mandatory (403 otherwise). Set SEC_USER_AGENT.
  - Rate limit 10 req/s per IP. We make ~11 requests, but still throttle politely.

Raw companyfacts JSON for each company is also written to fixtures/ so the build and
CI are fully reproducible offline (EDGAR data is U.S. public domain).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import duckdb
import httpx
import yaml

from db import get_local_db_path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "companies.yml"
FIXTURES_DIR = ROOT / "fixtures" / "companyfacts"
DB_PATH = get_local_db_path()

TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"

# Curated us-gaap concepts our metrics need. Multiple candidates per economic concept;
# the dbt staging layer coalesces them into one canonical column per company-year.
WANTED_CONCEPTS = {
    # revenue (duration)
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
    # cost of revenue (duration)
    "CostOfRevenue",
    "CostOfGoodsAndServicesSold",
    # gross profit (duration)
    "GrossProfit",
    # operating income (duration)
    "OperatingIncomeLoss",
    # R&D (duration)
    "ResearchAndDevelopmentExpense",
    # operating cash flow (duration)
    "NetCashProvidedByUsedInOperatingActivities",
    "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    # capex (duration)
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "PaymentsToAcquireProductiveAssets",
    # net income (duration), context
    "NetIncomeLoss",
    # deferred revenue / contract liability (instant)
    "ContractWithCustomerLiability",
    "ContractWithCustomerLiabilityCurrent",
    "DeferredRevenueCurrent",
    # remaining performance obligation (instant), disclosed inconsistently
    "RevenueRemainingPerformanceObligation",
}

# A full fiscal year, in days. Used to keep only annual (not quarterly) duration facts.
MIN_YEAR_DAYS = 350
MAX_YEAR_DAYS = 380


def _client(user_agent: str) -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"},
        timeout=30.0,
    )


def _require_user_agent() -> str:
    ua = os.environ.get("SEC_USER_AGENT", "").strip()
    if not ua or "@" not in ua:
        raise SystemExit(
            "SEC_USER_AGENT must be set to a descriptive 'Name email@domain' string "
            "(SEC returns 403 without it). Set it in .env or the environment."
        )
    return ua


def load_companies() -> list[dict]:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)["companies"]


def resolve_ciks(client: httpx.Client, tickers: list[str]) -> dict[str, int]:
    """Map ticker -> CIK using SEC's official ticker file (avoids hardcoding stale CIKs)."""
    resp = client.get(TICKER_MAP_URL)
    resp.raise_for_status()
    by_ticker = {row["ticker"].upper(): int(row["cik_str"]) for row in resp.json().values()}
    out: dict[str, int] = {}
    for t in tickers:
        if t.upper() not in by_ticker:
            raise SystemExit(f"Ticker {t} not found in SEC ticker map")
        out[t] = by_ticker[t.upper()]
    return out


def fetch_companyfacts(client: httpx.Client, cik: int) -> dict:
    resp = client.get(COMPANYFACTS_URL.format(cik=cik))
    resp.raise_for_status()
    return resp.json()


def _days(start: str, end: str) -> int:
    from datetime import date

    s = date.fromisoformat(start)
    e = date.fromisoformat(end)
    return (e - s).days


def extract_annual_facts(ticker: str, cik: int, facts_json: dict) -> list[dict]:
    """Flatten companyfacts JSON into long-format annual (10-K) rows.

    Duration concepts (income statement, cash flow): keep full-year periods only.
    Instant concepts (balance sheet): keep the period-end snapshot.
    In both cases filter to form '10-K' and dedupe by (concept, end_date) keeping the
    most recently filed value (handles restatements / comparatives across filings).
    """
    usgaap = facts_json.get("facts", {}).get("us-gaap", {})
    # dedupe key -> chosen row
    chosen: dict[tuple[str, str], dict] = {}
    for concept, payload in usgaap.items():
        if concept not in WANTED_CONCEPTS:
            continue
        for unit, items in payload.get("units", {}).items():
            for it in items:
                if it.get("form") != "10-K":
                    continue
                end = it.get("end")
                start = it.get("start")
                if end is None:
                    continue
                if start is not None:  # duration -> require full year
                    if not (MIN_YEAR_DAYS <= _days(start, end) <= MAX_YEAR_DAYS):
                        continue
                key = (concept, end)
                prev = chosen.get(key)
                if prev is None or (it.get("filed", "") > prev["filed"]):
                    chosen[key] = {
                        "ticker": ticker,
                        "cik": cik,
                        "concept": concept,
                        "unit": unit,
                        "period_start": start,
                        "period_end": end,
                        "fiscal_year_tag": it.get("fy"),
                        "fiscal_period_tag": it.get("fp"),
                        "form": it.get("form"),
                        "filed": it.get("filed"),
                        "value": it.get("val"),
                    }
    return list(chosen.values())


def write_raw(rows: list[dict], companies: list[dict], ciks: dict[str, int]) -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))
    try:
        con.execute("CREATE SCHEMA IF NOT EXISTS raw")
        con.execute("DROP TABLE IF EXISTS raw.facts")
        con.execute(
            """
            CREATE TABLE raw.facts (
                ticker            VARCHAR,
                cik               BIGINT,
                concept           VARCHAR,
                unit              VARCHAR,
                period_start      DATE,
                period_end        DATE,
                fiscal_year_tag   INTEGER,
                fiscal_period_tag VARCHAR,
                form              VARCHAR,
                filed             DATE,
                value             DOUBLE
            )
            """
        )
        if rows:
            con.executemany(
                "INSERT INTO raw.facts VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                [
                    [
                        r["ticker"], r["cik"], r["concept"], r["unit"],
                        r["period_start"], r["period_end"], r["fiscal_year_tag"],
                        r["fiscal_period_tag"], r["form"], r["filed"], r["value"],
                    ]
                    for r in rows
                ],
            )
        con.execute("DROP TABLE IF EXISTS raw.companies")
        con.execute(
            "CREATE TABLE raw.companies (ticker VARCHAR, cik BIGINT, name VARCHAR, "
            "fiscal_year_end VARCHAR)"
        )
        con.executemany(
            "INSERT INTO raw.companies VALUES (?,?,?,?)",
            [[c["ticker"], ciks[c["ticker"]], c["name"], c["fiscal_year_end"]] for c in companies],
        )
        # Export a tiny, deterministic snapshot of raw.* so CI / offline rebuilds never
        # hit EDGAR live. load_fixture.py replays these back into raw.*.
        FIXTURES_DIR.parent.mkdir(parents=True, exist_ok=True)
        facts_pq = (FIXTURES_DIR.parent / "raw_facts.parquet").as_posix()
        cos_pq = (FIXTURES_DIR.parent / "raw_companies.parquet").as_posix()
        con.execute(f"COPY raw.facts TO '{facts_pq}' (FORMAT parquet)")
        con.execute(f"COPY raw.companies TO '{cos_pq}' (FORMAT parquet)")
    finally:
        con.close()


def main() -> None:
    ua = _require_user_agent()
    companies = load_companies()
    tickers = [c["ticker"] for c in companies]
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    all_rows: list[dict] = []
    with _client(ua) as client:
        ciks = resolve_ciks(client, tickers)
        for ticker in tickers:
            cik = ciks[ticker]
            facts = fetch_companyfacts(client, cik)
            # Persist raw JSON for offline reproducibility / CI fixtures.
            (FIXTURES_DIR / f"{ticker}.json").write_text(json.dumps(facts))
            rows = extract_annual_facts(ticker, cik, facts)
            all_rows.extend(rows)
            print(f"  {ticker:5} CIK {cik:>10}  ->  {len(rows):4} annual facts")
            time.sleep(0.2)  # polite throttle, well under SEC's 10 req/s

    write_raw(all_rows, companies, ciks)
    print(f"\nLanded {len(all_rows)} rows into raw.facts at {DB_PATH}")


if __name__ == "__main__":
    main()
