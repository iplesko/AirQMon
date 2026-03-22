from __future__ import annotations

from co2_trend import Co2Trend
from db import insert_measurement
from display_app import data


def test_build_display_model_formats_missing_values() -> None:
    model = data.build_display_model(
        data.DisplaySnapshot(co2=None, temperature=None, humidity=None, trend=None)
    )

    assert model.co2_value == "--"
    assert model.co2_color == data.COLOR_MUTED
    assert model.co2_quality is None
    assert model.trend_value == "--"
    assert model.trend_color == data.COLOR_MUTED
    assert model.temperature_value == "--"
    assert model.humidity_value == "--"


def test_build_display_model_formats_sensor_values_and_trend() -> None:
    trend = Co2Trend(
        direction="rising",
        percentage=12.34,
        raw_percentage=12.34,
        recent_average=900.0,
        baseline_average=800.0,
        reference_ts=1000,
    )
    model = data.build_display_model(
        data.DisplaySnapshot(co2=1555.6, temperature=23.4, humidity=44.4, trend=trend)
    )

    assert model.co2_value == "1556"
    assert model.co2_color == data.COLOR_HIGH
    assert model.co2_quality == data.AIR_QUALITY_BAD
    assert model.trend_value == "\u2197 12.3%"
    assert model.trend_color == data.COLOR_HIGH
    assert model.temperature_value == "23.4\u00B0C"
    assert model.humidity_value == "44.4%"


def test_read_display_snapshot_uses_latest_row_and_calculates_trend(conn) -> None:
    insert_measurement(conn, 300, 500.0, 20.1, 40.1)
    insert_measurement(conn, 360, 500.0, 20.2, 40.2)
    insert_measurement(conn, 900, 600.0, 21.0, 41.0)
    insert_measurement(conn, 960, 600.0, 21.1, 41.1)
    insert_measurement(conn, 1000, 650.0, 21.2, 41.2)

    snapshot = data.read_display_snapshot(conn)

    assert snapshot.co2 == 650.0
    assert snapshot.temperature == 21.2
    assert snapshot.humidity == 41.2
    assert snapshot.trend is not None
    assert snapshot.trend.direction == "rising"
