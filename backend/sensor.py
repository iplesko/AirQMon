"""Sensor reader for the SCD4X (Dfrobot SEN0536) with simulator fallback.

This module exposes `read()` which returns a tuple `(co2_ppm, temperature_c, humidity_pct)`.
If the SCD4X driver or device is not available, a lightweight simulator returns plausible values.
"""
import random
import time

_device = None
_has_scd4x = False
try:
    from scd4x import SCD4X
    _has_scd4x = True
except Exception:
    _has_scd4x = False

if _has_scd4x:
    try:
        # Initialize the sensor and start periodic measurement. The driver may block or raise
        # if I2C is not available; swallow exceptions and fall back to simulator.
        _device = SCD4X(quiet=True)
        _device.start_periodic_measurement()
    except Exception:
        _device = None

_sim_co2 = 400.0
_sim_step = 100.0
_sim_min = 400.0
_sim_max = 2000.0
_sim_rising = True


def read_real():
    """Read values from the SCD4X device.

    Returns (co2_ppm, temperature_c, humidity_pct) as floats.
    Raises if device is not available or read fails.
    """
    if not _device:
        raise RuntimeError("SCD4X device not available")
    # The `measure()` call (as used on-device) returns at least co2, temp, rh.
    vals = _device.measure()
    # Accept tuples like (co2, temp, rh, ...)
    co2 = float(vals[0])
    temp = float(vals[1])
    hum = float(vals[2])
    return (co2, temp, hum)


def read_simulator():
    """Produce plausible synthetic sensor values for local development or when sensor is absent."""
    global _sim_co2, _sim_rising

    base_co2 = _sim_co2
    if _sim_rising:
        _sim_co2 += _sim_step
        if _sim_co2 >= _sim_max:
            _sim_co2 = _sim_max
            _sim_rising = False
    else:
        _sim_co2 -= _sim_step
        if _sim_co2 <= _sim_min:
            _sim_co2 = _sim_min
            _sim_rising = True

    base_temp = 22 + random.uniform(-1.5, 1.5)
    base_hum = 45 + random.uniform(-3, 3)
    return (round(base_co2, 1), round(base_temp, 2), round(base_hum, 2))


def read():
    """Return a reading from the real sensor when available, otherwise from the simulator."""
    if _device:
        try:
            return read_real()
        except Exception:
            # If a real read fails, fall back to simulator rather than crash.
            return read_simulator()
    return read_simulator()
