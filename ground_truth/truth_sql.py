"""Independent ground truth for the eval's golden set.

These SQL statements are hand-written directly from each metric's definition and run
against the mart with NO LLM and WITHOUT importing the MCP compiler. That independence is
what makes the eval meaningful: if the compiler emits wrong SQL, or the agent reports a
wrong number, the value here will not move with it.

A few golden questions are additionally anchored to values verifiable in the actual 10-K
filings (see eval/golden_set.yml) to catch definitional errors as well as compiler bugs.
"""

from __future__ import annotations

from db import MART_TABLE, get_connection

# One self-contained SELECT per governed metric. Parameterized by (ticker, fiscal_year).
_GROUND_TRUTH_SQL: dict[str, str] = {
    "total_revenue": "SELECT total_revenue",
    "revenue_growth_yoy": "SELECT (total_revenue - prev_total_revenue) / prev_total_revenue",
    "gross_margin": "SELECT gross_profit / total_revenue",
    "operating_margin": "SELECT operating_income / total_revenue",
    "rnd_intensity": "SELECT rnd_expense / total_revenue",
    "fcf_margin": "SELECT (operating_cash_flow - capex) / total_revenue",
    "rule_of_40": (
        "SELECT 100 * (((total_revenue - prev_total_revenue) / prev_total_revenue) "
        "+ ((operating_cash_flow - capex) / total_revenue))"
    ),
}


def ground_truth(metric: str, ticker: str, fiscal_year: int) -> float | None:
    """Return the independently-computed value, or None if the metric is unavailable
    for that company-year (e.g. Workday gross_margin)."""
    if metric not in _GROUND_TRUTH_SQL:
        raise KeyError(f"No ground-truth definition for metric '{metric}'")
    sql = f"{_GROUND_TRUTH_SQL[metric]} AS value FROM {MART_TABLE} " \
          "WHERE ticker = ? AND fiscal_year = ?"
    con = get_connection()
    try:
        row = con.execute(sql, [ticker, fiscal_year]).fetchone()
    finally:
        con.close()
    if row is None or row[0] is None:
        return None
    return float(row[0])
