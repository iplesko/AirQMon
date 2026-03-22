#!/usr/bin/env python3
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from typing import Optional

from display_control import request_layout_toggle

LAYOUT_BUTTON_GPIO = 24
BUTTON_BOUNCE_MS = 250
BUTTON_SHUTDOWN_HOLD_SECONDS = 5.0
BUTTON_IDLE_POLL_SECONDS = 1.0
BUTTON_HOLD_POLL_SECONDS = 0.1
POWEROFF_CANDIDATE_PATHS = ("/usr/sbin/poweroff", "/sbin/poweroff")
SYSTEMCTL_CANDIDATE_PATHS = ("/usr/bin/systemctl", "/bin/systemctl")


def load_input_runtime():
    import RPi.GPIO as GPIO

    from display_app.button import ButtonEdge, open_gpiochip_event_fd, wait_for_button_edge

    return GPIO, ButtonEdge, open_gpiochip_event_fd, wait_for_button_edge


def _first_existing_path(paths: tuple[str, ...]) -> Optional[str]:
    for path in paths:
        if os.path.exists(path):
            return path
    return None


def resolve_shutdown_command() -> Optional[tuple[str, ...]]:
    poweroff_binary = _first_existing_path(POWEROFF_CANDIDATE_PATHS)
    if poweroff_binary is not None:
        return (poweroff_binary,)

    systemctl_binary = _first_existing_path(SYSTEMCTL_CANDIDATE_PATHS)
    if systemctl_binary is not None:
        return (systemctl_binary, "poweroff")
    return None


def request_system_shutdown(shutdown_command: Optional[tuple[str, ...]]) -> bool:
    if shutdown_command is None:
        print("Input service shutdown is unavailable: no poweroff command was found.", file=sys.stderr)
        return False

    print(
        f"Layout button held for {BUTTON_SHUTDOWN_HOLD_SECONDS:.0f}s; requesting system shutdown.",
        file=sys.stderr,
    )
    try:
        subprocess.run(
            shutdown_command,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        print(f"System shutdown request failed: {exc}", file=sys.stderr)
        return False
    except subprocess.CalledProcessError as exc:
        error_output = (exc.stderr or exc.stdout or str(exc)).strip()
        print(f"System shutdown request failed: {error_output}", file=sys.stderr)
        return False
    return True


def main() -> int:
    try:
        GPIO, ButtonEdge, open_gpiochip_event_fd, wait_for_button_edge = load_input_runtime()
    except Exception as exc:
        print(f"Input runtime init failed: {exc}", file=sys.stderr)
        return 2

    GPIO.setwarnings(False)

    stop = False
    button_event_fd: Optional[int] = None
    last_layout_toggle_at = 0.0
    button_pressed_at: Optional[float] = None
    shutdown_attempted_for_press = False
    shutdown_command = resolve_shutdown_command()

    def _handle_stop(_signum: int, _frame) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)

    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(LAYOUT_BUTTON_GPIO, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        button_event_fd = open_gpiochip_event_fd(LAYOUT_BUTTON_GPIO)
        print("Input button interrupt backend: gpiochip", file=sys.stderr)
    except Exception as exc:
        print(f"Input button init failed: {exc}", file=sys.stderr)
        return 2

    try:
        while not stop:
            wait_timeout = BUTTON_IDLE_POLL_SECONDS
            if button_pressed_at is not None:
                hold_remaining = max(
                    0.0,
                    (button_pressed_at + BUTTON_SHUTDOWN_HOLD_SECONDS) - time.monotonic(),
                )
                wait_timeout = min(wait_timeout, hold_remaining, BUTTON_HOLD_POLL_SECONDS)

            try:
                button_edge = wait_for_button_edge(button_event_fd, wait_timeout)
            except OSError as exc:
                print(f"Input button wait failed: {exc}", file=sys.stderr)
                return 2

            if button_edge is None:
                if button_pressed_at is None or shutdown_attempted_for_press:
                    continue

                if GPIO.input(LAYOUT_BUTTON_GPIO) != GPIO.HIGH:
                    continue

                now = time.monotonic()
                if (now - button_pressed_at) < BUTTON_SHUTDOWN_HOLD_SECONDS:
                    continue

                shutdown_attempted_for_press = True
                if request_system_shutdown(shutdown_command):
                    stop = True
                continue

            now = time.monotonic()
            if button_edge == ButtonEdge.RISING:
                if button_pressed_at is None:
                    button_pressed_at = now
                    shutdown_attempted_for_press = False
                    if (now - last_layout_toggle_at) >= (BUTTON_BOUNCE_MS / 1000.0):
                        last_layout_toggle_at = now
                        if not request_layout_toggle():
                            print("Layout toggle request skipped: display service is unavailable.", file=sys.stderr)
                continue

            if button_edge != ButtonEdge.FALLING or button_pressed_at is None:
                continue

            held_for = now - button_pressed_at
            button_pressed_at = None

            if shutdown_attempted_for_press:
                shutdown_attempted_for_press = False
                continue

            if held_for >= BUTTON_SHUTDOWN_HOLD_SECONDS:
                shutdown_attempted_for_press = True
                if request_system_shutdown(shutdown_command):
                    stop = True
    finally:
        if button_event_fd is not None:
            try:
                os.close(button_event_fd)
            except OSError:
                pass
        try:
            GPIO.cleanup(LAYOUT_BUTTON_GPIO)
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
