from dataclasses import dataclass
from typing import Optional

from db import get_state, set_state

DEFAULT_CO2_HIGH = 1500
DEFAULT_CO2_CLEAR = 500
DEFAULT_COOLDOWN_SECONDS = 1800

CONFIG_KEY_CO2_HIGH = 'alert:co2_high'
CONFIG_KEY_CO2_CLEAR = 'alert:co2_clear'
CONFIG_KEY_COOLDOWN_SECONDS = 'alert:cooldown_seconds'

STATE_KEY_LAST_SEEN_ID = 'alert:last_seen_id'
STATE_KEY_IN_ALERT = 'alert:in_alert'
STATE_KEY_LAST_ALERT_TS = 'alert:last_alert_ts'


@dataclass(frozen=True)
class AlertConfig:
    co2_high: int
    co2_clear: int
    cooldown_seconds: int


@dataclass
class AlertRuntimeState:
    last_seen_id: int = 0
    in_alert: bool = False
    last_alert_ts: int = 0


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


def ensure_alert_config(conn) -> AlertConfig:
    co2_high_raw = get_state(conn, CONFIG_KEY_CO2_HIGH)
    co2_clear_raw = get_state(conn, CONFIG_KEY_CO2_CLEAR)
    cooldown_raw = get_state(conn, CONFIG_KEY_COOLDOWN_SECONDS)

    config = AlertConfig(
        co2_high=int_from_state(co2_high_raw, DEFAULT_CO2_HIGH),
        co2_clear=int_from_state(co2_clear_raw, DEFAULT_CO2_CLEAR),
        cooldown_seconds=int_from_state(cooldown_raw, DEFAULT_COOLDOWN_SECONDS),
    )

    if co2_high_raw is None:
        set_state(conn, CONFIG_KEY_CO2_HIGH, str(config.co2_high))
    if co2_clear_raw is None:
        set_state(conn, CONFIG_KEY_CO2_CLEAR, str(config.co2_clear))
    if cooldown_raw is None:
        set_state(conn, CONFIG_KEY_COOLDOWN_SECONDS, str(config.cooldown_seconds))

    return config


def ensure_runtime_config(conn) -> AlertConfig:
    config = ensure_alert_config(conn)
    if config.co2_clear >= config.co2_high:
        raise ValueError('Configured co2_clear must be lower than co2_high')
    return config


def load_runtime_state(conn) -> AlertRuntimeState:
    return AlertRuntimeState(
        last_seen_id=int_from_state(get_state(conn, STATE_KEY_LAST_SEEN_ID), 0),
        in_alert=bool_from_state(get_state(conn, STATE_KEY_IN_ALERT), False),
        last_alert_ts=int_from_state(get_state(conn, STATE_KEY_LAST_ALERT_TS), 0),
    )


def persist_runtime_state(conn, state: AlertRuntimeState) -> None:
    set_state(conn, STATE_KEY_LAST_SEEN_ID, str(state.last_seen_id))
    set_state(conn, STATE_KEY_IN_ALERT, '1' if state.in_alert else '0')
    set_state(conn, STATE_KEY_LAST_ALERT_TS, str(state.last_alert_ts))
