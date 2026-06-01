"""Deterministic governed agent — the governance contract with no LLM in the loop.

It uses exactly the governed tools (resolve_metric, query_metric) and applies the refusal
rules directly. It exists so the eval and CI can run the full harness offline (no API key,
no cost, no nondeterminism) and so there is a governed baseline isolated from LLM variance.
The live LLM agent is agent/analyst.py.

Refusal rules (identical to what the system prompt asks of Claude):
  * out-of-scope question -> refuse, name that the metric isn't governed
  * ambiguous question    -> refuse, ask which governed metric (and period)
  * missing company/year  -> refuse, ask for them
  * metric not available for that company-year (e.g. Workday gross_margin) -> refuse, say so
  * otherwise             -> report ONLY the number query_metric returned
"""

from __future__ import annotations

from agent.base import AgentResponse, extract_company, extract_fiscal_year
from mcp_server import tools


def answer(question: str) -> AgentResponse:
    trace: list[dict] = []

    res = tools.resolve_metric(question)
    trace.append({"tool": "resolve_metric", "args": {"text": question}, "result": res})

    if res["status"] == tools.RESOLUTION_OUT_OF_SCOPE:
        return AgentResponse(
            question, refused=True, text=res["message"], tool_trace=trace,
        )
    if res["status"] == tools.RESOLUTION_AMBIGUOUS:
        return AgentResponse(
            question, refused=True, text=res["message"], tool_trace=trace,
        )

    metric = res["metrics"][0]
    company = extract_company(question)
    fiscal_year = extract_fiscal_year(question)

    if company is None or fiscal_year is None:
        missing = "a company" if company is None else "a fiscal year"
        if company is None and fiscal_year is None:
            missing = "a company and a fiscal year"
        return AgentResponse(
            question, refused=True, metric=metric, company=company, fiscal_year=fiscal_year,
            text=f"'{metric}' is governed, but I need {missing} to answer. Please specify.",
            tool_trace=trace,
        )

    q = tools.query_metric(metric, filters={"company": company, "fiscal_year": fiscal_year})
    trace.append({
        "tool": "query_metric",
        "args": {"metric": metric, "filters": {"company": company, "fiscal_year": fiscal_year}},
        "result": q,
    })

    if q["status"] != "ok" or not q["rows"]:
        return AgentResponse(
            question, refused=True, metric=metric, company=company, fiscal_year=fiscal_year,
            text=f"No governed data for {metric} / {company} / FY{fiscal_year}.",
            tool_trace=trace,
        )

    row = q["rows"][0]
    if not row["available"]:
        return AgentResponse(
            question, refused=True, metric=metric, company=company, fiscal_year=fiscal_year,
            text=(
                f"{metric} is not available for {company} FY{fiscal_year} in the governed "
                "source (the company does not tag it). I won't estimate it."
            ),
            tool_trace=trace,
        )

    value = float(row["value"])
    return AgentResponse(
        question, refused=False, value=value, metric=metric, company=company,
        fiscal_year=fiscal_year,
        text=f"{metric} for {company} FY{fiscal_year} = {value}", tool_trace=trace,
    )


if __name__ == "__main__":
    for question in [
        "What was Snowflake's total revenue in fiscal 2024?",
        "What's CrowdStrike's rule of 40 for 2024?",
        "How's our margin doing?",
        "What's Datadog's net dollar retention in 2023?",
        "What was Workday's gross margin in 2024?",
    ]:
        r = answer(question)
        verdict = "REFUSED" if r.refused else f"ANSWER={r.value}"
        print(f"[{verdict}] {question}\n   -> {r.text}\n")
