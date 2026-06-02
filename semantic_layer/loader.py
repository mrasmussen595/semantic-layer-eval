"""Load, validate, and resolve against the governed semantic layer (metrics.yml).

Responsibilities:
  * Parse metrics.yml into typed Metric objects.
  * Validate each sql_expression references ONLY allowlisted mart columns (a real
    boundary check; a typo or an attempt to reference another table is a load error).
  * Resolve free-text terms to metric(s) with longest-phrase precedence, returning a
    RESOLVED / AMBIGUOUS / OUT_OF_SCOPE result. This is what lets the agent refuse
    instead of guessing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import yaml

METRICS_PATH = Path(__file__).resolve().parent / "metrics.yml"
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


@dataclass(frozen=True)
class Metric:
    name: str
    label: str
    description: str
    synonyms: tuple[str, ...]
    sql_expression: str
    format: str
    grain: str
    dimensions: tuple[str, ...]
    filters: tuple[str, ...]
    owner: str


class Resolution(str, Enum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    OUT_OF_SCOPE = "out_of_scope"


@dataclass
class ResolutionResult:
    status: Resolution
    metrics: list[str] = field(default_factory=list)
    message: str = ""


class SemanticLayerError(Exception):
    """Raised when metrics.yml is malformed or violates the column allowlist."""


@dataclass
class SemanticLayer:
    source_table: str
    grain: str
    allowed_columns: frozenset[str]
    dimension_columns: dict[str, str]
    time_column: str
    metrics: dict[str, Metric]
    _synonym_index: dict[str, frozenset[str]]
    _out_of_scope_phrases: tuple[str, ...]

    # ---- loading -------------------------------------------------------------
    @classmethod
    def load(cls, path: Path = METRICS_PATH) -> SemanticLayer:
        with open(path) as f:
            raw = yaml.safe_load(f)

        allowed = frozenset(raw["allowed_columns"])
        dim_cols = {k: v["column"] for k, v in raw["dimensions"].items()}
        time_col = raw["time"]["column"]

        metrics: dict[str, Metric] = {}
        synonym_index: dict[str, set[str]] = {}
        for m in raw["metrics"]:
            expr = " ".join(str(m["sql_expression"]).split())
            cls._validate_expression(m["name"], expr, allowed)
            metric = Metric(
                name=m["name"],
                label=m["label"],
                description=" ".join(str(m["description"]).split()),
                synonyms=tuple(s.lower() for s in m.get("synonyms", [])),
                sql_expression=expr,
                format=m.get("format", "number"),
                grain=m["grain"],
                dimensions=tuple(m.get("dimensions", [])),
                filters=tuple(m.get("filters", [])),
                owner=m.get("owner", raw.get("owner_default", "")),
            )
            if metric.name in metrics:
                raise SemanticLayerError(f"Duplicate metric name: {metric.name}")
            metrics[metric.name] = metric
            for syn in (metric.name, *metric.synonyms):
                synonym_index.setdefault(syn.lower(), set()).add(metric.name)

        return cls(
            source_table=raw["source_table"],
            grain=raw["grain"],
            allowed_columns=allowed,
            dimension_columns=dim_cols,
            time_column=time_col,
            metrics=metrics,
            _synonym_index={k: frozenset(v) for k, v in synonym_index.items()},
            _out_of_scope_phrases=tuple(
                phrase.lower() for phrase in raw.get("out_of_scope_phrases", [])
            ),
        )

    @staticmethod
    def _validate_expression(name: str, expr: str, allowed: frozenset[str]) -> None:
        idents = set(_IDENTIFIER.findall(expr))
        unknown = idents - allowed
        if unknown:
            raise SemanticLayerError(
                f"Metric '{name}' references columns not in the allowlist: "
                f"{sorted(unknown)}. Allowed: {sorted(allowed)}"
            )

    # ---- access --------------------------------------------------------------
    def list_metrics(self) -> list[Metric]:
        return list(self.metrics.values())

    def get(self, name: str) -> Metric | None:
        return self.metrics.get(name)

    # ---- resolution ----------------------------------------------------------
    def resolve(self, text: str) -> ResolutionResult:
        """Map free text to governed metric(s).

        Longest-phrase precedence: a multi-word synonym ("gross margin") wins over the
        single word it contains ("margin"), so specific asks resolve while bare ambiguous
        terms surface every candidate for clarification.
        """
        t = text.lower()
        if any(self._phrase_present(phrase, t) for phrase in self._out_of_scope_phrases):
            return ResolutionResult(
                Resolution.OUT_OF_SCOPE,
                message=(
                    "No governed metric matches this request. Governed metrics: "
                    + ", ".join(sorted(self.metrics))
                ),
            )
        matched: list[tuple[str, frozenset[str], frozenset[str]]] = []
        for syn, metric_names in self._synonym_index.items():
            if self._phrase_present(syn, t):
                matched.append((syn, frozenset(syn.split()), metric_names))

        if not matched:
            return ResolutionResult(
                Resolution.OUT_OF_SCOPE,
                message=(
                    "No governed metric matches this request. Governed metrics: "
                    + ", ".join(sorted(self.metrics))
                ),
            )

        # Drop shorter synonyms only when every occurrence is contained in a longer
        # matched phrase. A separately requested shorter metric must survive.
        maximal = [
            (tokens, names)
            for syn, tokens, names in matched
            if self._phrase_has_uncovered_occurrence(
                syn,
                [other_syn for other_syn, other, _ in matched if tokens < other],
                t,
            )
        ]
        specific = sorted(
            {n for tokens, names in maximal if len(names) == 1 for n in names}
        )
        candidates = specific or sorted({n for _, names in maximal for n in names})

        if len(candidates) == 1:
            return ResolutionResult(Resolution.RESOLVED, metrics=candidates)
        return ResolutionResult(
            Resolution.AMBIGUOUS,
            metrics=candidates,
            message=(
                "Request is ambiguous between governed metrics: "
                + ", ".join(candidates)
                + ". Ask which one (and over what fiscal year)."
            ),
        )

    @staticmethod
    def _phrase_present(phrase: str, text: str) -> bool:
        return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text) is not None

    @staticmethod
    def _phrase_has_uncovered_occurrence(
        phrase: str, covering_phrases: list[str], text: str
    ) -> bool:
        pattern = rf"(?<!\w){re.escape(phrase)}(?!\w)"
        covering_spans = [
            match.span()
            for covering in covering_phrases
            for match in re.finditer(rf"(?<!\w){re.escape(covering)}(?!\w)", text)
        ]
        return any(
            not any(
                cover_start <= start and end <= cover_end
                for cover_start, cover_end in covering_spans
            )
            for start, end in (match.span() for match in re.finditer(pattern, text))
        )
