"""Custom MCP server exposing ONLY governed metrics.

Run as a stdio MCP server (e.g. from Claude Desktop or any MCP client):

    uv run python -m mcp_server.server

Every tool delegates to mcp_server.tools, the same governed functions the in-process
agent uses. There is deliberately no tool that accepts raw SQL.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from mcp_server import tools

mcp = FastMCP(
    name="governed-metrics",
    instructions=(
        "Exposes a governed semantic layer over SEC 10-K SaaS financials. You may only "
        "read metrics through these tools. There is no raw-SQL capability. Resolve a "
        "question with resolve_metric first; if it is ambiguous or out of scope, refuse "
        "and ask the user to clarify instead of guessing."
    ),
)


@mcp.tool(description="List every governed metric (name, label, description, format, owner).")
def list_metrics() -> list[dict[str, str]]:
    return tools.list_metrics()


@mcp.tool(description="Get the full governed definition of one metric.")
def get_metric_definition(metric: str) -> dict[str, Any]:
    return tools.get_metric_definition(metric)


@mcp.tool(
    description=(
        "Resolve a free-text request to governed metric(s). Returns status "
        "'resolved' (one metric), 'ambiguous' (several, ask which), or 'out_of_scope' "
        "(none, refuse)."
    )
)
def resolve_metric(text: str) -> dict[str, Any]:
    return tools.resolve_metric(text)


@mcp.tool(
    description=(
        "Query a governed metric for the given dimensions/filters. SQL is compiled only "
        "from the semantic layer; raw SQL is not possible. Filters: {'company': <ticker "
        "or list>, 'fiscal_year': <year or list>}. Null values are reported as not "
        "available rather than guessed."
    )
)
def query_metric(
    metric: str,
    dimensions: list[str] | None = None,
    filters: dict[str, Any] | None = None,
    time_grain: str | None = None,
) -> dict[str, Any]:
    return tools.query_metric(metric, dimensions, filters, time_grain)


if __name__ == "__main__":
    mcp.run(transport="stdio")
