from __future__ import annotations

import sensor


def test_read_real_applies_temperature_offset(monkeypatch) -> None:
    fake_device = type(
        "FakeDevice",
        (),
        {"measure": lambda self: (1200.0, 25.0, 40.0)},
    )()
    monkeypatch.setattr(sensor, "_device", fake_device)

    assert sensor.read_real() == (1200.0, 21.0, 40.0)


def test_read_simulator_advances_and_flips_direction_at_upper_bound(monkeypatch) -> None:
    monkeypatch.setattr(sensor, "_sim_co2", 1900.0)
    monkeypatch.setattr(sensor, "_sim_step", 100.0)
    monkeypatch.setattr(sensor, "_sim_max", 2000.0)
    monkeypatch.setattr(sensor, "_sim_min", 400.0)
    monkeypatch.setattr(sensor, "_sim_rising", True)
    monkeypatch.setattr(sensor.random, "uniform", lambda a, b: 0.0)

    reading = sensor.read_simulator()

    assert reading == (1900.0, 22.0, 45.0)
    assert sensor._sim_co2 == 2000.0
    assert sensor._sim_rising is False


def test_read_uses_simulator_when_no_device(monkeypatch) -> None:
    monkeypatch.setattr(sensor, "_device", None)
    monkeypatch.setattr(sensor, "read_simulator", lambda: (500.0, 20.0, 40.0))

    assert sensor.read() == (500.0, 20.0, 40.0)


def test_read_falls_back_to_simulator_when_real_read_fails(monkeypatch) -> None:
    monkeypatch.setattr(sensor, "_device", object())
    monkeypatch.setattr(
        sensor,
        "read_real",
        lambda: (_ for _ in ()).throw(RuntimeError("i2c failure")),
    )
    monkeypatch.setattr(sensor, "read_simulator", lambda: (600.0, 21.0, 41.0))

    assert sensor.read() == (600.0, 21.0, 41.0)
