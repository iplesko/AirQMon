#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
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


@dataclass
class InputLoopState:
    stop: bool = False
    last_layout_toggle_at: float = 0.0
    button_pressed_at: Optional[float] = None
    shutdown_attempted_for_press: bool = False


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


def compute_wait_timeout(state: InputLoopState, now: float) -> float:
    wait_timeout = BUTTON_IDLE_POLL_SECONDS
    if state.button_pressed_at is None:
        return wait_timeout

    hold_remaining = max(
        0.0,
        (state.button_pressed_at + BUTTON_SHUTDOWN_HOLD_SECONDS) - now,
    )
    return min(wait_timeout, hold_remaining, BUTTON_HOLD_POLL_SECONDS)


def handle_no_button_edge(
    state: InputLoopState,
    *,
    now: float,
    button_is_high: bool,
    shutdown_command: Optional[tuple[str, ...]],
    request_shutdown=request_system_shutdown,
) -> None:
    if state.button_pressed_at is None or state.shutdown_attempted_for_press:
        return
    if not button_is_high:
        return
    if (now - state.button_pressed_at) < BUTTON_SHUTDOWN_HOLD_SECONDS:
        return

    state.shutdown_attempted_for_press = True
    if request_shutdown(shutdown_command):
        state.stop = True


def handle_button_edge_event(
    state: InputLoopState,
    button_edge,
    *,
    now: float,
    rising_edge,
    falling_edge,
    shutdown_command: Optional[tuple[str, ...]],
    request_layout=request_layout_toggle,
    request_shutdown=request_system_shutdown,
) -> None:
    if button_edge == rising_edge:
        if state.button_pressed_at is None:
            state.button_pressed_at = now
            state.shutdown_attempted_for_press = False
            if (now - state.last_layout_toggle_at) >= (BUTTON_BOUNCE_MS / 1000.0):
                state.last_layout_toggle_at = now
                if not request_layout():
                    print("Layout toggle request skipped: display service is unavailable.", file=sys.stderr)
        return

    if button_edge != falling_edge or state.button_pressed_at is None:
        return

    held_for = now - state.button_pressed_at
    state.button_pressed_at = None

    if state.shutdown_attempted_for_press:
        state.shutdown_attempted_for_press = False
        return

    if held_for >= BUTTON_SHUTDOWN_HOLD_SECONDS:
        state.shutdown_attempted_for_press = True
        if request_shutdown(shutdown_command):
            state.stop = True


def main() -> int:
    try:
        GPIO, ButtonEdge, open_gpiochip_event_fd, wait_for_button_edge = load_input_runtime()
    except Exception as exc:
        print(f"Input runtime init failed: {exc}", file=sys.stderr)
        return 2

    GPIO.setwarnings(False)

    state = InputLoopState()
    button_event_fd: Optional[int] = None
    shutdown_command = resolve_shutdown_command()

    def _handle_stop(_signum: int, _frame) -> None:
        state.stop = True

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
        while not state.stop:
            wait_timeout = compute_wait_timeout(state, time.monotonic())

            try:
                button_edge = wait_for_button_edge(button_event_fd, wait_timeout)
            except OSError as exc:
                print(f"Input button wait failed: {exc}", file=sys.stderr)
                return 2

            if button_edge is None:
                handle_no_button_edge(
                    state,
                    now=time.monotonic(),
                    button_is_high=GPIO.input(LAYOUT_BUTTON_GPIO) == GPIO.HIGH,
                    shutdown_command=shutdown_command,
                )
                continue

            handle_button_edge_event(
                state,
                button_edge,
                now=time.monotonic(),
                rising_edge=ButtonEdge.RISING,
                falling_edge=ButtonEdge.FALLING,
                shutdown_command=shutdown_command,
            )
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
