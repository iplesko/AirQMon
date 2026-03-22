from __future__ import annotations

import subprocess

import pytest

import input as input_service


def test_first_existing_path_returns_first_match(monkeypatch) -> None:
    monkeypatch.setattr(
        input_service.os.path,
        "exists",
        lambda path: path in {"/second", "/third"},
    )

    assert input_service._first_existing_path(("/first", "/second", "/third")) == "/second"
    assert input_service._first_existing_path(("/missing",)) is None


def test_resolve_shutdown_command_prefers_poweroff_binary(monkeypatch) -> None:
    monkeypatch.setattr(
        input_service,
        "_first_existing_path",
        lambda paths: "/usr/sbin/poweroff" if paths == input_service.POWEROFF_CANDIDATE_PATHS else None,
    )

    assert input_service.resolve_shutdown_command() == ("/usr/sbin/poweroff",)


def test_resolve_shutdown_command_falls_back_to_systemctl(monkeypatch) -> None:
    monkeypatch.setattr(
        input_service,
        "_first_existing_path",
        lambda paths: "/bin/systemctl" if paths == input_service.SYSTEMCTL_CANDIDATE_PATHS else None,
    )

    assert input_service.resolve_shutdown_command() == ("/bin/systemctl", "poweroff")


def test_request_system_shutdown_returns_false_without_command(capsys) -> None:
    result = input_service.request_system_shutdown(None)

    captured = capsys.readouterr()

    assert result is False
    assert "shutdown is unavailable" in captured.err


def test_request_system_shutdown_returns_true_on_success(monkeypatch, capsys) -> None:
    calls: list[tuple[tuple[str, ...], bool, bool, bool]] = []

    def fake_run(command, check, capture_output, text):
        calls.append((command, check, capture_output, text))

    monkeypatch.setattr(input_service.subprocess, "run", fake_run)

    result = input_service.request_system_shutdown(("/usr/sbin/poweroff",))

    captured = capsys.readouterr()

    assert result is True
    assert calls == [(( "/usr/sbin/poweroff",), True, True, True)]
    assert "requesting system shutdown" in captured.err


def test_request_system_shutdown_reports_missing_binary(monkeypatch, capsys) -> None:
    def fake_run(*_args, **_kwargs):
        raise FileNotFoundError("missing")

    monkeypatch.setattr(input_service.subprocess, "run", fake_run)

    result = input_service.request_system_shutdown(("/usr/sbin/poweroff",))

    captured = capsys.readouterr()

    assert result is False
    assert "System shutdown request failed" in captured.err


def test_request_system_shutdown_reports_called_process_error(monkeypatch, capsys) -> None:
    def fake_run(*_args, **_kwargs):
        raise subprocess.CalledProcessError(
            1,
            ("/usr/sbin/poweroff",),
            stderr="permission denied\n",
        )

    monkeypatch.setattr(input_service.subprocess, "run", fake_run)

    result = input_service.request_system_shutdown(("/usr/sbin/poweroff",))

    captured = capsys.readouterr()

    assert result is False
    assert "permission denied" in captured.err


def test_main_returns_2_when_runtime_dependencies_cannot_load(monkeypatch, capsys) -> None:
    def fail_runtime():
        raise ModuleNotFoundError("No module named 'RPi'")

    monkeypatch.setattr(input_service, "load_input_runtime", fail_runtime)

    assert input_service.main() == 2
    assert "Input runtime init failed" in capsys.readouterr().err


def test_compute_wait_timeout_uses_idle_poll_without_press() -> None:
    state = input_service.InputLoopState()

    assert input_service.compute_wait_timeout(state, now=10.0) == input_service.BUTTON_IDLE_POLL_SECONDS


def test_compute_wait_timeout_uses_hold_poll_when_button_is_pressed() -> None:
    state = input_service.InputLoopState(button_pressed_at=10.0)

    wait_timeout = input_service.compute_wait_timeout(
        state,
        now=10.0 + input_service.BUTTON_SHUTDOWN_HOLD_SECONDS - 0.05,
    )

    assert wait_timeout == pytest.approx(0.05)


def test_handle_no_button_edge_requests_shutdown_after_hold() -> None:
    state = input_service.InputLoopState(button_pressed_at=10.0)
    shutdown_calls: list[object] = []

    input_service.handle_no_button_edge(
        state,
        now=10.0 + input_service.BUTTON_SHUTDOWN_HOLD_SECONDS,
        button_is_high=True,
        shutdown_command=("poweroff",),
        request_shutdown=lambda command: shutdown_calls.append(command) or True,
    )

    assert state.shutdown_attempted_for_press is True
    assert state.stop is True
    assert shutdown_calls == [("poweroff",)]


def test_handle_button_edge_event_requests_layout_on_rising_edge() -> None:
    state = input_service.InputLoopState()
    layout_calls: list[str] = []

    input_service.handle_button_edge_event(
        state,
        button_edge="rising",
        now=5.0,
        rising_edge="rising",
        falling_edge="falling",
        shutdown_command=None,
        request_layout=lambda: layout_calls.append("layout") or True,
    )

    assert state.button_pressed_at == 5.0
    assert state.last_layout_toggle_at == 5.0
    assert layout_calls == ["layout"]


def test_handle_button_edge_event_respects_bounce_window() -> None:
    state = input_service.InputLoopState(last_layout_toggle_at=5.0)
    layout_calls: list[str] = []

    input_service.handle_button_edge_event(
        state,
        button_edge="rising",
        now=5.1,
        rising_edge="rising",
        falling_edge="falling",
        shutdown_command=None,
        request_layout=lambda: layout_calls.append("layout") or True,
    )

    assert state.button_pressed_at == 5.1
    assert state.last_layout_toggle_at == 5.0
    assert layout_calls == []


def test_handle_button_edge_event_requests_shutdown_on_long_fall() -> None:
    state = input_service.InputLoopState(button_pressed_at=10.0)
    shutdown_calls: list[object] = []

    input_service.handle_button_edge_event(
        state,
        button_edge="falling",
        now=10.0 + input_service.BUTTON_SHUTDOWN_HOLD_SECONDS,
        rising_edge="rising",
        falling_edge="falling",
        shutdown_command=("poweroff",),
        request_shutdown=lambda command: shutdown_calls.append(command) or True,
    )

    assert state.button_pressed_at is None
    assert state.shutdown_attempted_for_press is True
    assert state.stop is True
    assert shutdown_calls == [("poweroff",)]
