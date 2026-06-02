"""The compiler produces correct, parameterized SQL and runs it."""

from __future__ import annotations

import pytest

from ground_truth.truth_sql import ground_truth
from mcp_server import tools
from mcp_server.compiler import CompileError, compile_query
from semantic_layer.loader import SemanticLayer


@pytest.fixture(scope="module")
def sl() -> SemanticLayer:
    return SemanticLayer.load()


def test_compiles_filtered_query(sl: SemanticLayer):
    q = compile_query(sl, "total_revenue", ["company"], {"company": "SNOW", "fiscal_year": 2024})
    assert "FROM main_marts.fct_company_year" in q.sql
    assert "ticker = ?" in q.sql and "fiscal_year = ?" in q.sql
    assert q.params == ["SNOW", 2024]


def test_list_filter_becomes_in_clause(sl: SemanticLayer):
    q = compile_query(sl, "rule_of_40", filters={"company": ["SNOW", "DDOG"]})
    assert "ticker IN (?, ?)" in q.sql
    assert q.params == ["SNOW", "DDOG"]


def test_unknown_metric_rejected(sl: SemanticLayer):
    with pytest.raises(CompileError):
        compile_query(sl, "gross_margin_non_gaap")


def test_forbidden_filter_rejected(sl: SemanticLayer):
    with pytest.raises(CompileError):
        compile_query(sl, "total_revenue", filters={"sector": "software"})


def test_unsupported_time_grain_rejected(sl: SemanticLayer):
    with pytest.raises(CompileError):
        compile_query(sl, "total_revenue", time_grain="quarter")


def test_query_metric_matches_ground_truth():
    res = tools.query_metric("total_revenue", filters={"company": "SNOW", "fiscal_year": 2024})
    assert res["status"] == "ok"
    assert len(res["rows"]) == 1
    assert res["rows"][0]["value"] == pytest.approx(ground_truth("total_revenue", "SNOW", 2024))


def test_query_metric_reports_workday_gap_as_not_available():
    res = tools.query_metric("gross_margin", filters={"company": "WDAY", "fiscal_year": 2024})
    assert res["status"] == "ok"
    assert res["rows"][0]["available"] is False
    assert res["rows"][0]["value"] is None


def test_query_metric_unknown_returns_error_not_crash():
    res = tools.query_metric("ebitda")
    assert res["status"] == "error"
