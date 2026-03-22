#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from display_app.assets import BACKEND_DIR, EMOJI_FONT_PATH, TEXT_FONT_PATH

BASE_DIR = BACKEND_DIR
OUTPUT_DIR = BASE_DIR / "preview_out"
WIDTH = 320
HEIGHT = 240
LAYOUT_STANDARD = "standard"
LAYOUT_FACES = "faces"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render the display layouts to PNG files using fake readings.")
    parser.add_argument("--co2", type=float, required=True, help="CO2 value in ppm.")
    parser.add_argument("--temperature", type=float, required=True, help="Temperature value in deg C.")
    parser.add_argument("--humidity", type=float, required=True, help="Humidity value in percent.")
    parser.add_argument(
        "--trend",
        type=float,
        default=0.0,
        help="Trend percentage. Positive means rising, negative means falling, zero means neutral.",
    )
    return parser.parse_args()


def load_runtime():
    try:
        from display_app import faces_layout, layout_common
        from display_app.data import DisplaySnapshot, build_display_model
        from display_app.layouts import FACES_LAYOUT, STANDARD_LAYOUT
    except ModuleNotFoundError as exc:
        if exc.name == "PIL":
            raise RuntimeError(
                "Missing Python dependency: Pillow. Install backend requirements first, for example:\n"
                "  .\\venv\\Scripts\\python.exe -m pip install -r requirements.txt"
            ) from exc
        raise

    return faces_layout, layout_common, DisplaySnapshot, build_display_model, STANDARD_LAYOUT, FACES_LAYOUT


def configure_fonts(faces_layout, layout_common) -> None:
    if not Path(TEXT_FONT_PATH).exists():
        raise FileNotFoundError(f"Missing bundled text font: {TEXT_FONT_PATH}")
    if not Path(EMOJI_FONT_PATH).exists():
        raise FileNotFoundError(f"Missing bundled emoji font: {EMOJI_FONT_PATH}")

    layout_common.FONT_PATH = TEXT_FONT_PATH
    faces_layout.EMOJI_FONT_PATH = EMOJI_FONT_PATH
    faces_layout.load_emoji_font.cache_clear()
    faces_layout.best_fit_emoji_font.cache_clear()
    faces_layout.render_face_icon.cache_clear()


def build_preview_trend(percentage: float):
    from co2_trend import Co2Trend

    if percentage > 0:
        direction = "rising"
    elif percentage < 0:
        direction = "falling"
    else:
        direction = "neutral"

    baseline_average = 1000.0
    recent_average = baseline_average * (1.0 + (percentage / 100.0))
    return Co2Trend(
        direction=direction,
        percentage=0.0 if direction == "neutral" else percentage,
        raw_percentage=percentage,
        recent_average=recent_average,
        baseline_average=baseline_average,
        reference_ts=int(time.time()),
    )


def main() -> int:
    args = parse_args()

    try:
        (
            faces_layout,
            layout_common,
            display_snapshot_cls,
            build_display_model,
            standard_layout,
            faces_layout_instance,
        ) = load_runtime()
        configure_fonts(faces_layout, layout_common)

        snapshot = display_snapshot_cls(
            co2=args.co2,
            temperature=args.temperature,
            humidity=args.humidity,
            trend=build_preview_trend(args.trend),
        )
        model = build_display_model(snapshot)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        for layout_name, layout in (
            (LAYOUT_STANDARD, standard_layout),
            (LAYOUT_FACES, faces_layout_instance),
        ):
            output_path = OUTPUT_DIR / f"display-preview-{layout_name}.png"
            layout.render(model, (WIDTH, HEIGHT)).save(output_path)
            print(output_path)
    except Exception as exc:
        print(f"Preview render failed: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
