#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$repo_dir"

if [[ ! -f .venv/bin/activate ]]; then
  echo "Missing .venv. Create it and install requirements before running this script." >&2
  exit 1
fi

source .venv/bin/activate
export PYTHONPATH="$repo_dir/scripts${PYTHONPATH:+:$PYTHONPATH}"
mkdir -p "$repo_dir/consolidation-data"
export NYAYA_CONSOLIDATION_DIR="$(mktemp -d "$repo_dir/consolidation-data/workspace-XXXXXX")"

echo "Empty workspace store: $NYAYA_CONSOLIDATION_DIR"
echo "Review workspace: http://127.0.0.1:8000/admin"
echo "Reader: http://127.0.0.1:8000/library"
echo "Press Ctrl+C to stop the server. Each run creates a new empty store."

exec python webui/run.py
