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
  echo "    No .env found; copying from .env.example. Set SEC_USER_AGENT before ingesting."
  cp .env.example .env
fi
set -a; source .env; set +a

echo "==> [4/5] Ingesting SEC EDGAR 10-K facts -> raw.* (DuckDB)"
uv run python -m ingest.fetch_edgar

echo "==> [5/5] Building dbt models (staging -> marts)"
uv run dbt build --project-dir transform --profiles-dir transform

echo "==> Done. Run the demo with:  uv run python -m agent.analyst  (requires ANTHROPIC_API_KEY)"
