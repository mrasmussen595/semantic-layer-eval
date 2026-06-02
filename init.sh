#!/usr/bin/env bash
# One-shot setup: install uv, sync deps, ingest EDGAR, build dbt, run the demo.
set -euo pipefail
cd "$(dirname "$0")"

echo "==> [1/5] Ensuring uv is installed"
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

echo "==> [2/5] Syncing dependencies (all extras + dev)"
uv sync --all-extras --group dev

echo "==> [3/5] Checking environment"
if [ ! -f .env ]; then
  echo "    No .env found; copying from .env.example."
  cp .env.example .env
fi
set -a; source .env; set +a

# Default to the committed public-domain snapshot so the build is reproducible and offline.
# Set REFRESH_EDGAR=1 to pull fresh facts from live SEC EDGAR (needs SEC_USER_AGENT).
echo "==> [4/5] Loading data -> raw.* (DuckDB)"
if [ "${REFRESH_EDGAR:-0}" = "1" ]; then
  echo "    REFRESH_EDGAR=1 -> pulling live from SEC EDGAR"
  uv run python -m ingest.fetch_edgar
else
  echo "    Using committed snapshot (set REFRESH_EDGAR=1 to fetch live)"
  uv run python -m ingest.load_fixture
fi

echo "==> [5/5] Building dbt models (staging -> marts) + running the governance eval"
uv run dbt build --project-dir transform --profiles-dir transform
uv run python -m eval.harness

echo ""
echo "==> Done. Try the governed agent (no API key needed):"
echo "      uv run python -m agent.reference_agent"
echo "    Or the live Claude agent (needs ANTHROPIC_API_KEY in .env):"
echo "      uv run python -m agent.analyst \"What was Snowflake's total revenue in fiscal 2024?\""
echo "    Eval report: eval/report/eval_report.md"
