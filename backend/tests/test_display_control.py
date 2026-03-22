from __future__ import annotations

import display_control


def test_write_and_read_display_pid_round_trip(test_tmp_dir) -> None:
    pid_file = test_tmp_dir / "display.pid"

    display_control.write_display_pid(pid=4321, pid_file=pid_file)

    assert display_control.read_display_pid(pid_file) == 4321


def test_read_display_pid_returns_none_for_invalid_values(test_tmp_dir) -> None:
    pid_file = test_tmp_dir / "display.pid"
    pid_file.write_text("not-a-pid\n", encoding="ascii")

    assert display_control.read_display_pid(pid_file) is None

    pid_file.write_text("-5\n", encoding="ascii")

    assert display_control.read_display_pid(pid_file) is None


def test_remove_display_pid_ignores_missing_files(test_tmp_dir) -> None:
    pid_file = test_tmp_dir / "missing.pid"

    display_control.remove_display_pid(pid_file)

    assert pid_file.exists() is False


def test_request_layout_toggle_returns_false_without_signal(monkeypatch, test_tmp_dir) -> None:
    pid_file = test_tmp_dir / "display.pid"
    monkeypatch.setattr(display_control, "DISPLAY_TOGGLE_SIGNAL", None)

    assert display_control.request_layout_toggle(pid_file) is False


def test_request_layout_toggle_removes_stale_pid_when_process_is_not_display(monkeypatch, test_tmp_dir) -> None:
    pid_file = test_tmp_dir / "display.pid"
    pid_file.write_text("4321\n", encoding="ascii")

    monkeypatch.setattr(display_control, "DISPLAY_TOGGLE_SIGNAL", 10)
    monkeypatch.setattr(display_control, "_pid_matches_display", lambda pid: False)

    assert display_control.request_layout_toggle(pid_file) is False
    assert pid_file.exists() is False


def test_request_layout_toggle_removes_pid_when_process_is_missing(monkeypatch, test_tmp_dir) -> None:
    pid_file = test_tmp_dir / "display.pid"
    pid_file.write_text("4321\n", encoding="ascii")

    def fake_kill(_pid, _signal_number):
        raise ProcessLookupError

    monkeypatch.setattr(display_control, "DISPLAY_TOGGLE_SIGNAL", 10)
    monkeypatch.setattr(display_control, "_pid_matches_display", lambda pid: True)
    monkeypatch.setattr(display_control.os, "kill", fake_kill)

    assert display_control.request_layout_toggle(pid_file) is False
    assert pid_file.exists() is False


def test_request_layout_toggle_returns_false_on_permission_error(monkeypatch, test_tmp_dir) -> None:
    pid_file = test_tmp_dir / "display.pid"
    pid_file.write_text("4321\n", encoding="ascii")

    def fake_kill(_pid, _signal_number):
        raise PermissionError

    monkeypatch.setattr(display_control, "DISPLAY_TOGGLE_SIGNAL", 10)
    monkeypatch.setattr(display_control, "_pid_matches_display", lambda pid: True)
    monkeypatch.setattr(display_control.os, "kill", fake_kill)

    assert display_control.request_layout_toggle(pid_file) is False
    assert pid_file.exists() is True


def test_request_layout_toggle_sends_signal_to_display_process(monkeypatch, test_tmp_dir) -> None:
    pid_file = test_tmp_dir / "display.pid"
    pid_file.write_text("4321\n", encoding="ascii")
    kill_calls: list[tuple[int, int]] = []

    monkeypatch.setattr(display_control, "DISPLAY_TOGGLE_SIGNAL", 10)
    monkeypatch.setattr(display_control, "_pid_matches_display", lambda pid: True)
    monkeypatch.setattr(
        display_control.os,
        "kill",
        lambda pid, signal_number: kill_calls.append((pid, signal_number)),
    )

    assert display_control.request_layout_toggle(pid_file) is True
    assert kill_calls == [(4321, 10)]
