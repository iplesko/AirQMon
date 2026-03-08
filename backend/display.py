#!/usr/bin/env python3
"""Render latest CO2 reading as a full-screen value on a 240x320 SPI LCD."""
from __future__ import annotations

import argparse
from datetime import datetime
import signal
import sys
import time
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont
from db import get_conn, get_state, init_db, latest
import RPi.GPIO as GPIO
from luma.core.interface.serial import spi
from luma.lcd.device import ili9341


# ILI9341 supports native mode 320x240 in luma.lcd.
# Rotate=1 renders content in portrait orientation on a 240x320 panel.
WIDTH = 320
HEIGHT = 240

COLOR_NORMAL = "#37B6FF"   # webapp --accent
COLOR_HIGH = "#FF7B72"     # .co2-high
COLOR_VERY_HIGH = "#FF3B30"  # .co2-very-high
BACKGROUND = "#000000"
DISPLAY_BRIGHTNESS = 60
STATE_KEY_DISPLAY_BRIGHTNESS = "display:brightness"
STATE_KEY_NIGHT_MODE_ENABLED = "display:night_mode_enabled"
DEFAULT_NIGHT_MODE_ENABLED = True
NIGHT_MODE_START_HOUR = 22
NIGHT_MODE_END_HOUR = 6
NIGHT_MODE_BRIGHTNESS = 20
DISPLAY_PWM_HZ = 1000
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
SPI_PORT = 0
SPI_DEVICE = 0
ROTATE = 0
DISPLAY_BRIGHTNESS_GPIO = 18
DC_GPIO = 25
RST_GPIO = 27


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[1]
    default_db = repo_root / "backend" / "data.db"

    parser = argparse.ArgumentParser(
        description="Show latest CO2 value on a Waveshare 2.4 inch SPI display."
    )
    parser.add_argument(
        "--db",
        default=str(default_db),
        help="Path to SQLite DB (default: backend/data.db)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=5.0,
        help="Refresh interval in seconds (default: 5.0)",
    )
    return parser.parse_args()


def co2_color(co2: Optional[float]) -> str:
    if co2 is None:
        return COLOR_NORMAL
    if co2 >= 2000:
        return COLOR_VERY_HIGH
    if co2 >= 1000:
        return COLOR_HIGH
    return COLOR_NORMAL


def read_latest_co2(conn) -> Optional[float]:
    row = latest(conn)
    if not row:
        return None
    co2 = row.get("co2")
    if co2 is None:
        return None
    return float(co2)


def read_display_brightness(conn) -> int:
    raw = get_state(conn, STATE_KEY_DISPLAY_BRIGHTNESS, str(DISPLAY_BRIGHTNESS))
    try:
        value = int(raw) if raw is not None else DISPLAY_BRIGHTNESS
    except (TypeError, ValueError):
        return DISPLAY_BRIGHTNESS
    return max(0, min(100, value))


def read_night_mode_enabled(conn) -> bool:
    default = "1" if DEFAULT_NIGHT_MODE_ENABLED else "0"
    return get_state(conn, STATE_KEY_NIGHT_MODE_ENABLED, default).strip() == "1"


def is_night_mode_active() -> bool:
    hour = datetime.now().hour
    if NIGHT_MODE_START_HOUR == NIGHT_MODE_END_HOUR:
        return True
    if NIGHT_MODE_START_HOUR < NIGHT_MODE_END_HOUR:
        return NIGHT_MODE_START_HOUR <= hour < NIGHT_MODE_END_HOUR
    return hour >= NIGHT_MODE_START_HOUR or hour < NIGHT_MODE_END_HOUR


def effective_brightness(configured_brightness: int, night_mode_enabled: bool) -> int:
    night_mode_brightness = max(0, min(100, NIGHT_MODE_BRIGHTNESS))
    if night_mode_enabled and is_night_mode_active():
        return night_mode_brightness
    return configured_brightness


def load_font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_PATH, size=size)


def best_fit_font(text: str, max_w: int, max_h: int) -> ImageFont.FreeTypeFont:
    low = 12
    high = 320
    best = load_font(low)
    while low <= high:
        mid = (low + high) // 2
        font = load_font(mid)
        bbox = font.getbbox(text)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        if w <= max_w and h <= max_h:
            best = font
            low = mid + 1
        else:
            high = mid - 1
    return best


def draw_scaled_fallback_text(
    img: Image.Image,
    text: str,
    color: str,
    max_w: int,
    max_h: int,
) -> None:
    """Draw text with Pillow bitmap font and scale it up when TTF fonts are unavailable."""
    base_font = ImageFont.load_default()
    bbox = base_font.getbbox(text)
    base_w = max(1, bbox[2] - bbox[0])
    base_h = max(1, bbox[3] - bbox[1])
    scale = max(1, min(max_w // base_w, max_h // base_h))

    mask = Image.new("L", (base_w, base_h), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.text((-bbox[0], -bbox[1]), text, font=base_font, fill=255)
    scaled = mask.resize((base_w * scale, base_h * scale), Image.Resampling.NEAREST)

    color_img = Image.new("RGB", scaled.size, color)
    x = (img.width - scaled.width) // 2
    y = (img.height - scaled.height) // 2
    img.paste(color_img, (x, y), scaled)


def make_frame(co2: Optional[float], size: tuple[int, int]) -> Image.Image:
    width, height = size
    value_text = "--" if co2 is None else f"{int(round(co2))}"
    color = co2_color(co2)

    img = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(img)

    # Use almost full panel area while leaving a tiny anti-clip margin.
    target_w = max(1, int(width * 0.995))
    target_h = max(1, int(height * 0.995))
    font = best_fit_font(value_text, target_w, target_h)
    bbox = draw.textbbox((0, 0), value_text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (width - text_w) // 2 - bbox[0]
    y = (height - text_h) // 2 - bbox[1]
    draw.text((x, y), value_text, font=font, fill=color)
    return img


def main() -> int:
    args = parse_args()
    conn = get_conn(args.db)
    init_db(conn)
    GPIO.setwarnings(False)

    try:
        serial = spi(
            port=SPI_PORT,
            device=SPI_DEVICE,
            gpio_DC=DC_GPIO,
            gpio_RST=RST_GPIO,
        )
    except Exception as exc:
        print(f"Failed to initialize SPI display: {exc}", file=sys.stderr)
        conn.close()
        return 2
    display = ili9341(serial, width=WIDTH, height=HEIGHT, rotate=ROTATE)
    display_size = display.size

    display_pwm = None
    configured_brightness = read_display_brightness(conn)
    night_mode_enabled = read_night_mode_enabled(conn)
    active_brightness = effective_brightness(configured_brightness, night_mode_enabled)
    try:
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(DISPLAY_BRIGHTNESS_GPIO, GPIO.OUT)
        display_pwm = GPIO.PWM(DISPLAY_BRIGHTNESS_GPIO, DISPLAY_PWM_HZ)
        display_pwm.start(active_brightness)
    except Exception as exc:
        print(f"Display brightness PWM init failed: {exc}", file=sys.stderr)
        display_pwm = None

    stop = False

    def _handle_stop(_signum: int, _frame) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)

    last_drawn: Optional[int] = None
    try:
        while not stop:
            try:
                configured_brightness = read_display_brightness(conn)
                night_mode_enabled = read_night_mode_enabled(conn)
                latest_brightness = effective_brightness(configured_brightness, night_mode_enabled)
                if latest_brightness != active_brightness and display_pwm is not None:
                    display_pwm.ChangeDutyCycle(latest_brightness)
                    active_brightness = latest_brightness
            except Exception as exc:
                print(f"Display brightness update failed: {exc}", file=sys.stderr)

            try:
                co2 = read_latest_co2(conn)
                rounded = None if co2 is None else int(round(co2))
                if rounded != last_drawn:
                    frame = make_frame(co2, display_size)
                    display.display(frame)
                    last_drawn = rounded
            except Exception as exc:
                err_img = Image.new("RGB", display_size, BACKGROUND)
                err_draw = ImageDraw.Draw(err_img)
                err_font = load_font(22)
                err_draw.text((12, display_size[1] // 2 - 12), "No CO2 data", font=err_font, fill=COLOR_HIGH)
                display.display(err_img)
                print(f"Display update failed: {exc}", file=sys.stderr)

            time.sleep(max(0.2, args.interval))
    finally:
        conn.close()

    if display_pwm is not None:
        try:
            display_pwm.ChangeDutyCycle(0.0)
            display_pwm.stop()
        except Exception:
            pass
    try:
        GPIO.cleanup(DISPLAY_BRIGHTNESS_GPIO)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
