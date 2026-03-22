from __future__ import annotations

import pytest

import co2_trend as trend


def measurement(ts: int, co2: float) -> dict[str, float]:
    return {"ts": ts, "co2": co2}


def test_calculate_co2_trend_returns_rising_trend() -> None:
    measurements = [
        measurement(300, 500.0),
        measurement(360, 500.0),
        measurement(900, 600.0),
        measurement(960, 600.0),
        measurement(1000, 600.0),
    ]

    result = trend.calculate_co2_trend(measurements)

    assert result is not None
    assert result.direction == "rising"
    assert result.percentage == pytest.approx(20.0)
    assert result.raw_percentage == pytest.approx(20.0)
    assert result.reference_ts == 1000


def test_calculate_co2_trend_returns_neutral_when_change_is_small() -> None:
    measurements = [
        measurement(300, 1000.0),
        measurement(360, 1000.0),
        measurement(900, 1005.0),
        measurement(960, 1005.0),
        measurement(1000, 1005.0),
    ]

    result = trend.calculate_co2_trend(measurements)

    assert result is not None
    assert result.direction == "neutral"
    assert result.percentage == 0.0
    assert result.raw_percentage == pytest.approx(0.5)


def test_calculate_co2_trend_returns_none_without_required_windows() -> None:
    result = trend.calculate_co2_trend([measurement(1000, 750.0)])

    assert result is None


def test_format_co2_trend_percentage_hides_negative_sign() -> None:
    assert trend.format_co2_trend_percentage(-12.34) == "12.3%"
    assert trend.format_co2_trend_percentage(0.0) == "0.0%"
