from __future__ import annotations

import pytest

from db import get_state, set_state
import runtime_config as runtime


def test_state_helpers_parse_defaults_and_bounds() -> None:
    assert runtime.bool_from_state("true") is True
    assert runtime.bool_from_state("YES") is True
    assert runtime.bool_from_state("off") is False
    assert runtime.bool_from_state(None, default=True) is True

    assert runtime.int_from_state("12", default=0) == 12
    assert runtime.int_from_state("oops", default=7) == 7
    assert runtime.bounded_int_from_state("120", 60, 0, 100) == 100
    assert runtime.bounded_int_from_state("-10", 60, 0, 100) == 0


def test_read_runtime_config_persists_defaults(conn) -> None:
    config = runtime.read_runtime_config(conn, persist_defaults=True)

    assert config == runtime.RuntimeConfig(
        co2_high=runtime.DEFAULT_CO2_HIGH,
        co2_clear=runtime.DEFAULT_CO2_CLEAR,
        cooldown_seconds=runtime.DEFAULT_COOLDOWN_SECONDS,
        display_brightness=runtime.DEFAULT_DISPLAY_BRIGHTNESS,
        night_mode_enabled=runtime.DEFAULT_NIGHT_MODE_ENABLED,
    )
    assert get_state(conn, runtime.CONFIG_KEY_CO2_HIGH) == str(runtime.DEFAULT_CO2_HIGH)
    assert get_state(conn, runtime.CONFIG_KEY_CO2_CLEAR) == str(runtime.DEFAULT_CO2_CLEAR)
    assert get_state(conn, runtime.CONFIG_KEY_COOLDOWN_SECONDS) == str(
        runtime.DEFAULT_COOLDOWN_SECONDS
    )
    assert get_state(conn, runtime.STATE_KEY_DISPLAY_BRIGHTNESS) == str(
        runtime.DEFAULT_DISPLAY_BRIGHTNESS
    )
    assert get_state(conn, runtime.STATE_KEY_NIGHT_MODE_ENABLED) == "1"


def test_persist_runtime_config_round_trips(conn) -> None:
    expected = runtime.RuntimeConfig(
        co2_high=1200,
        co2_clear=800,
        cooldown_seconds=900,
        display_brightness=35,
        night_mode_enabled=False,
    )

    runtime.persist_runtime_config(conn, expected)

    assert runtime.read_runtime_config(conn) == expected


def test_validate_runtime_config_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="co2_clear must be lower than co2_high"):
        runtime.validate_runtime_config(
            runtime.RuntimeConfig(
                co2_high=1000,
                co2_clear=1000,
                cooldown_seconds=10,
                display_brightness=60,
                night_mode_enabled=True,
            )
        )

    with pytest.raises(ValueError, match="display_brightness must be between 0 and 100"):
        runtime.validate_runtime_config(
            runtime.RuntimeConfig(
                co2_high=1200,
                co2_clear=800,
                cooldown_seconds=10,
                display_brightness=101,
                night_mode_enabled=True,
            )
        )


def test_ensure_alert_config_raises_for_invalid_persisted_state(conn) -> None:
    set_state(conn, runtime.CONFIG_KEY_CO2_HIGH, "1000")
    set_state(conn, runtime.CONFIG_KEY_CO2_CLEAR, "1000")
    set_state(conn, runtime.CONFIG_KEY_COOLDOWN_SECONDS, "30")

    with pytest.raises(ValueError, match="co2_clear must be lower than co2_high"):
        runtime.ensure_alert_config(conn)
