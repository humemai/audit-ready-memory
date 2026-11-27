#!/usr/bin/env bash
# Set up from a clean clone and check what the documentation claims: tests, benchmarks, examples.
#
#   git clone https://github.com/humemai/audit-ready-memory
#   cd audit-ready-memory && bash scripts/verify.sh
set -euo pipefail
cd "$(dirname "$0")/.."

command -v uv >/dev/null || {
    echo "uv is needed first: https://docs.astral.sh/uv/getting-started/installation/" >&2
    exit 1
}

echo "== set up"
uv sync --locked --all-extras
echo "== tests"
uv run pytest -q
echo "== benchmark set"
uv run python -m benchmarks.run
echo "== examples"
for example in examples/*.py; do
    echo "-- $example"
    uv run python "$example"
done
echo "== all checks passed in ${SECONDS} s"
