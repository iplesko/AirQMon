from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Optional

from co2_trend import (
    CO2_TREND_BASELINE_OFFSET_SECONDS,
    CO2_TREND_BASELINE_WINDOW_SECONDS,
    Co2Trend,
    calculate_co2_trend,
    format_co2_trend_percentage,
)
from db import latest, range_query

COLOR_NORMAL = "#22C55E"
COLOR_HIGH = "#FF7B72"
COLOR_VERY_HIGH = "#FF3B30"
COLOR_MUTED = "#94A3B8"


@dataclass(frozen=True)
class DisplaySnapshot:
    co2: Optional[float]
    temperature: Optional[float]
    humidity: Optional[float]
    trend: Optional[Co2Trend]


@dataclass(frozen=True)
class DisplayModel:
    co2_value: str
    co2_color: str
    trend_value: str
    trend_color: str
    temperature_value: str
    humidity_value: str


def _co2_color(co2: Optional[float]) -> str:
    if co2 is None:
        return COLOR_NORMAL
    if co2 >= 2000:
        return COLOR_VERY_HIGH
    if co2 >= 1000:
        return COLOR_HIGH
    return COLOR_NORMAL


def _trend_color(trend: Optional[Co2Trend]) -> str:
    if trend is None or trend.direction == "neutral":
        return COLOR_MUTED
    if trend.direction == "rising":
        return COLOR_HIGH
    return COLOR_NORMAL


def _trend_arrow(trend: Optional[Co2Trend]) -> str:
    if trend is None:
        return "--"
    if trend.direction == "rising":
        return "\u2197"
    if trend.direction == "falling":
        return "\u2198"
    return "\u2192"


def _as_float(value: object) -> Optional[float]:
    if value is None:
        return None
    return float(value)


def _format_temperature(value: Optional[float]) -> str:
    if value is None:
        return "--"
    return f"{value:.1f}\u00B0C"


def _format_humidity(value: Optional[float]) -> str:
    if value is None:
        return "--"
    return f"{value:.1f}%"


def _format_trend(trend: Optional[Co2Trend]) -> str:
    if trend is None:
        return "--"
    return f"{_trend_arrow(trend)} {format_co2_trend_percentage(trend.percentage)}"


def read_display_snapshot(conn) -> DisplaySnapshot:
    row = latest(conn)
    if not row:
        return DisplaySnapshot(co2=None, temperature=None, humidity=None, trend=None)

    ts_raw = row.get("ts")
    reference_ts = int(ts_raw) if ts_raw is not None else int(time.time())
    trend_start = reference_ts - CO2_TREND_BASELINE_OFFSET_SECONDS - CO2_TREND_BASELINE_WINDOW_SECONDS
    measurements = range_query(conn, trend_start, reference_ts)
    trend = calculate_co2_trend(measurements)

    return DisplaySnapshot(
        co2=_as_float(row.get("co2")),
        temperature=_as_float(row.get("temperature")),
        humidity=_as_float(row.get("humidity")),
        trend=trend,
    )


def build_display_model(snapshot: DisplaySnapshot) -> DisplayModel:
    return DisplayModel(
        co2_value="--" if snapshot.co2 is None else f"{int(round(snapshot.co2))}",
        co2_color=_co2_color(snapshot.co2),
        trend_value=_format_trend(snapshot.trend),
        trend_color=_trend_color(snapshot.trend),
        temperature_value=_format_temperature(snapshot.temperature),
        humidity_value=_format_humidity(snapshot.humidity),
    )
