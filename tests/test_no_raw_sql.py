"""The governance guarantee: there is no raw-SQL path, and caller-supplied
values cannot become SQL. These tests are the teeth behind the thesis.
"""

from __future__ import annotations

import inspect

from mcp_server import tools
from mcp_server.compiler import compile_query
from semantic_layer.loader import SemanticLayer

SL = SemanticLayer.load()


def test_no_governed_tool_accepts_a_sql_parameter():
    # None of the four governed tools may expose a parameter that could carry SQL.
    forbidden = {"sql", "query", "raw", "statement", "expr", "expression", "where"}
    for fn in (tools.list_metrics, tools.get_metric_definition, tools.resolve_metric,
               tools.query_metric):
        params = set(inspect.signature(fn).parameters)
        assert not (params & forbidden), f"{fn.__name__} exposes {params & forbidden}"


def test_query_metric_only_exposes_governed_parameters():
    params = list(inspect.signature(tools.query_metric).parameters)
    assert params == ["metric", "dimensions", "filters", "time_grain"]


def test_caller_metric_name_is_a_lookup_not_interpolation():
    # An injection attempt in the metric NAME is treated as an unknown metric, never run.
    res = tools.query_metric("total_revenue; DROP TABLE main_marts.fct_company_year; --")
    assert res["status"] == "error"


def test_filter_values_are_bound_parameters_not_interpolated():
    injection = "SNOW' OR '1'='1"
    q = compile_query(SL, "total_revenue", filters={"company": injection})
    # The malicious string must live in params, never in the SQL text.
    assert injection not in q.sql
    assert injection in q.params
    assert "?" in q.sql


def test_injection_in_filter_value_matches_nothing():
    res = tools.query_metric("total_revenue", filters={"company": "SNOW' OR '1'='1"})
    assert res["status"] == "ok"
    assert res["rows"] == []  # parameterized: it matched a literal ticker, which doesn't exist


def test_table_still_present_after_injection_attempts():
    # Prove nothing was dropped/mutated by the attempts above.
    res = tools.query_metric("total_revenue", filters={"company": "SNOW", "fiscal_year": 2024})
    assert res["status"] == "ok" and res["rows"][0]["value"] is not None
