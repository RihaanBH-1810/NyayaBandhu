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
export NYAYA_CONSOLIDATION_DIR="$repo_dir/consolidation-data/visual-workspace"

echo "Workspace store: $NYAYA_CONSOLIDATION_DIR"
echo "Review workspace: http://127.0.0.1:8000/admin"
echo "Reader: http://127.0.0.1:8000/library"
echo "Press Ctrl+C to stop the server. This store is reused on the next run."

exec python webui/run.py
