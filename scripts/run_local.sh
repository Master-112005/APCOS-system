#!/usr/bin/env bash
set -euo pipefail

if [[ -d ".venv" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

python -m pytest -q
(cd os && cargo test)

python -m apcos
