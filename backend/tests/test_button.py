from __future__ import annotations

import ctypes
import importlib

import pytest

button = importlib.import_module("display_app.button")


def test_ioc_packs_ioctl_fields() -> None:
    assert button._ioc(0x3, 0xB4, 0x04, 16) == ((0x3 << 30) | (0xB4 << 8) | 0x04 | (16 << 16))


def test_ioctl_roundtrip_returns_updated_structure(monkeypatch) -> None:
    request = button.GpioEventRequest(
        lineoffset=24,
        handleflags=button.GPIOHANDLE_REQUEST_INPUT,
        eventflags=button.GPIOEVENT_REQUEST_RISING_EDGE,
        consumer_label=b"airqmon-input",
        fd=-1,
    )

    def fake_ioctl(fd, request_code, payload_buffer, mutate):
        updated = button.GpioEventRequest(
            lineoffset=24,
            handleflags=button.GPIOHANDLE_REQUEST_INPUT,
            eventflags=button.GPIOEVENT_REQUEST_RISING_EDGE,
            consumer_label=b"airqmon-input",
            fd=77,
        )
        payload_buffer[:] = ctypes.string_at(ctypes.addressof(updated), ctypes.sizeof(updated))

    monkeypatch.setattr(button, "fcntl", type("FakeFcntl", (), {"ioctl": staticmethod(fake_ioctl)})())

    response = button._ioctl_roundtrip(3, 4, request)

    assert response.fd == 77


def test_open_gpiochip_event_fd_returns_response_fd_and_closes_chip(monkeypatch) -> None:
    close_calls: list[int] = []

    monkeypatch.setattr(button.os, "open", lambda path, flags: 11)
    monkeypatch.setattr(button.os, "close", lambda fd: close_calls.append(fd))
    monkeypatch.setattr(
        button,
        "_ioctl_roundtrip",
        lambda fd, request_code, request: button.GpioEventRequest(
            lineoffset=request.lineoffset,
            handleflags=request.handleflags,
            eventflags=request.eventflags,
            consumer_label=request.consumer_label,
            fd=42,
        ),
    )

    event_fd = button.open_gpiochip_event_fd(24)

    assert event_fd == 42
    assert close_calls == [11]


def test_open_gpiochip_event_fd_raises_for_invalid_response_fd(monkeypatch) -> None:
    monkeypatch.setattr(button.os, "open", lambda path, flags: 11)
    monkeypatch.setattr(button.os, "close", lambda fd: None)
    monkeypatch.setattr(
        button,
        "_ioctl_roundtrip",
        lambda fd, request_code, request: button.GpioEventRequest(
            lineoffset=request.lineoffset,
            handleflags=request.handleflags,
            eventflags=request.eventflags,
            consumer_label=request.consumer_label,
            fd=-1,
        ),
    )

    with pytest.raises(OSError, match="invalid event file descriptor"):
        button.open_gpiochip_event_fd(24)


def test_wait_for_button_edge_returns_none_on_interrupt(monkeypatch) -> None:
    def fake_select(*_args, **_kwargs):
        raise InterruptedError

    monkeypatch.setattr(button.select, "select", fake_select)

    assert button.wait_for_button_edge(5, 1.0) is None


def test_wait_for_button_edge_returns_none_on_timeout(monkeypatch) -> None:
    monkeypatch.setattr(button.select, "select", lambda *args, **kwargs: ([], [], []))

    assert button.wait_for_button_edge(5, 1.0) is None


def test_wait_for_button_edge_decodes_rising_and_falling_edges(monkeypatch) -> None:
    monkeypatch.setattr(button.select, "select", lambda *args, **kwargs: ([5], [], []))
    rising_event = button.GpioEventData(timestamp=1, id=button.GPIOEVENT_EVENT_RISING_EDGE)
    falling_event = button.GpioEventData(timestamp=1, id=button.GPIOEVENT_EVENT_FALLING_EDGE)
    reads = [
        ctypes.string_at(ctypes.addressof(rising_event), ctypes.sizeof(rising_event)),
        ctypes.string_at(ctypes.addressof(falling_event), ctypes.sizeof(falling_event)),
    ]
    monkeypatch.setattr(button.os, "read", lambda fd, size: reads.pop(0))

    assert button.wait_for_button_edge(5, 1.0) == button.ButtonEdge.RISING
    assert button.wait_for_button_edge(5, 1.0) == button.ButtonEdge.FALLING


def test_wait_for_button_edge_returns_none_for_short_or_unknown_event(monkeypatch) -> None:
    monkeypatch.setattr(button.select, "select", lambda *args, **kwargs: ([5], [], []))
    unknown_event = button.GpioEventData(timestamp=1, id=999)
    reads = [
        b"\x00\x01",
        ctypes.string_at(ctypes.addressof(unknown_event), ctypes.sizeof(unknown_event)),
    ]
    monkeypatch.setattr(button.os, "read", lambda fd, size: reads.pop(0))

    assert button.wait_for_button_edge(5, 1.0) is None
    assert button.wait_for_button_edge(5, 1.0) is None
