#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime
import os
import signal
import sys
import time
from pathlib import Path
from typing import Optional

import RPi.GPIO as GPIO
from luma.core.interface.serial import spi
from luma.lcd.device import ili9341

from db import get_conn, init_db
from runtime_config import read_display_config

from .button import open_gpiochip_event_fd, wait_for_rising_edge
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
LAYOUT_BUTTON_GPIO = 24
BUTTON_BOUNCE_MS = 250
NIGHT_MODE_START_HOUR = 22
NIGHT_MODE_END_HOUR = 6
NIGHT_MODE_BRIGHTNESS = 1
DISPLAY_PWM_HZ = 1000


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[2]
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
    button_event_fd: Optional[int] = None
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
    current_layout = STANDARD_LAYOUT
    last_layout_toggle_at = 0.0
    refresh_interval = max(0.2, args.interval)

    def _handle_stop(_signum: int, _frame) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)

    try:
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(LAYOUT_BUTTON_GPIO, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        button_event_fd = open_gpiochip_event_fd(LAYOUT_BUTTON_GPIO)
        print("Layout button interrupt backend: gpiochip", file=sys.stderr)
    except Exception as exc:
        print(f"Layout button init failed: {exc}", file=sys.stderr)

    last_drawn_signature: Optional[tuple[object, ...]] = None
    next_refresh_at = 0.0
    latest_model: Optional[DisplayModel] = None
    try:
        while not stop:
            now = time.monotonic()
            should_refresh = now >= next_refresh_at

            try:
                if should_refresh:
                    display_config = read_display_config(conn)
                    latest_brightness = effective_brightness(
                        display_config.display_brightness,
                        display_config.night_mode_enabled,
                    )
                    if latest_brightness != active_brightness and display_pwm is not None:
                        display_pwm.ChangeDutyCycle(latest_brightness)
                        active_brightness = latest_brightness
            except Exception as exc:
                print(f"Display brightness update failed: {exc}", file=sys.stderr)

            try:
                if should_refresh:
                    latest_model = build_display_model(read_display_snapshot(conn))
                    next_refresh_at = now + refresh_interval
                if latest_model is not None:
                    current_signature = (current_layout.name, latest_model)
                    if current_signature != last_drawn_signature:
                        display.display(current_layout.render(latest_model, display_size))
                        last_drawn_signature = current_signature
            except Exception as exc:
                display.display(make_error_frame("No CO2 data", display_size))
                print(f"Display update failed: {exc}", file=sys.stderr)
                next_refresh_at = now + refresh_interval

            sleep_until_refresh = max(0.0, next_refresh_at - time.monotonic())
            if button_event_fd is None:
                time.sleep(sleep_until_refresh)
                continue

            try:
                button_pressed = wait_for_rising_edge(button_event_fd, sleep_until_refresh)
            except OSError as exc:
                print(f"Layout button wait failed: {exc}", file=sys.stderr)
                os.close(button_event_fd)
                button_event_fd = None
                continue

            if not button_pressed:
                continue

            now = time.monotonic()
            if (now - last_layout_toggle_at) >= (BUTTON_BOUNCE_MS / 1000.0):
                current_layout = toggle_layout(current_layout)
                last_layout_toggle_at = now
    finally:
        conn.close()

    if button_event_fd is not None:
        try:
            os.close(button_event_fd)
        except OSError:
            pass
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
    try:
        GPIO.cleanup(LAYOUT_BUTTON_GPIO)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
