"""Phase 3 — semantic layer loading/validation, resolution, and ground truth."""

from __future__ import annotations

import pytest

from ground_truth.truth_sql import ground_truth
from semantic_layer.loader import (
    Resolution,
    SemanticLayer,
    SemanticLayerError,
)

EXPECTED_METRICS = {
    "total_revenue",
    "revenue_growth_yoy",
    "gross_margin",
    "operating_margin",
    "rnd_intensity",
    "fcf_margin",
    "rule_of_40",
}


@pytest.fixture(scope="module")
def sl() -> SemanticLayer:
    return SemanticLayer.load()


def test_loads_all_governed_metrics(sl: SemanticLayer):
    assert set(sl.metrics) == EXPECTED_METRICS


def test_every_expression_uses_only_allowlisted_columns(sl: SemanticLayer):
    # Loading already validates; this asserts the allowlist is actually enforced.
    for m in sl.list_metrics():
        idents = set(__import__("re").findall(r"[A-Za-z_][A-Za-z0-9_]*", m.sql_expression))
        assert idents <= sl.allowed_columns, f"{m.name} references {idents - sl.allowed_columns}"


def test_expression_validation_rejects_unknown_column(sl: SemanticLayer):
    with pytest.raises(SemanticLayerError):
        SemanticLayer._validate_expression("bad", "revenue / headcount", sl.allowed_columns)


@pytest.mark.parametrize(
    "text,status,expected",
    [
        ("gross margin", Resolution.RESOLVED, ["gross_margin"]),
        ("how is our gross margin in fy2024", Resolution.RESOLVED, ["gross_margin"]),
        ("revenue growth", Resolution.RESOLVED, ["revenue_growth_yoy"]),
        ("rule of 40", Resolution.RESOLVED, ["rule_of_40"]),
        ("total revenue", Resolution.RESOLVED, ["total_revenue"]),
        ("margin", Resolution.AMBIGUOUS, None),
        ("profitability", Resolution.AMBIGUOUS, None),
        ("gross margin and operating margin", Resolution.AMBIGUOUS, None),
        ("net dollar retention", Resolution.OUT_OF_SCOPE, []),
        ("what is the stock price", Resolution.OUT_OF_SCOPE, []),
    ],
)
def test_resolution(sl: SemanticLayer, text, status, expected):
    r = sl.resolve(text)
    assert r.status == status
    if expected is not None:
        assert r.metrics == expected
    if status == Resolution.AMBIGUOUS:
        assert len(r.metrics) > 1


def test_ambiguous_margin_surfaces_all_three(sl: SemanticLayer):
    r = sl.resolve("what's the margin")
    assert set(r.metrics) == {"gross_margin", "operating_margin", "fcf_margin"}


# ---- ground truth (requires the built warehouse) ----------------------------


def test_ground_truth_matches_filing_anchors():
    # Snowflake FY2024 total revenue is $2.8065B in the 10-K.
    assert ground_truth("total_revenue", "SNOW", 2024) == pytest.approx(2.806489e9, rel=1e-4)
    # Datadog FY2023 gross margin ~80.7%.
    assert ground_truth("gross_margin", "DDOG", 2023) == pytest.approx(0.807, abs=0.005)


def test_ground_truth_admits_workday_gross_margin_gap():
    assert ground_truth("gross_margin", "WDAY", 2024) is None


def test_ground_truth_unknown_metric_raises():
    with pytest.raises(KeyError):
        ground_truth("nonexistent_metric", "SNOW", 2024)
