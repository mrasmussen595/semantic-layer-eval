"""Runnable demo of the governed analyst (no API key needed -- uses the reference agent).

    uv run python scripts/demo.py

Walks through a correct answer and the four ways the agent refuses instead of guessing.
The live Claude agent (agent/analyst.py) behaves to the same contract with a key.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import reference_agent  # noqa: E402

WALKTHROUGH = [
    ("Governed answer", "What was Snowflake's total revenue in fiscal 2024?"),
    ("Ambiguous -> refuse", "How's our margin looking?"),
    ("Out of scope -> refuse", "What was Datadog's net dollar retention in 2023?"),
    ("Non-GAAP trap -> refuse", "What was Snowflake's non-GAAP gross margin in fiscal 2024?"),
    ("Unavailable -> refuse", "What was Workday's gross margin in fiscal 2024?"),
]


def main() -> None:
    print("=" * 78)
    print("Governing the AI Analyst — governed semantic layer over SEC 10-K financials")
    print("=" * 78)
    for label, question in WALKTHROUGH:
        r = reference_agent.answer(question)
        verdict = "ANSWER" if not r.refused else "REFUSED"
        print(f"\n[{label}]")
        print(f"  Q: {question}")
        print(f"  {verdict}: {r.text}")
    print("\n" + "=" * 78)
    print("Every number above came from query_metric over the governed layer. No raw SQL,")
    print("no estimates, no fabrication.")
    print("Full correctness/refusal proof: eval/report/eval_report.md")


if __name__ == "__main__":
    main()
