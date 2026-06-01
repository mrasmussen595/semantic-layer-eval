"""Shared agent contract: the response type both agents emit, and deterministic helpers
for pulling a company and fiscal year out of a question.

The eval grades AgentResponse objects, so the live Claude agent and the deterministic
reference agent are interchangeable from the harness's point of view.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

CONFIG = Path(__file__).resolve().parent.parent / "config" / "companies.yml"
_YEAR = re.compile(r"\b(20\d{2})\b")
_STOP_SUFFIXES = {"inc", "inc.", "corporation", "holdings", "ltd", "ltd.", "co", "co."}


@dataclass
class AgentResponse:
    question: str
    refused: bool
    value: float | None = None
    metric: str | None = None
    company: str | None = None
    fiscal_year: int | None = None
    text: str = ""
    tool_trace: list[dict] = field(default_factory=list)


def _company_keywords() -> dict[str, str]:
    """keyword -> ticker. Keyword is the ticker and the distinctive first word of the name."""
    with open(CONFIG) as f:
        companies = yaml.safe_load(f)["companies"]
    out: dict[str, str] = {}
    for c in companies:
        ticker = c["ticker"]
        out[ticker.lower()] = ticker
        first = c["name"].split()[0].strip(",.").lower()
        if first not in _STOP_SUFFIXES:
            out[first] = ticker
    return out


COMPANY_KEYWORDS = _company_keywords()


def extract_company(text: str) -> str | None:
    """Return the single ticker named in the text, or None if zero or more than one."""
    t = text.lower()
    found = {
        ticker
        for kw, ticker in COMPANY_KEYWORDS.items()
        if re.search(rf"(?<!\w){re.escape(kw)}(?!\w)", t)
    }
    return next(iter(found)) if len(found) == 1 else None


def extract_fiscal_year(text: str) -> int | None:
    m = _YEAR.search(text)
    return int(m.group(1)) if m else None
