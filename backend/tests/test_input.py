from __future__ import annotations

import subprocess

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
