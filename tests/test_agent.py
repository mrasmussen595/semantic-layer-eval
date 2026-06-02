"""Phase 5 — the deterministic reference agent obeys the governance contract, and the
live agent is wired to only the governed tools.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent import analyst, reference_agent
from agent.base import extract_company
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


@pytest.mark.parametrize(
    "question",
    [
        "What is total revenue now in 2023?",
        "What was net revenue in 2023?",
        "What was our team's revenue in 2023?",
    ],
)
def test_company_extraction_does_not_treat_common_words_as_tickers(question):
    assert extract_company(question) is None


def test_company_extraction_accepts_uppercase_ticker():
    assert extract_company("What was NOW revenue in 2023?") == "NOW"


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


def test_live_agent_rejects_answer_without_query_provenance(monkeypatch):
    fabricated = SimpleNamespace(
        type="tool_use",
        name="final_answer",
        id="fabricated",
        input={
            "refused": False,
            "value": 123456789.0,
            "metric": "total_revenue",
            "company": "SNOW",
            "fiscal_year": 2024,
            "explanation": "fabricated",
        },
    )
    client = SimpleNamespace(
        messages=SimpleNamespace(
            create=lambda **kwargs: SimpleNamespace(content=[fabricated]),
        ),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "anthropic",
        SimpleNamespace(Anthropic=lambda: client),
    )

    r = analyst.answer("What was Snowflake's total revenue in fiscal 2024?")

    assert r.refused is True
    assert r.value is None
    assert "governance" in r.text.lower()


def test_live_agent_accepts_answer_with_query_provenance(monkeypatch):
    question = "What was Snowflake's total revenue in fiscal 2024?"
    responses = iter([
        SimpleNamespace(content=[
            SimpleNamespace(
                type="tool_use",
                name="resolve_metric",
                id="resolve",
                input={"text": question},
            ),
        ]),
        SimpleNamespace(content=[
            SimpleNamespace(
                type="tool_use",
                name="query_metric",
                id="query",
                input={
                    "metric": "total_revenue",
                    "filters": {"company": "SNOW", "fiscal_year": 2024},
                },
            ),
        ]),
        SimpleNamespace(content=[
            SimpleNamespace(
                type="tool_use",
                name="final_answer",
                id="answer",
                input={
                    "refused": False,
                    "value": 2806489000.0,
                    "metric": "total_revenue",
                    "company": "SNOW",
                    "fiscal_year": 2024,
                    "explanation": "governed",
                },
            ),
        ]),
    ])
    client = SimpleNamespace(
        messages=SimpleNamespace(create=lambda **kwargs: next(responses)),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "anthropic",
        SimpleNamespace(Anthropic=lambda: client),
    )

    r = analyst.answer(question)

    assert r.refused is False
    assert r.value == 2806489000.0
