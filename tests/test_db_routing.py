"""Database routing must send every local pipeline stage to the same DuckDB file."""

from __future__ import annotations

import importlib
import os

import db
from ingest import fetch_edgar, load_fixture


def test_edgar_db_override_routes_ingest_and_queries(monkeypatch, tmp_path):
    override = tmp_path / "override.duckdb"
    old_edgar_db = os.environ.get("EDGAR_DB")
    try:
        monkeypatch.setenv("EDGAR_DB", str(override))
        monkeypatch.delenv("MOTHERDUCK_TOKEN", raising=False)
        importlib.reload(db)
        importlib.reload(fetch_edgar)
        importlib.reload(load_fixture)

        assert fetch_edgar.DB_PATH == override
        assert load_fixture.DB_PATH == override
        con = db.get_connection(read_only=False)
        con.close()
        assert override.exists()
    finally:
        if old_edgar_db is None:
            monkeypatch.delenv("EDGAR_DB", raising=False)
        else:
            monkeypatch.setenv("EDGAR_DB", old_edgar_db)
        importlib.reload(db)
        importlib.reload(fetch_edgar)
        importlib.reload(load_fixture)
