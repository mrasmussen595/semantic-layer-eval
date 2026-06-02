"""Governed tool functions: the entire surface the agent (or any MCP client) can use.

These four functions are the only way to reach the data, and none of them accepts SQL.
Both the MCP server (server.py) and the in-process agent call exactly these, so the
governance guarantee is identical whether reached over MCP or directly.
"""

from __future__ import annotations

from typing import Any

from db import get_connection
from mcp_server.compiler import CompileError, compile_query
from semantic_layer.loader import Resolution, SemanticLayer

_SL = SemanticLayer.load()


def list_metrics() -> list[dict[str, str]]:
    """List every governed metric (name, label, description, format, owner)."""
    return [
        {
            "name": m.name,
            "label": m.label,
            "description": m.description,
            "format": m.format,
            "owner": m.owner,
        }
        for m in _SL.list_metrics()
    ]


def get_metric_definition(metric: str) -> dict[str, Any]:
    """Return the full governed definition of one metric, or an error if it is not governed."""
    m = _SL.get(metric)
    if m is None:
        return {
            "status": "error",
            "message": f"'{metric}' is not a governed metric.",
            "governed_metrics": sorted(_SL.metrics),
        }
    return {
        "status": "ok",
        "name": m.name,
        "label": m.label,
        "description": m.description,
        "synonyms": list(m.synonyms),
        "sql_expression": m.sql_expression,
        "format": m.format,
        "grain": m.grain,
        "dimensions": list(m.dimensions),
        "filters": list(m.filters),
        "owner": m.owner,
    }


def resolve_metric(text: str) -> dict[str, Any]:
    """Map a free-text request to governed metric(s).

    Returns status 'resolved' (exactly one), 'ambiguous' (more than one, the agent must
    ask which), or 'out_of_scope' (none, the agent must refuse). This is the gate that
    makes refusal possible.
    """
    r = _SL.resolve(text)
    return {"status": r.status.value, "metrics": r.metrics, "message": r.message}


def query_metric(
    metric: str,
    dimensions: list[str] | None = None,
    filters: dict[str, Any] | None = None,
    time_grain: str | None = None,
) -> dict[str, Any]:
    """Return values for a governed metric. Compiles SQL ONLY from the semantic layer;
    raw SQL is impossible. Rows whose value is null are reported as 'not_available'
    (e.g. Workday gross_margin) rather than guessed.
    """
    try:
        compiled = compile_query(_SL, metric, dimensions, filters, time_grain)
    except CompileError as e:
        return {"status": "error", "message": str(e)}

    con = get_connection()
    try:
        cur = con.execute(compiled.sql, compiled.params)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]
    finally:
        con.close()

    out_rows = []
    for row in rows:
        out_rows.append(
            {
                "ticker": row["ticker"],
                "fiscal_year": row["fiscal_year"],
                "value": row["value"],
                "available": row["value"] is not None,
            }
        )
    return {
        "status": "ok",
        "metric": metric,
        "format": _SL.metrics[metric].format,
        "compiled_sql": compiled.sql,  # surfaced for transparency/auditability
        "rows": out_rows,
    }


# Re-exported so callers can branch on resolution status without importing the enum.
RESOLUTION_RESOLVED = Resolution.RESOLVED.value
RESOLUTION_AMBIGUOUS = Resolution.AMBIGUOUS.value
RESOLUTION_OUT_OF_SCOPE = Resolution.OUT_OF_SCOPE.value
