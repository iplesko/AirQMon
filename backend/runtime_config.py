from dataclasses import dataclass
from typing import Optional

from db import get_state, set_state

DEFAULT_CO2_HIGH = 1500
DEFAULT_CO2_CLEAR = 500
DEFAULT_COOLDOWN_SECONDS = 1800
DEFAULT_DISPLAY_BRIGHTNESS = 60
DEFAULT_NIGHT_MODE_ENABLED = True

CONFIG_KEY_CO2_HIGH = 'alert:co2_high'
CONFIG_KEY_CO2_CLEAR = 'alert:co2_clear'
CONFIG_KEY_COOLDOWN_SECONDS = 'alert:cooldown_seconds'
STATE_KEY_DISPLAY_BRIGHTNESS = 'display:brightness'
STATE_KEY_NIGHT_MODE_ENABLED = 'display:night_mode_enabled'


@dataclass(frozen=True)
class AlertConfig:
    co2_high: int
    co2_clear: int
    cooldown_seconds: int


@dataclass(frozen=True)
class DisplayConfig:
    display_brightness: int
    night_mode_enabled: bool


@dataclass(frozen=True)
class RuntimeConfig:
    co2_high: int
    co2_clear: int
    cooldown_seconds: int
    display_brightness: int
    night_mode_enabled: bool

    @property
    def alert(self) -> AlertConfig:
        return AlertConfig(
            co2_high=self.co2_high,
            co2_clear=self.co2_clear,
            cooldown_seconds=self.cooldown_seconds,
        )

    @property
    def display(self) -> DisplayConfig:
        return DisplayConfig(
            display_brightness=self.display_brightness,
            night_mode_enabled=self.night_mode_enabled,
        )


def bool_from_state(raw: Optional[str], default: bool = False) -> bool:
    if raw is None:
        return default
    return raw.lower() in ('1', 'true', 'yes', 'on')


def int_from_state(raw: Optional[str], default: int = 0) -> int:
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def bounded_int_from_state(raw: Optional[str], default: int, minimum: int, maximum: int) -> int:
    value = int_from_state(raw, default)
    return max(minimum, min(maximum, value))


def _get_state_with_default(conn, key: str, default: str, persist_defaults: bool) -> str:
    raw = get_state(conn, key)
    if raw is not None:
        return raw
    if persist_defaults:
        set_state(conn, key, default)
    return default


def read_alert_config(conn, *, persist_defaults: bool = False) -> AlertConfig:
    return AlertConfig(
        co2_high=int_from_state(
            _get_state_with_default(conn, CONFIG_KEY_CO2_HIGH, str(DEFAULT_CO2_HIGH), persist_defaults),
            DEFAULT_CO2_HIGH,
        ),
        co2_clear=int_from_state(
            _get_state_with_default(conn, CONFIG_KEY_CO2_CLEAR, str(DEFAULT_CO2_CLEAR), persist_defaults),
            DEFAULT_CO2_CLEAR,
        ),
        cooldown_seconds=int_from_state(
            _get_state_with_default(conn, CONFIG_KEY_COOLDOWN_SECONDS, str(DEFAULT_COOLDOWN_SECONDS), persist_defaults),
            DEFAULT_COOLDOWN_SECONDS,
        ),
    )


def read_display_config(conn, *, persist_defaults: bool = False) -> DisplayConfig:
    night_mode_default = '1' if DEFAULT_NIGHT_MODE_ENABLED else '0'
    return DisplayConfig(
        display_brightness=bounded_int_from_state(
            _get_state_with_default(
                conn,
                STATE_KEY_DISPLAY_BRIGHTNESS,
                str(DEFAULT_DISPLAY_BRIGHTNESS),
                persist_defaults,
            ),
            DEFAULT_DISPLAY_BRIGHTNESS,
            0,
            100,
        ),
        night_mode_enabled=bool_from_state(
            _get_state_with_default(
                conn,
                STATE_KEY_NIGHT_MODE_ENABLED,
                night_mode_default,
                persist_defaults,
            ),
            DEFAULT_NIGHT_MODE_ENABLED,
        ),
    )


def read_runtime_config(conn, *, persist_defaults: bool = False) -> RuntimeConfig:
    alert = read_alert_config(conn, persist_defaults=persist_defaults)
    display = read_display_config(conn, persist_defaults=persist_defaults)
    return RuntimeConfig(
        co2_high=alert.co2_high,
        co2_clear=alert.co2_clear,
        cooldown_seconds=alert.cooldown_seconds,
        display_brightness=display.display_brightness,
        night_mode_enabled=display.night_mode_enabled,
    )


def validate_alert_config(config: AlertConfig) -> None:
    if config.co2_clear >= config.co2_high:
        raise ValueError('co2_clear must be lower than co2_high')
    if config.cooldown_seconds < 0:
        raise ValueError('cooldown_seconds must be >= 0')


def validate_display_config(config: DisplayConfig) -> None:
    if not (0 <= config.display_brightness <= 100):
        raise ValueError('display_brightness must be between 0 and 100')


def validate_runtime_config(config: RuntimeConfig) -> None:
    validate_alert_config(config.alert)
    validate_display_config(config.display)


def ensure_alert_config(conn) -> AlertConfig:
    config = read_alert_config(conn, persist_defaults=True)
    validate_alert_config(config)
    return config


def ensure_runtime_config(conn) -> RuntimeConfig:
    config = read_runtime_config(conn, persist_defaults=True)
    validate_runtime_config(config)
    return config


def persist_alert_config(conn, config: AlertConfig) -> None:
    set_state(conn, CONFIG_KEY_CO2_HIGH, str(config.co2_high))
    set_state(conn, CONFIG_KEY_CO2_CLEAR, str(config.co2_clear))
    set_state(conn, CONFIG_KEY_COOLDOWN_SECONDS, str(config.cooldown_seconds))


def persist_display_config(conn, config: DisplayConfig) -> None:
    set_state(conn, STATE_KEY_DISPLAY_BRIGHTNESS, str(config.display_brightness))
    set_state(conn, STATE_KEY_NIGHT_MODE_ENABLED, '1' if config.night_mode_enabled else '0')


def persist_runtime_config(conn, config: RuntimeConfig) -> None:
    persist_alert_config(conn, config.alert)
    persist_display_config(conn, config.display)
