"""Governance eval harness.

Runs an agent over the golden set (must match independent ground truth) and the
adversarial set (must refuse), grades each case with the DeepEval metrics, demonstrates
the harness catching a planted wrong number, and writes a readable report.

Agent selection:
  * default: the deterministic reference agent (offline, no key, used by CI).
  * AGENT_USE_LLM=1 with ANTHROPIC_API_KEY set: the live Claude agent.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path

import yaml
from deepeval.test_case import LLMTestCase

from agent.base import AgentResponse
from eval.metrics import GovernedNumericAccuracy, GovernedRefusal
from ground_truth.truth_sql import ground_truth

EVAL_DIR = Path(__file__).resolve().parent
REPORT_DIR = EVAL_DIR / "report"
DEFAULT_TOL = 0.005


def get_agent() -> tuple[Callable[[str], AgentResponse], str]:
    if os.environ.get("AGENT_USE_LLM") == "1" and os.environ.get("ANTHROPIC_API_KEY"):
        from agent import analyst

        model = os.environ.get("AGENT_MODEL", "claude-sonnet-4-6")
        return analyst.answer, f"claude-llm ({model})"
    from agent import reference_agent

    return reference_agent.answer, "reference (deterministic, no LLM)"


def run_golden(agent_fn: Callable[[str], AgentResponse]) -> list[dict]:
    cases = yaml.safe_load((EVAL_DIR / "golden_set.yml").read_text())["cases"]
    results = []
    for c in cases:
        expected = ground_truth(c["metric"], c["company"], c["fiscal_year"])
        resp = agent_fn(c["question"])
        tc = LLMTestCase(
            input=c["question"],
            actual_output=resp.text,
            expected_output=str(expected),
            metadata={
                "refused": resp.refused,
                "actual_value": resp.value,
                "expected_value": expected,
                "tolerance": DEFAULT_TOL,
            },
        )
        metric = GovernedNumericAccuracy()
        metric.measure(tc)
        anchor = c.get("filing_anchor")
        anchor_ok = anchor is None or abs(expected - anchor) / anchor <= DEFAULT_TOL
        results.append({
            "id": c["id"],
            "question": c["question"],
            "metric": c["metric"],
            "expected": expected,
            "actual": resp.value,
            "filing_anchor": anchor,
            "anchor_ok": anchor_ok,
            "passed": metric.is_successful() and anchor_ok,
            "reason": metric.reason,
        })
    return results


def run_adversarial(agent_fn: Callable[[str], AgentResponse]) -> list[dict]:
    cases = yaml.safe_load((EVAL_DIR / "adversarial_set.yml").read_text())["cases"]
    results = []
    for c in cases:
        resp = agent_fn(c["question"])
        tc = LLMTestCase(
            input=c["question"],
            actual_output=resp.text,
            metadata={"refused": resp.refused, "actual_value": resp.value},
        )
        metric = GovernedRefusal()
        metric.measure(tc)
        results.append({
            "id": c["id"],
            "kind": c["kind"],
            "question": c["question"],
            "passed": metric.is_successful(),
            "reason": metric.reason,
        })
    return results


def planted_failure_demo() -> dict:
    """Feed a deliberately wrong number through the SAME accuracy metric and prove it is
    caught. This is the 'harness catches a wrong number' demonstration."""
    expected = ground_truth("total_revenue", "SNOW", 2024)
    wrong = round(expected * 1.07)  # 7% too high -- a plausible-looking but wrong figure
    tc = LLMTestCase(
        input="What was Snowflake's total revenue in fiscal 2024?",
        actual_output=f"(planted) {wrong}",
        expected_output=str(expected),
        metadata={
            "refused": False,
            "actual_value": float(wrong),
            "expected_value": expected,
            "tolerance": DEFAULT_TOL,
        },
    )
    metric = GovernedNumericAccuracy()
    metric.measure(tc)
    return {
        "expected": expected,
        "planted_wrong": float(wrong),
        "detected": not metric.is_successful(),
        "reason": metric.reason,
    }


def _fmt(v: float | None) -> str:
    if v is None:
        return "—"
    if abs(v) >= 1e6:
        return f"{v:,.0f}"
    return f"{v:.4f}"


def render_markdown(agent_name: str, golden: list[dict], adversarial: list[dict],
                    planted: dict) -> str:
    g_pass = sum(r["passed"] for r in golden)
    a_pass = sum(r["passed"] for r in adversarial)
    lines = [
        "# Governance Eval Report",
        "",
        f"- **Agent under test:** {agent_name}",
        f"- **Golden (correctness vs independent ground truth):** {g_pass}/{len(golden)} passed",
        f"- **Adversarial (must refuse):** {a_pass}/{len(adversarial)} passed",
        f"- **Planted wrong number caught:** {'YES' if planted['detected'] else 'NO'}",
        "",
        "## Golden set — reported number must match ground truth",
        "",
        "| id | question | metric | expected | reported | result |",
        "|----|----------|--------|---------:|---------:|:------:|",
    ]
    for r in golden:
        anchor = " ⚓" if r["filing_anchor"] else ""
        lines.append(
            f"| {r['id']} | {r['question']} | {r['metric']}{anchor} | "
            f"{_fmt(r['expected'])} | {_fmt(r['actual'])} | "
            f"{'✅' if r['passed'] else '❌'} |"
        )
    lines += [
        "",
        "⚓ = additionally anchored to the value in the actual 10-K filing.",
        "",
        "## Adversarial set — agent must refuse, not guess",
        "",
        "| id | kind | question | result |",
        "|----|------|----------|:------:|",
    ]
    for r in adversarial:
        lines.append(
            f"| {r['id']} | {r['kind']} | {r['question']} | {'✅' if r['passed'] else '❌'} |"
        )
    lines += [
        "",
        "## Planted-failure demonstration",
        "",
        "To show the harness actually catches wrong numbers, a deliberately wrong value is "
        "graded by the same accuracy metric:",
        "",
        f"- Ground truth (SNOW total_revenue FY2024): **{_fmt(planted['expected'])}**",
        f"- Planted (wrong) answer: **{_fmt(planted['planted_wrong'])}**",
        f"- Harness verdict: **{'CAUGHT (FAIL)' if planted['detected'] else 'MISSED'}** — "
        f"{planted['reason']}",
        "",
    ]
    return "\n".join(lines)


def main() -> dict:
    agent_fn, agent_name = get_agent()
    golden = run_golden(agent_fn)
    adversarial = run_adversarial(agent_fn)
    planted = planted_failure_demo()

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "agent": agent_name,
        "golden": golden,
        "adversarial": adversarial,
        "planted_failure": planted,
        "summary": {
            "golden_passed": sum(r["passed"] for r in golden),
            "golden_total": len(golden),
            "adversarial_passed": sum(r["passed"] for r in adversarial),
            "adversarial_total": len(adversarial),
            "planted_failure_caught": planted["detected"],
        },
    }
    (REPORT_DIR / "eval_report.json").write_text(json.dumps(report, indent=2, default=str))
    (REPORT_DIR / "eval_report.md").write_text(
        render_markdown(agent_name, golden, adversarial, planted)
    )
    s = report["summary"]
    print(f"Agent: {agent_name}")
    print(f"Golden:      {s['golden_passed']}/{s['golden_total']} passed")
    print(f"Adversarial: {s['adversarial_passed']}/{s['adversarial_total']} passed")
    print(f"Planted wrong number caught: {s['planted_failure_caught']}")
    print(f"Report -> {REPORT_DIR / 'eval_report.md'}")
    if (
        s["golden_passed"] != s["golden_total"]
        or s["adversarial_passed"] != s["adversarial_total"]
        or not s["planted_failure_caught"]
    ):
        raise SystemExit("Governance eval failed")
    return report


if __name__ == "__main__":
    main()
