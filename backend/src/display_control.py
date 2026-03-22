from __future__ import annotations

import os
import signal
from pathlib import Path
from typing import Optional

from paths import DISPLAY_PID_FILE

DISPLAY_TOGGLE_SIGNAL = getattr(signal, "SIGUSR1", None)


def _normalize_pid_file(pid_file: Path | str | None = None) -> Path:
    if pid_file is None:
        return DISPLAY_PID_FILE
    return Path(pid_file)


def write_display_pid(pid: Optional[int] = None, pid_file: Path | str | None = None) -> None:
    target = _normalize_pid_file(pid_file)
    pid_value = os.getpid() if pid is None else pid
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_target = target.with_name(f"{target.name}.tmp")
    temp_target.write_text(f"{pid_value}\n", encoding="ascii")
    os.replace(temp_target, target)


def remove_display_pid(pid_file: Path | str | None = None) -> None:
    target = _normalize_pid_file(pid_file)
    try:
        target.unlink()
    except FileNotFoundError:
        pass


def read_display_pid(pid_file: Path | str | None = None) -> Optional[int]:
    target = _normalize_pid_file(pid_file)
    try:
        raw_pid = target.read_text(encoding="ascii").strip()
    except FileNotFoundError:
        return None
    except OSError:
        return None

    try:
        pid = int(raw_pid)
    except ValueError:
        return None
    if pid <= 0:
        return None
    return pid


def _pid_matches_display(pid: int) -> bool:
    proc_cmdline = Path(f"/proc/{pid}/cmdline")
    if not proc_cmdline.exists():
        return True

    try:
        raw_cmdline = proc_cmdline.read_bytes()
    except OSError:
        return False

    args = [arg for arg in raw_cmdline.decode("utf-8", errors="ignore").split("\x00") if arg]
    return any(Path(arg).name == "display.py" or arg in {"display", "display_app.main"} for arg in args)


def request_layout_toggle(pid_file: Path | str | None = None) -> bool:
    if DISPLAY_TOGGLE_SIGNAL is None:
        return False

    target = _normalize_pid_file(pid_file)
    pid = read_display_pid(target)
    if pid is None:
        return False
    if not _pid_matches_display(pid):
        remove_display_pid(target)
        return False

    try:
        os.kill(pid, DISPLAY_TOGGLE_SIGNAL)
    except ProcessLookupError:
        remove_display_pid(target)
        return False
    except PermissionError:
        return False
    return True
