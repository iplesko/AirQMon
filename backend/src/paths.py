from __future__ import annotations

from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SRC_DIR.parent
REPO_ROOT = BACKEND_DIR.parent

ASSETS_DIR = SRC_DIR / "assets"
DEFAULT_DB_PATH = BACKEND_DIR / "data.db"
DISPLAY_PID_FILE = BACKEND_DIR / "airqmon-display.pid"
FRONTEND_DIST_DIR = REPO_ROOT / "frontend" / "dist"
PREVIEW_OUTPUT_DIR = BACKEND_DIR / "preview_out"
