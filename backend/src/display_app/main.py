#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import signal
import sys
import time
from typing import Optional

from db import get_conn, init_db
from display_control import DISPLAY_TOGGLE_SIGNAL, remove_display_pid, write_display_pid
from paths import DEFAULT_DB_PATH
from runtime_config import read_display_config

from .data import DisplayModel, build_display_model, read_display_snapshot
from .layouts import STANDARD_LAYOUT, make_error_frame, toggle_layout

# ILI9341 supports native mode 320x240 in luma.lcd.
# Rotate=1 renders content in portrait orientation on a 240x320 panel.
WIDTH = 320
HEIGHT = 240
SPI_PORT = 0
SPI_DEVICE = 0
ROTATE = 0
DISPLAY_BRIGHTNESS_GPIO = 18
DC_GPIO = 25
RST_GPIO = 27
NIGHT_MODE_START_HOUR = 22
NIGHT_MODE_END_HOUR = 6
NIGHT_MODE_BRIGHTNESS = 1
DISPLAY_PWM_HZ = 1000
DISPLAY_IDLE_POLL_SECONDS = 0.1


@dataclass(frozen=True)
class DisplayRefreshResult:
    next_refresh_at: float
    model: Optional[DisplayModel]


def load_display_runtime():
    import RPi.GPIO as GPIO
    from luma.core.interface.serial import spi
    from luma.lcd.device import ili9341

    return GPIO, spi, ili9341


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Show CO2 with trend, temperature, and humidity on a Waveshare 2.4 inch SPI display."
    )
    parser.add_argument(
        "--db",
        default=str(DEFAULT_DB_PATH),
        help="Path to SQLite DB (default: backend/data.db)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=5.0,
        help="Refresh interval in seconds (default: 5.0)",
    )
    return parser.parse_args()


def is_night_mode_active_for_hour(hour: int) -> bool:
    if NIGHT_MODE_START_HOUR == NIGHT_MODE_END_HOUR:
        return True
    if NIGHT_MODE_START_HOUR < NIGHT_MODE_END_HOUR:
        return NIGHT_MODE_START_HOUR <= hour < NIGHT_MODE_END_HOUR
    return hour >= NIGHT_MODE_START_HOUR or hour < NIGHT_MODE_END_HOUR


def is_night_mode_active() -> bool:
    return is_night_mode_active_for_hour(datetime.now().hour)


def effective_brightness(configured_brightness: int, night_mode_enabled: bool) -> int:
    night_mode_brightness = max(0, min(100, NIGHT_MODE_BRIGHTNESS))
    if night_mode_enabled and is_night_mode_active():
        return night_mode_brightness
    return configured_brightness


def update_display_brightness(conn, active_brightness: int, display_pwm):
    display_config = read_display_config(conn)
    latest_brightness = effective_brightness(
        display_config.display_brightness,
        display_config.night_mode_enabled,
    )
    if latest_brightness != active_brightness and display_pwm is not None:
        display_pwm.ChangeDutyCycle(latest_brightness)
        return latest_brightness
    return active_brightness


def refresh_display_model(conn, display, display_size: tuple[int, int], refresh_interval: float, now: float) -> DisplayRefreshResult:
    try:
        return DisplayRefreshResult(
            next_refresh_at=now + refresh_interval,
            model=build_display_model(read_display_snapshot(conn)),
        )
    except Exception as exc:
        display.display(make_error_frame("Data read error", display_size))
        print(f"Display data refresh failed: {exc}", file=sys.stderr)
        return DisplayRefreshResult(next_refresh_at=now + refresh_interval, model=None)


def apply_layout_toggles(current_layout, pending_layout_toggles: int):
    while pending_layout_toggles > 0:
        current_layout = toggle_layout(current_layout)
        pending_layout_toggles -= 1
    return current_layout, pending_layout_toggles


def render_model_if_needed(
    display,
    current_layout,
    latest_model: Optional[DisplayModel],
    display_size: tuple[int, int],
    last_drawn_signature: Optional[tuple[object, ...]],
    refresh_interval: float,
    now: float,
):
    if latest_model is None:
        return last_drawn_signature, None

    try:
        current_signature = (current_layout.name, latest_model)
        if current_signature != last_drawn_signature:
            display.display(current_layout.render(latest_model, display_size))
            last_drawn_signature = current_signature
        return last_drawn_signature, None
    except Exception as exc:
        display.display(make_error_frame("Configuration error", display_size))
        print(f"Display render failed: {exc}", file=sys.stderr)
        return last_drawn_signature, now + refresh_interval


def compute_sleep_until_refresh(next_refresh_at: float, now: float) -> float:
    return min(max(0.0, next_refresh_at - now), DISPLAY_IDLE_POLL_SECONDS)


def main() -> int:
    args = parse_args()
    try:
        GPIO, spi, ili9341 = load_display_runtime()
    except Exception as exc:
        print(f"Display runtime init failed: {exc}", file=sys.stderr)
        return 2

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
    display_config = read_display_config(conn, persist_defaults=True)
    active_brightness = effective_brightness(
        display_config.display_brightness,
        display_config.night_mode_enabled,
    )
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
    exit_code = 0
    current_layout = STANDARD_LAYOUT
    pending_layout_toggles = 0
    refresh_interval = max(0.2, args.interval)

    def _handle_stop(_signum: int, _frame) -> None:
        nonlocal stop
        stop = True

    def _handle_toggle_layout(_signum: int, _frame) -> None:
        nonlocal pending_layout_toggles
        pending_layout_toggles += 1

    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)
    if DISPLAY_TOGGLE_SIGNAL is None:
        print("Display layout toggle signal is unavailable on this platform.", file=sys.stderr)
    else:
        signal.signal(DISPLAY_TOGGLE_SIGNAL, _handle_toggle_layout)

    last_drawn_signature: Optional[tuple[object, ...]] = None
    next_refresh_at = 0.0
    latest_model: Optional[DisplayModel] = None
    try:
        try:
            write_display_pid()
        except OSError as exc:
            print(f"Display control init failed: {exc}", file=sys.stderr)
            exit_code = 2
            stop = True

        while not stop:
            now = time.monotonic()
            should_refresh = now >= next_refresh_at

            try:
                if should_refresh:
                    active_brightness = update_display_brightness(conn, active_brightness, display_pwm)
            except Exception as exc:
                print(f"Display brightness update failed: {exc}", file=sys.stderr)

            if should_refresh:
                refresh_result = refresh_display_model(conn, display, display_size, refresh_interval, now)
                latest_model = refresh_result.model
                next_refresh_at = refresh_result.next_refresh_at

            current_layout, pending_layout_toggles = apply_layout_toggles(
                current_layout,
                pending_layout_toggles,
            )

            last_drawn_signature, render_refresh_at = render_model_if_needed(
                display,
                current_layout,
                latest_model,
                display_size,
                last_drawn_signature,
                refresh_interval,
                now,
            )
            if render_refresh_at is not None:
                next_refresh_at = render_refresh_at

            sleep_until_refresh = compute_sleep_until_refresh(next_refresh_at, time.monotonic())
            if sleep_until_refresh > 0.0:
                try:
                    time.sleep(sleep_until_refresh)
                except InterruptedError:
                    pass
    finally:
        conn.close()
        remove_display_pid()

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
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
