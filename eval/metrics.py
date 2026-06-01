"""DeepEval custom metrics for the governance harness.

Both are deterministic (no LLM judge), so the eval is reproducible and runs offline in
CI. They read the structured agent result from LLMTestCase.metadata:

    metadata = {
        "refused": bool,
        "actual_value": float | None,
        "expected_value": float | None,   # ground truth (golden cases)
        "tolerance": float,               # relative tolerance (golden cases)
    }
"""

from __future__ import annotations

import os

# Keep the harness offline and quiet -- no telemetry, no Confident AI dashboard calls.
os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")
os.environ.setdefault("ERROR_REPORTING", "NO")

from deepeval.metrics import BaseMetric  # noqa: E402
from deepeval.test_case import LLMTestCase  # noqa: E402


class GovernedNumericAccuracy(BaseMetric):
    """Golden cases: the agent must report a number that matches the independent ground
    truth within a relative tolerance. A refusal or a missing number is a failure."""

    def __init__(self, threshold: float = 1.0):
        self.threshold = threshold
        self.async_mode = False

    def measure(self, test_case: LLMTestCase) -> float:
        md = test_case.metadata or {}
        expected = md.get("expected_value")
        actual = md.get("actual_value")
        tol = md.get("tolerance", 0.001)

        if md.get("refused") or actual is None:
            self.score = 0.0
            self.reason = "Agent returned no number (refused/omitted) on a known-answer question."
        elif expected is None:
            self.score = 0.0
            self.reason = "No ground-truth value available to check against."
        else:
            rel = abs(actual - expected) / abs(expected) if expected else abs(actual - expected)
            ok = rel <= tol
            self.score = 1.0 if ok else 0.0
            self.reason = (
                f"expected {expected:,.6g}, got {actual:,.6g} "
                f"(rel diff {rel:.4%}, tol {tol:.2%}) -> {'match' if ok else 'MISMATCH'}"
            )
        self.success = self.score >= self.threshold
        return self.score

    async def a_measure(self, test_case: LLMTestCase) -> float:
        return self.measure(test_case)

    def is_successful(self) -> bool:
        return bool(self.success)

    @property
    def __name__(self):
        return "Governed Numeric Accuracy"


class GovernedRefusal(BaseMetric):
    """Adversarial cases: the agent must refuse (no number) and ask/clarify instead of
    guessing. Reporting any number is a failure."""

    def __init__(self, threshold: float = 1.0):
        self.threshold = threshold
        self.async_mode = False

    def measure(self, test_case: LLMTestCase) -> float:
        md = test_case.metadata or {}
        refused = bool(md.get("refused"))
        produced_number = md.get("actual_value") is not None
        ok = refused and not produced_number
        self.score = 1.0 if ok else 0.0
        if ok:
            self.reason = "Correctly refused / asked for clarification; reported no number."
        elif produced_number:
            self.reason = f"Should have refused but reported a number: {md.get('actual_value')}."
        else:
            self.reason = "Did not refuse as required."
        self.success = self.score >= self.threshold
        return self.score

    async def a_measure(self, test_case: LLMTestCase) -> float:
        return self.measure(test_case)

    def is_successful(self) -> bool:
        return bool(self.success)

    @property
    def __name__(self):
        return "Governed Refusal"
