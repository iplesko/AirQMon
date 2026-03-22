from __future__ import annotations

from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BACKEND_DIR / "assets"
TEXT_FONT_PATH = str(ASSETS_DIR / "DejaVuSans-Bold.ttf")
EMOJI_FONT_PATH = str(ASSETS_DIR / "NotoEmoji-Regular.ttf")
