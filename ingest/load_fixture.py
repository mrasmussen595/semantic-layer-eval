"""Rebuild raw.* in DuckDB from the committed parquet snapshot — no network.

The live pipeline is ingest/fetch_edgar.py (hits SEC EDGAR). This module replays the
frozen snapshot it exported, so CI and offline runs are fully deterministic. EDGAR data
is U.S. public domain, so committing the snapshot is fine.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from db import get_local_db_path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"
DB_PATH = get_local_db_path()


def main() -> None:
    facts_pq = (FIXTURES / "raw_facts.parquet").as_posix()
    cos_pq = (FIXTURES / "raw_companies.parquet").as_posix()
    for p in (facts_pq, cos_pq):
        if not Path(p).exists():
            raise SystemExit(f"Missing fixture {p}. Run `python -m ingest.fetch_edgar` first.")

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))
    try:
        con.execute("CREATE SCHEMA IF NOT EXISTS raw")
        con.execute(
            f"CREATE OR REPLACE TABLE raw.facts AS SELECT * FROM read_parquet('{facts_pq}')"
        )
        con.execute(
            f"CREATE OR REPLACE TABLE raw.companies AS SELECT * FROM read_parquet('{cos_pq}')"
        )
        n = con.execute("SELECT count(*) FROM raw.facts").fetchone()[0]
        print(f"Loaded {n} rows into raw.facts from fixture snapshot")
    finally:
        con.close()


if __name__ == "__main__":
    main()
