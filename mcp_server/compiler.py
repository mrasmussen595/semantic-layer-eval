"""Compile a governed metric request into parameterized SQL.

The ONLY way to produce SQL in this system. There is no code path that accepts a raw SQL
string from a caller:
  * the SELECT expression comes from the metric definition (validated at load time against
    a column allowlist),
  * filter COLUMN names come from a fixed dimension/time map (never from caller input),
  * filter VALUES are always bound parameters (never string-interpolated).

So the surface a caller controls is: which governed metric, which allowed dimensions,
which allowed filters, and the (parameterized) filter values. Nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from semantic_layer.loader import SemanticLayer

SUPPORTED_TIME_GRAIN = "fiscal_year"


class CompileError(Exception):
    """Raised when a request references an unknown/forbidden metric, dimension, or filter."""


@dataclass
class CompiledQuery:
    sql: str
    params: list = field(default_factory=list)


def compile_query(
    sl: SemanticLayer,
    metric_name: str,
    dimensions: list[str] | None = None,
    filters: dict[str, object] | None = None,
    time_grain: str | None = None,
) -> CompiledQuery:
    dimensions = dimensions or []
    filters = filters or {}

    metric = sl.get(metric_name)
    if metric is None:
        raise CompileError(
            f"Unknown metric '{metric_name}'. Governed metrics: {sorted(sl.metrics)}"
        )

    if time_grain not in (None, SUPPORTED_TIME_GRAIN):
        raise CompileError(
            f"Unsupported time_grain '{time_grain}'. Only '{SUPPORTED_TIME_GRAIN}' is governed."
        )

    for d in dimensions:
        if d not in metric.dimensions:
            raise CompileError(
                f"Dimension '{d}' is not allowed for metric '{metric_name}'. "
                f"Allowed: {list(metric.dimensions)}"
            )

    # Resolve a filter/dimension name to its physical column from fixed maps only.
    def column_for(name: str) -> str:
        if name in sl.dimension_columns:
            return sl.dimension_columns[name]
        if name == sl.time_column or name == SUPPORTED_TIME_GRAIN:
            return sl.time_column
        raise CompileError(f"No governed column for '{name}'")

    where_clauses: list[str] = []
    params: list = []
    for fname, fval in filters.items():
        if fname not in metric.filters:
            raise CompileError(
                f"Filter '{fname}' is not allowed for metric '{metric_name}'. "
                f"Allowed: {list(metric.filters)}"
            )
        col = column_for(fname)
        if isinstance(fval, (list, tuple)):
            if not fval:
                raise CompileError(f"Filter '{fname}' got an empty list")
            placeholders = ", ".join(["?"] * len(fval))
            where_clauses.append(f"{col} IN ({placeholders})")
            params.extend(fval)
        else:
            where_clauses.append(f"{col} = ?")
            params.append(fval)

    # Identifying columns are always returned so a value is never ambiguous about which
    # company/year it belongs to.
    select_sql = (
        f"SELECT {sl.dimension_columns['company']} AS ticker, "
        f"{sl.time_column} AS fiscal_year, "
        f"({metric.sql_expression}) AS value"
    )
    sql = f"{select_sql} FROM {sl.source_table}"
    if where_clauses:
        sql += " WHERE " + " AND ".join(where_clauses)
    sql += " ORDER BY ticker, fiscal_year"
    return CompiledQuery(sql=sql, params=params)
