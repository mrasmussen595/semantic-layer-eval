"""Live Claude analyst, governed through the MCP tools.

Runs a standard tool-use loop with Anthropic's API. The model may only call the governed
tools; it must conclude by calling `final_answer`, which we turn into the same
AgentResponse the deterministic reference agent emits, so the eval grades both identically.

Requires ANTHROPIC_API_KEY. Model defaults to claude-sonnet-4-6 (override with AGENT_MODEL).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from agent.base import AgentResponse
from mcp_server import tools

SYSTEM_PROMPT = (Path(__file__).resolve().parent / "system_prompt.md").read_text()
DEFAULT_MODEL = os.environ.get("AGENT_MODEL", "claude-sonnet-4-6")
MAX_TURNS = 8

# Anthropic tool schemas for the four governed tools plus the structured terminator.
TOOL_SCHEMAS = [
    {
        "name": "list_metrics",
        "description": "List every governed metric (name, label, description, format, owner).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_metric_definition",
        "description": "Get the full governed definition of one metric.",
        "input_schema": {
            "type": "object",
            "properties": {"metric": {"type": "string"}},
            "required": ["metric"],
        },
    },
    {
        "name": "resolve_metric",
        "description": "Resolve free text to governed metric(s): resolved/ambiguous/out_of_scope.",
        "input_schema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
    {
        "name": "query_metric",
        "description": "Query a governed metric. SQL is compiled only from the semantic layer.",
        "input_schema": {
            "type": "object",
            "properties": {
                "metric": {"type": "string"},
                "dimensions": {"type": "array", "items": {"type": "string"}},
                "filters": {"type": "object"},
                "time_grain": {"type": "string"},
            },
            "required": ["metric"],
        },
    },
    {
        "name": "final_answer",
        "description": "Conclude. Call exactly once. Set refused=true to refuse/clarify.",
        "input_schema": {
            "type": "object",
            "properties": {
                "refused": {"type": "boolean"},
                "value": {"type": ["number", "null"]},
                "metric": {"type": ["string", "null"]},
                "company": {"type": ["string", "null"]},
                "fiscal_year": {"type": ["integer", "null"]},
                "explanation": {"type": "string"},
            },
            "required": ["refused", "explanation"],
        },
    },
]

_DISPATCH = {
    "list_metrics": lambda a: tools.list_metrics(),
    "get_metric_definition": lambda a: tools.get_metric_definition(a["metric"]),
    "resolve_metric": lambda a: tools.resolve_metric(a["text"]),
    "query_metric": lambda a: tools.query_metric(
        a["metric"], a.get("dimensions"), a.get("filters"), a.get("time_grain")
    ),
}


def _has_query_provenance(answer: dict, trace: list[dict]) -> bool:
    resolved = False
    for call in trace:
        if call["tool"] == "resolve_metric":
            result = call["result"]
            resolved = (
                result["status"] == tools.RESOLUTION_RESOLVED
                and result["metrics"] == [answer.get("metric")]
            )
        elif call["tool"] == "query_metric" and resolved:
            args = call["args"]
            filters = args.get("filters") or {}
            result = call["result"]
            if (
                args["metric"] == answer.get("metric")
                and filters.get("company") == answer.get("company")
                and filters.get("fiscal_year") == answer.get("fiscal_year")
                and result["status"] == "ok"
                and any(
                    row["ticker"] == answer.get("company")
                    and row["fiscal_year"] == answer.get("fiscal_year")
                    and row["available"]
                    and row["value"] == answer.get("value")
                    for row in result["rows"]
                )
            ):
                return True
    return False


def answer(question: str, model: str = DEFAULT_MODEL) -> AgentResponse:
    import anthropic  # imported here so the module loads without the SDK configured

    client = anthropic.Anthropic()
    messages: list[dict] = [{"role": "user", "content": question}]
    trace: list[dict] = []

    for _ in range(MAX_TURNS):
        resp = client.messages.create(
            model=model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOL_SCHEMAS,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": resp.content})

        tool_uses = [b for b in resp.content if getattr(b, "type", None) == "tool_use"]
        if not tool_uses:
            # Model stopped without a final_answer; treat as a refusal we can grade.
            text = "".join(getattr(b, "text", "") for b in resp.content)
            return AgentResponse(question, refused=True, text=text, tool_trace=trace)

        tool_results = []
        for tu in tool_uses:
            if tu.name == "final_answer":
                a = tu.input
                if not a.get("refused", True) and not _has_query_provenance(a, trace):
                    return AgentResponse(
                        question=question,
                        refused=True,
                        text="Governance rejected an answer without matching query provenance.",
                        tool_trace=trace,
                    )
                return AgentResponse(
                    question=question,
                    refused=bool(a.get("refused", True)),
                    value=a.get("value"),
                    metric=a.get("metric"),
                    company=a.get("company"),
                    fiscal_year=a.get("fiscal_year"),
                    text=a.get("explanation", ""),
                    tool_trace=trace,
                )
            result = _DISPATCH[tu.name](tu.input)
            trace.append({"tool": tu.name, "args": tu.input, "result": result})
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": json.dumps(result, default=str),
            })
        messages.append({"role": "user", "content": tool_results})

    return AgentResponse(
        question, refused=True, text="Stopped without a final answer.", tool_trace=trace
    )


if __name__ == "__main__":
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit(
            "Set ANTHROPIC_API_KEY to run the live agent (or use the reference agent)."
        )
    import sys

    q = " ".join(sys.argv[1:]) or "What was Snowflake's total revenue in fiscal 2024?"
    r = answer(q)
    print(("REFUSED: " if r.refused else f"ANSWER {r.value}: ") + r.text)
