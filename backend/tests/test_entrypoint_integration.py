from __future__ import annotations

import importlib
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import alerter
import collector
import display_control
from db import get_conn, init_db, insert_measurement, latest
from push_notifications import PushDeliveryStats
import input as input_service

display_main = importlib.import_module("display_app.main")


def test_collector_main_runs_one_iteration_and_writes_measurement(
    monkeypatch, db_path: Path, capsys
) -> None:
    original_collect_once = collector.collect_once

    monkeypatch.setattr(
        collector,
        "parse_args",
        lambda: Namespace(db=str(db_path), interval=0.5),
    )
    monkeypatch.setattr(collector.signal, "signal", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(collector, "running", True)

    def single_iteration(conn, last_prune):
        result = original_collect_once(
            conn,
            last_prune=123_456,
            ts=123_456,
            read_sensor=lambda: (850.0, 22.1, 44.2),
        )
        collector.running = False
        return result

    monkeypatch.setattr(collector, "collect_once", single_iteration)

    assert collector.main() is None

    captured = capsys.readouterr()
    check_conn = get_conn(str(db_path))
    try:
        row = latest(check_conn)
    finally:
        check_conn.close()

    assert row is not None
    assert row["ts"] == 123_456
    assert row["co2"] == 850.0
    assert "Starting collector, writing to" in captured.out
    assert "Collector stopped" in captured.out


def test_alerter_main_processes_existing_measurement_and_persists_state(
    monkeypatch, db_path: Path, capsys
) -> None:
    setup_conn = get_conn(str(db_path))
    init_db(setup_conn)
    row_id = insert_measurement(setup_conn, 200_000, 2000.0, 24.0, 45.0)
    setup_conn.close()

    original_process_row = alerter.process_row

    monkeypatch.setattr(
        alerter,
        "parse_args",
        lambda: Namespace(db=str(db_path), poll_interval=0.0),
    )
    monkeypatch.setattr(alerter.signal, "signal", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(alerter, "running", True)
    monkeypatch.setattr(
        alerter,
        "get_vapid_credentials",
        lambda: ("private-key.pem", {"sub": "mailto:test@example.com"}),
    )
    monkeypatch.setattr(
        alerter,
        "send_push_to_all",
        lambda *_args, **_kwargs: PushDeliveryStats(attempted=1, sent=1, removed=0),
    )

    def single_iteration(*args, **kwargs):
        original_process_row(*args, **kwargs)
        alerter.running = False

    monkeypatch.setattr(alerter, "process_row", single_iteration)

    assert alerter.main() is None

    captured = capsys.readouterr()
    check_conn = get_conn(str(db_path))
    try:
        state = alerter.load_runtime_state(check_conn)
    finally:
        check_conn.close()

    assert state.last_seen_id == row_id
    assert state.in_alert is True
    assert state.last_alert_ts == 200_000
    assert '"event": "alerter_started"' in captured.out
    assert "Alerter stopped" in captured.out


def test_input_main_happy_path_handles_layout_toggle_and_shutdown(monkeypatch, capsys) -> None:
    signal_handlers: dict[object, object] = {}
    kill_calls: list[tuple[int, int]] = []
    close_calls: list[int] = []

    class FakeGPIO:
        BCM = "BCM"
        IN = "IN"
        PUD_DOWN = "PUD_DOWN"
        HIGH = 1

        def __init__(self):
            self.setup_calls: list[tuple[object, object, object]] = []
            self.cleanup_calls: list[object] = []

        def setwarnings(self, _value):
            return None

        def setmode(self, _mode):
            return None

        def setup(self, gpio, mode, pull_up_down=None):
            self.setup_calls.append((gpio, mode, pull_up_down))

        def input(self, _gpio):
            return self.HIGH

        def cleanup(self, gpio):
            self.cleanup_calls.append(gpio)

    class FakeButtonEdge:
        RISING = "rising"
        FALLING = "falling"

    fake_gpio = FakeGPIO()
    button_events = iter([FakeButtonEdge.RISING, None])
    monotonic_values = iter([10.0, 10.0, 15.0, 15.0])

    def fake_monotonic():
        try:
            return next(monotonic_values)
        except StopIteration:
            return 15.0

    monkeypatch.setattr(
        input_service,
        "load_input_runtime",
        lambda: (
            fake_gpio,
            FakeButtonEdge,
            lambda _gpio: 55,
            lambda _fd, _timeout: next(button_events),
        ),
    )
    monkeypatch.setattr(input_service, "resolve_shutdown_command", lambda: ("/usr/sbin/poweroff",))
    monkeypatch.setattr(input_service.signal, "signal", lambda sig, handler: signal_handlers.__setitem__(sig, handler))
    monkeypatch.setattr(input_service.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(input_service.subprocess, "run", lambda *args, **kwargs: None)
    monkeypatch.setattr(input_service.os, "close", lambda fd: close_calls.append(fd))

    monkeypatch.setattr(display_control, "DISPLAY_TOGGLE_SIGNAL", 10)
    monkeypatch.setattr(display_control, "read_display_pid", lambda *_args, **_kwargs: 4321)
    monkeypatch.setattr(display_control, "_pid_matches_display", lambda _pid: True)
    monkeypatch.setattr(display_control.os, "kill", lambda pid, sig: kill_calls.append((pid, sig)))

    assert input_service.main() == 0

    captured = capsys.readouterr()

    assert fake_gpio.setup_calls == [(input_service.LAYOUT_BUTTON_GPIO, fake_gpio.IN, fake_gpio.PUD_DOWN)]
    assert fake_gpio.cleanup_calls == [input_service.LAYOUT_BUTTON_GPIO]
    assert close_calls == [55]
    assert kill_calls == [(4321, 10)]
    assert "Input button interrupt backend: gpiochip" in captured.err
    assert "requesting system shutdown" in captured.err


def test_display_main_happy_path_refreshes_renders_and_cleans_up(monkeypatch, capsys) -> None:
    signal_handlers: dict[object, object] = {}
    write_calls: list[str] = []
    remove_calls: list[str] = []
    rendered_frames: list[object] = []
    monotonic_values = iter([0.0, 0.0, 0.0])

    class FakeConn:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    class FakePWM:
        def __init__(self):
            self.started: list[int] = []
            self.changed: list[float] = []
            self.stopped = False

        def start(self, value):
            self.started.append(value)

        def ChangeDutyCycle(self, value):
            self.changed.append(value)

        def stop(self):
            self.stopped = True

    class FakeGPIO:
        BCM = "BCM"
        OUT = "OUT"

        def __init__(self):
            self.cleanup_calls: list[object] = []
            self.pwm = FakePWM()

        def setwarnings(self, _value):
            return None

        def setmode(self, _mode):
            return None

        def setup(self, *_args, **_kwargs):
            return None

        def PWM(self, *_args, **_kwargs):
            return self.pwm

        def cleanup(self, gpio):
            self.cleanup_calls.append(gpio)

    class FakeDisplay:
        size = (320, 240)

        def display(self, frame):
            rendered_frames.append(frame)
            signal_handlers[display_main.signal.SIGINT](None, None)

    class FakeLayout:
        def __init__(self, name: str):
            self.name = name

        def render(self, model, size):
            return (self.name, model, size)

    fake_conn = FakeConn()
    fake_gpio = FakeGPIO()
    fake_display = FakeDisplay()
    standard_layout = FakeLayout("standard")
    faces_layout = FakeLayout("faces")
    config_calls = iter(
        [
            SimpleNamespace(display_brightness=60, night_mode_enabled=False),
            SimpleNamespace(display_brightness=30, night_mode_enabled=False),
        ]
    )
    toggled = {"done": False}

    def fake_monotonic():
        try:
            return next(monotonic_values)
        except StopIteration:
            return 0.0

    def fake_signal(sig, handler):
        signal_handlers[sig] = handler

    def fake_read_display_config(_conn, persist_defaults=False):
        if persist_defaults:
            return next(config_calls)
        return next(config_calls)

    def fake_read_display_snapshot(_conn):
        if not toggled["done"] and display_main.DISPLAY_TOGGLE_SIGNAL in signal_handlers:
            toggled["done"] = True
            signal_handlers[display_main.DISPLAY_TOGGLE_SIGNAL](None, None)
        return "snapshot"

    monkeypatch.setattr(display_main, "parse_args", lambda: Namespace(db="ignored.db", interval=0.5))
    monkeypatch.setattr(display_main, "get_conn", lambda _path: fake_conn)
    monkeypatch.setattr(display_main, "init_db", lambda _conn: None)
    monkeypatch.setattr(display_main, "read_display_config", fake_read_display_config)
    monkeypatch.setattr(display_main, "read_display_snapshot", fake_read_display_snapshot)
    monkeypatch.setattr(display_main, "build_display_model", lambda _snapshot: "model")
    monkeypatch.setattr(display_main, "STANDARD_LAYOUT", standard_layout)
    monkeypatch.setattr(display_main, "toggle_layout", lambda _layout: faces_layout)
    monkeypatch.setattr(display_main, "write_display_pid", lambda: write_calls.append("write"))
    monkeypatch.setattr(display_main, "remove_display_pid", lambda: remove_calls.append("remove"))
    monkeypatch.setattr(display_main.signal, "signal", fake_signal)
    monkeypatch.setattr(display_main.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(display_main.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(display_main, "DISPLAY_TOGGLE_SIGNAL", 10)
    monkeypatch.setattr(
        display_main,
        "load_display_runtime",
        lambda: (
            fake_gpio,
            lambda **_kwargs: "serial",
            lambda serial, width, height, rotate: fake_display,
        ),
    )

    assert display_main.main() == 0

    captured = capsys.readouterr()

    assert write_calls == ["write"]
    assert remove_calls == ["remove"]
    assert fake_conn.closed is True
    assert fake_gpio.pwm.started == [60]
    assert fake_gpio.pwm.changed == [30, 0.0]
    assert fake_gpio.pwm.stopped is True
    assert fake_gpio.cleanup_calls == [display_main.DISPLAY_BRIGHTNESS_GPIO]
    assert rendered_frames == [("faces", "model", fake_display.size)]
    assert captured.err == ""
