"""Phase 6 — the governance eval, runnable in CI against the deterministic reference agent.

Golden cases must match independent ground truth; adversarial cases must refuse; and the
harness must catch a planted wrong number. The live Claude agent is graded by the same
harness via AGENT_USE_LLM=1 (see eval/harness.py), but CI runs offline.
"""

from __future__ import annotations

import pytest
from deepeval.metrics import BaseMetric

from agent import reference_agent
from agent.base import AgentResponse
from eval import harness
from eval.harness import planted_failure_demo, run_adversarial, run_golden
from eval.metrics import GovernedNumericAccuracy, GovernedRefusal


def test_golden_cases_match_ground_truth():
    results = run_golden(reference_agent.answer)
    failed = [(r["id"], r["reason"]) for r in results if not r["passed"]]
    assert not failed, f"golden failures: {failed}"
    assert len(results) >= 8


def test_adversarial_cases_are_refused():
    results = run_adversarial(reference_agent.answer)
    failed = [(r["id"], r["kind"], r["reason"]) for r in results if not r["passed"]]
    assert not failed, f"adversarial failures: {failed}"


def test_harness_catches_planted_wrong_number():
    demo = planted_failure_demo()
    assert demo["detected"] is True
    assert demo["planted_wrong"] != demo["expected"]


def test_metrics_are_real_deepeval_metrics():
    assert issubclass(GovernedNumericAccuracy, BaseMetric)
    assert issubclass(GovernedRefusal, BaseMetric)


def test_harness_exits_nonzero_when_eval_fails(monkeypatch, tmp_path):
    def wrong_agent(question: str) -> AgentResponse:
        return AgentResponse(question=question, refused=False, value=1.0, text="wrong")

    monkeypatch.setattr(harness, "get_agent", lambda: (wrong_agent, "wrong"))
    monkeypatch.setattr(harness, "REPORT_DIR", tmp_path)

    with pytest.raises(SystemExit):
        harness.main()

    assert (tmp_path / "eval_report.md").exists()
