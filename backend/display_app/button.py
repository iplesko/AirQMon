from __future__ import annotations

import ctypes
import fcntl
import os
import select

GPIO_CHIP_DEVICE = "/dev/gpiochip0"
GPIOHANDLE_REQUEST_INPUT = 1 << 0
GPIOEVENT_REQUEST_RISING_EDGE = 1 << 0
GPIOEVENT_EVENT_RISING_EDGE = 0x01


class GpioEventRequest(ctypes.Structure):
    _fields_ = [
        ("lineoffset", ctypes.c_uint32),
        ("handleflags", ctypes.c_uint32),
        ("eventflags", ctypes.c_uint32),
        ("consumer_label", ctypes.c_char * 32),
        ("fd", ctypes.c_int),
    ]


class GpioEventData(ctypes.Structure):
    _fields_ = [
        ("timestamp", ctypes.c_uint64),
        ("id", ctypes.c_uint32),
    ]


def _ioc(direction: int, request_type: int, number: int, size: int) -> int:
    return (
        (direction << 30)
        | (request_type << 8)
        | number
        | (size << 16)
    )


def _iowr(request_type: int, number: int, data_type: type[ctypes.Structure]) -> int:
    return _ioc(0x3, request_type, number, ctypes.sizeof(data_type))


GPIO_GET_LINEEVENT_IOCTL = _iowr(0xB4, 0x04, GpioEventRequest)


def _ioctl_roundtrip(fd: int, request_code: int, payload: ctypes.Structure) -> ctypes.Structure:
    payload_buffer = bytearray(
        ctypes.string_at(ctypes.addressof(payload), ctypes.sizeof(payload))
    )
    fcntl.ioctl(fd, request_code, payload_buffer, True)
    return type(payload).from_buffer_copy(payload_buffer)


def open_gpiochip_event_fd(line_offset: int) -> int:
    chip_fd = os.open(GPIO_CHIP_DEVICE, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
    try:
        request = GpioEventRequest(
            lineoffset=line_offset,
            handleflags=GPIOHANDLE_REQUEST_INPUT,
            eventflags=GPIOEVENT_REQUEST_RISING_EDGE,
            consumer_label=b"airqmon-display",
            fd=-1,
        )
        response = _ioctl_roundtrip(chip_fd, GPIO_GET_LINEEVENT_IOCTL, request)
    finally:
        os.close(chip_fd)

    if response.fd < 0:
        raise OSError("gpiochip edge request returned an invalid event file descriptor")
    return response.fd


def wait_for_rising_edge(event_fd: int, timeout_seconds: float) -> bool:
    try:
        readable, _, _ = select.select([event_fd], [], [], max(0.0, timeout_seconds))
    except InterruptedError:
        return False

    if not readable:
        return False

    raw_event = os.read(event_fd, ctypes.sizeof(GpioEventData))
    if len(raw_event) < ctypes.sizeof(GpioEventData):
        return False

    event = GpioEventData.from_buffer_copy(raw_event)
    return event.id == GPIOEVENT_EVENT_RISING_EDGE
