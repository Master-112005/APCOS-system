#!/usr/bin/env bash
set -euo pipefail

if [[ -d ".venv" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

python -m pytest -q
(cd os && cargo build && cargo test && cargo clippy -- -D warnings)

mkdir -p dist
tar -czf dist/apcos-rc.tar.gz \
  apcos core interface os services tests voice configs docs scripts models \
  README.md ARCHITECTURE.md ROADMAP.md SECURITY.md CHANGELOG.md LICENSE CONTRIBUTING.md \
  pyproject.toml requirements.txt requirements-dev.txt .env.example

echo "Release package written to dist/apcos-rc.tar.gz"
