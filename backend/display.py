#!/usr/bin/env python3
"""Render CO2, trend, temperature, and humidity on a 320x240 SPI LCD."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import signal
import sys
import time
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont
from co2_trend import (
    CO2_TREND_BASELINE_OFFSET_SECONDS,
    CO2_TREND_BASELINE_WINDOW_SECONDS,
    Co2Trend,
    calculate_co2_trend,
    format_co2_trend_percentage,
)
from db import get_conn, get_state, init_db, latest, range_query
import RPi.GPIO as GPIO
from luma.core.interface.serial import spi
from luma.lcd.device import ili9341


# ILI9341 supports native mode 320x240 in luma.lcd.
# Rotate=1 renders content in portrait orientation on a 240x320 panel.
WIDTH = 320
HEIGHT = 240

COLOR_NORMAL = "#22C55E"   # webapp --accent
COLOR_HIGH = "#FF7B72"     # .co2-high
COLOR_VERY_HIGH = "#FF3B30"  # .co2-very-high
COLOR_TEXT = "#E6EEF8"
COLOR_MUTED = "#94A3B8"
COLOR_DIVIDER = "#8792A2"
BACKGROUND = "#000000"
DISPLAY_BRIGHTNESS = 60
STATE_KEY_DISPLAY_BRIGHTNESS = "display:brightness"
STATE_KEY_NIGHT_MODE_ENABLED = "display:night_mode_enabled"
DEFAULT_NIGHT_MODE_ENABLED = True
NIGHT_MODE_START_HOUR = 22
NIGHT_MODE_END_HOUR = 6
NIGHT_MODE_BRIGHTNESS = 1
DISPLAY_PWM_HZ = 1000
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
SPI_PORT = 0
SPI_DEVICE = 0
ROTATE = 0
DISPLAY_BRIGHTNESS_GPIO = 18
DC_GPIO = 25
RST_GPIO = 27
SECTION_DIVIDER_WIDTH = 2
BOTTOM_LABEL_FONT_SIZE = 14
BOTTOM_SECTION_HEIGHT_RATIO = 3
TOP_LABEL_FONT_SIZE = 14


@dataclass(frozen=True)
class DisplaySnapshot:
    co2: Optional[float]
    temperature: Optional[float]
    humidity: Optional[float]
    trend: Optional[Co2Trend]


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[1]
    default_db = repo_root / "backend" / "data.db"

    parser = argparse.ArgumentParser(
        description="Show CO2 with trend, temperature, and humidity on a Waveshare 2.4 inch SPI display."
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


def trend_color(trend: Optional[Co2Trend]) -> str:
    if trend is None or trend.direction == "neutral":
        return COLOR_MUTED
    if trend.direction == "rising":
        return COLOR_HIGH
    return COLOR_NORMAL


def trend_arrow(trend: Optional[Co2Trend]) -> str:
    if trend is None:
        return "--"
    if trend.direction == "rising":
        return "\u2197"
    if trend.direction == "falling":
        return "\u2198"
    return "\u2192"


def as_float(value: object) -> Optional[float]:
    if value is None:
        return None
    return float(value)


def read_display_snapshot(conn) -> DisplaySnapshot:
    row = latest(conn)
    if not row:
        return DisplaySnapshot(co2=None, temperature=None, humidity=None, trend=None)

    ts_raw = row.get("ts")
    reference_ts = int(ts_raw) if ts_raw is not None else int(time.time())
    trend_start = reference_ts - CO2_TREND_BASELINE_OFFSET_SECONDS - CO2_TREND_BASELINE_WINDOW_SECONDS
    measurements = range_query(conn, trend_start, reference_ts)
    trend = calculate_co2_trend(measurements)

    return DisplaySnapshot(
        co2=as_float(row.get("co2")),
        temperature=as_float(row.get("temperature")),
        humidity=as_float(row.get("humidity")),
        trend=trend,
    )


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


def draw_centered_text(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    color: str,
) -> None:
    x0, y0, x1, y1 = box
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = x0 + ((x1 - x0 + 1 - text_w) // 2) - bbox[0]
    y = y0 + ((y1 - y0 + 1 - text_h) // 2) - bbox[1]
    draw.text((x, y), text, font=font, fill=color)


def draw_metric_box(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    label: str,
    value: str,
    value_color: str,
) -> None:
    x0, y0, x1, y1 = box
    label_font = load_font(BOTTOM_LABEL_FONT_SIZE)
    label_bbox = draw.textbbox((0, 0), label, font=label_font)
    label_w = label_bbox[2] - label_bbox[0]
    label_h = label_bbox[3] - label_bbox[1]
    label_x = x0 + ((x1 - x0 + 1 - label_w) // 2) - label_bbox[0]
    label_y = y0 + 6 - label_bbox[1]
    draw.text((label_x, label_y), label, font=label_font, fill=COLOR_MUTED)

    value_top = label_y + label_h + 6
    value_box = (x0 + 6, value_top, x1 - 6, y1 - 6)
    max_w = max(1, value_box[2] - value_box[0] + 1)
    max_h = max(1, value_box[3] - value_box[1] + 1)
    value_font = best_fit_font(value, max_w, max_h)
    draw_centered_text(draw, value_box, value, value_font, value_color)


def format_temperature(value: Optional[float]) -> str:
    if value is None:
        return "--"
    return f"{value:.1f}\u00B0C"


def format_humidity(value: Optional[float]) -> str:
    if value is None:
        return "--"
    return f"{value:.1f}%"


def format_trend(trend: Optional[Co2Trend]) -> str:
    if trend is None:
        return "--"
    return f"{trend_arrow(trend)} {format_co2_trend_percentage(trend.percentage)}"


def snapshot_signature(snapshot: DisplaySnapshot) -> tuple[object, ...]:
    trend_direction = None if snapshot.trend is None else snapshot.trend.direction
    trend_percentage = None if snapshot.trend is None else round(snapshot.trend.percentage, 1)
    return (
        None if snapshot.co2 is None else int(round(snapshot.co2)),
        None if snapshot.temperature is None else round(snapshot.temperature, 1),
        None if snapshot.humidity is None else round(snapshot.humidity, 1),
        trend_direction,
        trend_percentage,
    )


def make_frame(snapshot: DisplaySnapshot, size: tuple[int, int]) -> Image.Image:
    width, height = size
    value_text = "--" if snapshot.co2 is None else f"{int(round(snapshot.co2))}"
    value_color = co2_color(snapshot.co2)

    img = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(img)

    top_height = (height * (BOTTOM_SECTION_HEIGHT_RATIO - 1)) // BOTTOM_SECTION_HEIGHT_RATIO
    divider_y = top_height
    bottom_y0 = divider_y + SECTION_DIVIDER_WIDTH

    draw.rectangle((0, divider_y, width - 1, bottom_y0 - 1), fill=COLOR_DIVIDER)

    top_label_font = load_font(TOP_LABEL_FONT_SIZE)
    top_label_y = 6
    draw.text((10, top_label_y), "CO2 ppm", font=top_label_font, fill=COLOR_MUTED)
    top_label_bbox = draw.textbbox((10, top_label_y), "CO2 ppm", font=top_label_font)
    top_box = (4, top_label_bbox[3] + 4, width - 5, max(top_label_bbox[3] + 4, divider_y - 5))
    target_w = max(1, top_box[2] - top_box[0] + 1)
    target_h = max(1, top_box[3] - top_box[1] + 1)
    font = best_fit_font(value_text, target_w, target_h)
    draw_centered_text(draw, top_box, value_text, font, value_color)

    first_divider_x = width // 3
    second_divider_x = (2 * width) // 3
    draw.rectangle((first_divider_x, bottom_y0, first_divider_x + SECTION_DIVIDER_WIDTH - 1, height - 1), fill=COLOR_DIVIDER)
    draw.rectangle((second_divider_x, bottom_y0, second_divider_x + SECTION_DIVIDER_WIDTH - 1, height - 1), fill=COLOR_DIVIDER)

    trend_box = (0, bottom_y0, first_divider_x - 1, height - 1)
    temp_box = (first_divider_x + SECTION_DIVIDER_WIDTH, bottom_y0, second_divider_x - 1, height - 1)
    humidity_box = (second_divider_x + SECTION_DIVIDER_WIDTH, bottom_y0, width - 1, height - 1)

    draw_metric_box(draw, trend_box, "Trend", format_trend(snapshot.trend), trend_color(snapshot.trend))
    draw_metric_box(draw, temp_box, "Temp", format_temperature(snapshot.temperature), COLOR_TEXT)
    draw_metric_box(draw, humidity_box, "Hum", format_humidity(snapshot.humidity), COLOR_TEXT)
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

    last_drawn_signature: Optional[tuple[object, ...]] = None
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
                snapshot = read_display_snapshot(conn)
                current_signature = snapshot_signature(snapshot)
                if current_signature != last_drawn_signature:
                    frame = make_frame(snapshot, display_size)
                    display.display(frame)
                    last_drawn_signature = current_signature
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
