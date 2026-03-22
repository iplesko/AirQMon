from __future__ import annotations

import importlib
from argparse import Namespace
from types import SimpleNamespace

import pytest

display_main = importlib.import_module("display_app.main")


def test_is_night_mode_active_for_hour_handles_wrapping_window() -> None:
    assert display_main.is_night_mode_active_for_hour(23) is True
    assert display_main.is_night_mode_active_for_hour(3) is True
    assert display_main.is_night_mode_active_for_hour(12) is False


def test_is_night_mode_active_for_hour_handles_same_start_and_end(monkeypatch) -> None:
    monkeypatch.setattr(display_main, "NIGHT_MODE_START_HOUR", 6)
    monkeypatch.setattr(display_main, "NIGHT_MODE_END_HOUR", 6)

    assert display_main.is_night_mode_active_for_hour(0) is True
    assert display_main.is_night_mode_active_for_hour(12) is True


def test_effective_brightness_uses_night_mode_when_active(monkeypatch) -> None:
    monkeypatch.setattr(display_main, "NIGHT_MODE_BRIGHTNESS", 150)
    monkeypatch.setattr(display_main, "is_night_mode_active", lambda: True)

    assert display_main.effective_brightness(60, True) == 100
    assert display_main.effective_brightness(60, False) == 60


def test_main_returns_2_when_runtime_dependencies_cannot_load(monkeypatch, capsys) -> None:
    monkeypatch.setattr(display_main, "parse_args", lambda: Namespace(db="ignored.db", interval=5.0))

    def fail_runtime():
        raise ModuleNotFoundError("No module named 'RPi'")

    monkeypatch.setattr(display_main, "load_display_runtime", fail_runtime)

    assert display_main.main() == 2
    assert "Display runtime init failed" in capsys.readouterr().err


def test_main_returns_2_when_spi_initialization_fails(monkeypatch, capsys, test_tmp_dir) -> None:
    fake_conn = type(
        "FakeConn",
        (),
        {
            "__init__": lambda self: setattr(self, "closed", False),
            "close": lambda self: setattr(self, "closed", True),
        },
    )()
    fake_gpio = type(
        "FakeGPIO",
        (),
        {
            "setwarnings": lambda self, _value: None,
        },
    )()

    monkeypatch.setattr(
        display_main,
        "parse_args",
        lambda: Namespace(db=str(test_tmp_dir / "display.db"), interval=5.0),
    )
    monkeypatch.setattr(display_main, "get_conn", lambda _path: fake_conn)
    monkeypatch.setattr(display_main, "init_db", lambda _conn: None)
    monkeypatch.setattr(
        display_main,
        "load_display_runtime",
        lambda: (
            fake_gpio,
            lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("spi unavailable")),
            object,
        ),
    )

    assert display_main.main() == 2
    assert fake_conn.closed is True
    assert "Failed to initialize SPI display: spi unavailable" in capsys.readouterr().err


def test_update_display_brightness_changes_pwm_when_value_changes(monkeypatch) -> None:
    pwm_calls: list[int] = []
    pwm = SimpleNamespace(ChangeDutyCycle=lambda value: pwm_calls.append(value))

    monkeypatch.setattr(
        display_main,
        "read_display_config",
        lambda _conn: SimpleNamespace(display_brightness=30, night_mode_enabled=False),
    )
    monkeypatch.setattr(display_main, "effective_brightness", lambda brightness, _night: brightness)

    result = display_main.update_display_brightness("conn", active_brightness=60, display_pwm=pwm)

    assert result == 30
    assert pwm_calls == [30]


def test_update_display_brightness_keeps_value_without_pwm(monkeypatch) -> None:
    monkeypatch.setattr(
        display_main,
        "read_display_config",
        lambda _conn: SimpleNamespace(display_brightness=30, night_mode_enabled=False),
    )
    monkeypatch.setattr(display_main, "effective_brightness", lambda brightness, _night: brightness)

    assert display_main.update_display_brightness("conn", active_brightness=60, display_pwm=None) == 60


def test_refresh_display_model_returns_model_and_next_refresh(monkeypatch) -> None:
    rendered_frames: list[object] = []
    display = SimpleNamespace(display=lambda frame: rendered_frames.append(frame))

    monkeypatch.setattr(display_main, "read_display_snapshot", lambda _conn: "snapshot")
    monkeypatch.setattr(display_main, "build_display_model", lambda snapshot: f"model:{snapshot}")

    result = display_main.refresh_display_model(
        "conn",
        display,
        (320, 240),
        refresh_interval=5.0,
        now=10.0,
    )

    assert result == display_main.DisplayRefreshResult(next_refresh_at=15.0, model="model:snapshot")
    assert rendered_frames == []


def test_refresh_display_model_shows_error_frame_on_failure(monkeypatch, capsys) -> None:
    rendered_frames: list[object] = []
    display = SimpleNamespace(display=lambda frame: rendered_frames.append(frame))

    monkeypatch.setattr(
        display_main,
        "read_display_snapshot",
        lambda _conn: (_ for _ in ()).throw(RuntimeError("db failure")),
    )
    monkeypatch.setattr(display_main, "make_error_frame", lambda message, size: (message, size))

    result = display_main.refresh_display_model(
        "conn",
        display,
        (320, 240),
        refresh_interval=5.0,
        now=10.0,
    )

    assert result == display_main.DisplayRefreshResult(next_refresh_at=15.0, model=None)
    assert rendered_frames == [("Data read error", (320, 240))]
    assert "Display data refresh failed: db failure" in capsys.readouterr().err


def test_apply_layout_toggles_consumes_pending_events(monkeypatch) -> None:
    monkeypatch.setattr(display_main, "toggle_layout", lambda layout: f"{layout}*")

    layout, pending = display_main.apply_layout_toggles("standard", 2)

    assert layout == "standard**"
    assert pending == 0


def test_render_model_if_needed_only_draws_when_signature_changes() -> None:
    rendered_frames: list[object] = []
    display = SimpleNamespace(display=lambda frame: rendered_frames.append(frame))

    class FakeLayout:
        name = "standard"

        def render(self, model, size):
            return (model, size)

    model = object()
    layout = FakeLayout()

    signature, refresh_at = display_main.render_model_if_needed(
        display,
        layout,
        model,
        (320, 240),
        last_drawn_signature=None,
        refresh_interval=5.0,
        now=10.0,
    )

    assert signature == ("standard", model)
    assert refresh_at is None
    assert rendered_frames == [((model), (320, 240))]

    signature, refresh_at = display_main.render_model_if_needed(
        display,
        layout,
        model,
        (320, 240),
        last_drawn_signature=signature,
        refresh_interval=5.0,
        now=10.0,
    )

    assert signature == ("standard", model)
    assert refresh_at is None
    assert len(rendered_frames) == 1


def test_render_model_if_needed_shows_error_frame_on_failure(monkeypatch, capsys) -> None:
    rendered_frames: list[object] = []
    display = SimpleNamespace(display=lambda frame: rendered_frames.append(frame))

    class FakeLayout:
        name = "standard"

        def render(self, model, size):
            raise RuntimeError("bad render")

    monkeypatch.setattr(display_main, "make_error_frame", lambda message, size: (message, size))

    signature, refresh_at = display_main.render_model_if_needed(
        display,
        FakeLayout(),
        object(),
        (320, 240),
        last_drawn_signature=None,
        refresh_interval=5.0,
        now=10.0,
    )

    assert signature is None
    assert refresh_at == pytest.approx(15.0)
    assert rendered_frames == [("Configuration error", (320, 240))]
    assert "Display render failed: bad render" in capsys.readouterr().err


def test_compute_sleep_until_refresh_clamps_to_idle_poll() -> None:
    assert display_main.compute_sleep_until_refresh(1.0, now=0.0) == pytest.approx(
        display_main.DISPLAY_IDLE_POLL_SECONDS
    )
    assert display_main.compute_sleep_until_refresh(0.05, now=0.0) == pytest.approx(0.05)
    assert display_main.compute_sleep_until_refresh(0.0, now=1.0) == 0.0
