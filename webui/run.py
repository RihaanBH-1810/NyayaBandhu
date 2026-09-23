"""Launch the viewer: ``.venv/Scripts/python webui/run.py``."""
from __future__ import annotations

from pathlib import Path

import uvicorn

REPO_ROOT = Path(__file__).resolve().parent.parent

if __name__ == "__main__":
    uvicorn.run("webui.app:app", host="127.0.0.1", port=8000, app_dir=str(REPO_ROOT))
