from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Sequence


CO2_TREND_RECENT_WINDOW_SECONDS = 2 * 60
CO2_TREND_BASELINE_OFFSET_SECONDS = 10 * 60
CO2_TREND_BASELINE_WINDOW_SECONDS = 2 * 60
CO2_TREND_NEUTRAL_PERCENT_THRESHOLD = 1.0


@dataclass(frozen=True)
class Co2Trend:
    direction: str
    percentage: float
    raw_percentage: float
    recent_average: float
    baseline_average: float
    reference_ts: int


def _get_average_co2_in_window(
    measurements: Sequence[Mapping[str, object]], start_ts: int, end_ts: int
) -> Optional[float]:
    values = []
    for item in measurements:
        ts = item.get("ts")
        co2 = item.get("co2")
        if ts is None or co2 is None:
            continue
        ts_int = int(ts)
        if start_ts <= ts_int <= end_ts:
            values.append(float(co2))

    if not values:
        return None
    return sum(values) / len(values)


def _get_trend_direction(percentage: float) -> str:
    if percentage >= CO2_TREND_NEUTRAL_PERCENT_THRESHOLD:
        return "rising"
    if percentage <= -CO2_TREND_NEUTRAL_PERCENT_THRESHOLD:
        return "falling"
    return "neutral"


def calculate_co2_trend(measurements: Sequence[Mapping[str, object]]) -> Optional[Co2Trend]:
    if not measurements:
        return None

    last_item = measurements[-1]
    reference_ts_raw = last_item.get("ts")
    if reference_ts_raw is None:
        return None
    reference_ts = int(reference_ts_raw)

    recent_start = reference_ts - CO2_TREND_RECENT_WINDOW_SECONDS
    baseline_end = reference_ts - CO2_TREND_BASELINE_OFFSET_SECONDS
    baseline_start = baseline_end - CO2_TREND_BASELINE_WINDOW_SECONDS

    recent_average = _get_average_co2_in_window(measurements, recent_start, reference_ts)
    baseline_average = _get_average_co2_in_window(measurements, baseline_start, baseline_end)

    if recent_average is None or baseline_average is None or baseline_average <= 0:
        return None

    raw_percentage = ((recent_average - baseline_average) / baseline_average) * 100.0
    direction = _get_trend_direction(raw_percentage)
    percentage = 0.0 if direction == "neutral" else raw_percentage

    return Co2Trend(
        direction=direction,
        percentage=percentage,
        raw_percentage=raw_percentage,
        recent_average=recent_average,
        baseline_average=baseline_average,
        reference_ts=reference_ts,
    )


def format_co2_trend_percentage(percentage: float) -> str:
    if percentage == 0:
        return "0.0%"
    return f"{abs(percentage):.1f}%"
