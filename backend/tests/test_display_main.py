from __future__ import annotations

import importlib
from argparse import Namespace

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
