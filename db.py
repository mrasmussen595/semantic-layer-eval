"""DuckDB routing shared by ingestion, the compiler, ground truth, and eval.

Local DuckDB by default. If MOTHERDUCK_TOKEN is set, readers connect to an existing
MotherDuck database instead. Provisioning and dbt builds for MotherDuck are not automated.
"""

from __future__ import annotations

import os
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / "warehouse" / "edgar.duckdb"
MART_TABLE = "main_marts.fct_company_year"


def get_local_db_path() -> Path:
    return Path(os.environ.get("EDGAR_DB", str(DEFAULT_DB)))


def get_connection(read_only: bool = True) -> duckdb.DuckDBPyConnection:
    token = os.environ.get("MOTHERDUCK_TOKEN", "").strip()
    if token:
        db = os.environ.get("MOTHERDUCK_DATABASE", "edgar")
        return duckdb.connect(f"md:{db}", config={"motherduck_token": token})
    return duckdb.connect(str(get_local_db_path()), read_only=read_only)
