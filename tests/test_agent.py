"""Phase 5 — the deterministic reference agent obeys the governance contract, and the
live agent is wired to only the governed tools.
"""

from __future__ import annotations

import pytest

from agent import analyst, reference_agent
from ground_truth.truth_sql import ground_truth


def test_reference_agent_answers_with_ground_truth_value():
    r = reference_agent.answer("What was Snowflake's total revenue in fiscal 2024?")
    assert r.refused is False
    assert r.metric == "total_revenue" and r.company == "SNOW" and r.fiscal_year == 2024
    assert r.value == pytest.approx(ground_truth("total_revenue", "SNOW", 2024))


def test_reference_agent_refuses_ambiguous():
    r = reference_agent.answer("How's our margin doing?")
    assert r.refused is True
    assert r.value is None
    assert "ambiguous" in r.text.lower()


def test_reference_agent_refuses_out_of_scope():
    r = reference_agent.answer("What's Datadog's net dollar retention in 2023?")
    assert r.refused is True
    assert r.value is None


def test_reference_agent_refuses_unavailable_metric():
    r = reference_agent.answer("What was Workday's gross margin in 2024?")
    assert r.refused is True
    assert "not available" in r.text.lower()


def test_reference_agent_refuses_when_period_missing():
    r = reference_agent.answer("What is Snowflake's total revenue?")
    assert r.refused is True
    assert r.value is None


# ---- live agent wiring (no API call) ----------------------------------------


def test_live_agent_exposes_only_governed_tools_plus_terminator():
    names = {t["name"] for t in analyst.TOOL_SCHEMAS}
    assert names == {
        "list_metrics", "get_metric_definition", "resolve_metric", "query_metric",
        "final_answer",
    }
    # No tool schema accepts a raw SQL field.
    for t in analyst.TOOL_SCHEMAS:
        assert "sql" not in t["input_schema"].get("properties", {})


def test_live_agent_dispatch_covers_every_governed_tool():
    assert set(analyst._DISPATCH) == {
        "list_metrics", "get_metric_definition", "resolve_metric", "query_metric",
    }
