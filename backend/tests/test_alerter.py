from __future__ import annotations

from unittest.mock import Mock

import alerter
from push_notifications import PushDeliveryStats
from runtime_config import AlertConfig


def make_row(
    *,
    row_id: int = 1,
    ts: int = 1000,
    co2: float = 1200.0,
    temperature: float = 22.5,
    humidity: float = 45.0,
) -> dict[str, float]:
    return {
        "id": row_id,
        "ts": ts,
        "co2": co2,
        "temperature": temperature,
        "humidity": humidity,
    }


def test_runtime_state_round_trips_through_database(conn) -> None:
    state = alerter.AlertRuntimeState(last_seen_id=7, in_alert=True, last_alert_ts=900)

    alerter.persist_runtime_state(conn, state)

    assert alerter.load_runtime_state(conn) == state


def test_should_send_high_alert_requires_threshold_and_cooldown() -> None:
    config = AlertConfig(co2_high=1000, co2_clear=700, cooldown_seconds=300)

    assert (
        alerter.should_send_high_alert(
            1000,
            1200.0,
            alerter.AlertRuntimeState(last_seen_id=0, in_alert=False, last_alert_ts=600),
            config,
        )
        is True
    )
    assert (
        alerter.should_send_high_alert(
            1000,
            950.0,
            alerter.AlertRuntimeState(last_seen_id=0, in_alert=False, last_alert_ts=0),
            config,
        )
        is False
    )
    assert (
        alerter.should_send_high_alert(
            1000,
            1200.0,
            alerter.AlertRuntimeState(last_seen_id=0, in_alert=True, last_alert_ts=0),
            config,
        )
        is False
    )
    assert (
        alerter.should_send_high_alert(
            1000,
            1200.0,
            alerter.AlertRuntimeState(last_seen_id=0, in_alert=False, last_alert_ts=800),
            config,
        )
        is False
    )


def test_process_row_sends_high_alert_and_updates_state(conn, monkeypatch) -> None:
    row = make_row(row_id=7, ts=1000, co2=1200.0)
    state = alerter.AlertRuntimeState()
    config = AlertConfig(co2_high=1000, co2_clear=700, cooldown_seconds=300)
    events: list[tuple[str, dict]] = []

    build_high_payload = Mock(return_value="high-payload")
    send_push_to_all = Mock(return_value=PushDeliveryStats(attempted=2, sent=1, removed=0))

    monkeypatch.setattr(alerter, "build_high_payload", build_high_payload)
    monkeypatch.setattr(alerter, "send_push_to_all", send_push_to_all)
    monkeypatch.setattr(
        alerter,
        "log_event",
        lambda event, **fields: events.append((event, fields)),
    )

    alerter.process_row(conn, row, state, config, "private-key.pem", {"sub": "mailto:test@example.com"})

    build_high_payload.assert_called_once_with(row, 1000)
    send_push_to_all.assert_called_once_with(
        conn,
        "high-payload",
        "private-key.pem",
        {"sub": "mailto:test@example.com"},
    )
    assert state == alerter.AlertRuntimeState(last_seen_id=7, in_alert=True, last_alert_ts=1000)
    assert len(events) == 1
    assert events[0][0] == "alert_sent"
    assert events[0][1]["push_sent"] == 1


def test_process_row_logs_when_high_alert_cannot_be_sent(conn, monkeypatch) -> None:
    row = make_row(row_id=5, ts=1000, co2=1200.0)
    state = alerter.AlertRuntimeState()
    config = AlertConfig(co2_high=1000, co2_clear=700, cooldown_seconds=300)
    events: list[tuple[str, dict]] = []

    monkeypatch.setattr(alerter, "build_high_payload", Mock(return_value="high-payload"))
    monkeypatch.setattr(
        alerter,
        "send_push_to_all",
        Mock(return_value=PushDeliveryStats(attempted=0, sent=0, removed=0)),
    )
    monkeypatch.setattr(
        alerter,
        "log_event",
        lambda event, **fields: events.append((event, fields)),
    )

    alerter.process_row(conn, row, state, config, "private-key.pem", {"sub": "mailto:test@example.com"})

    assert state == alerter.AlertRuntimeState(last_seen_id=5, in_alert=False, last_alert_ts=0)
    assert len(events) == 1
    assert events[0][0] == "alert_not_sent"


def test_process_row_sends_recovery_and_clears_alert_state(conn, monkeypatch) -> None:
    row = make_row(row_id=9, ts=1100, co2=650.0)
    state = alerter.AlertRuntimeState(last_seen_id=8, in_alert=True, last_alert_ts=900)
    config = AlertConfig(co2_high=1000, co2_clear=700, cooldown_seconds=300)
    events: list[tuple[str, dict]] = []

    build_recovery_payload = Mock(return_value="recovery-payload")
    send_push_to_all = Mock(return_value=PushDeliveryStats(attempted=1, sent=1, removed=0))

    monkeypatch.setattr(alerter, "build_recovery_payload", build_recovery_payload)
    monkeypatch.setattr(alerter, "send_push_to_all", send_push_to_all)
    monkeypatch.setattr(
        alerter,
        "log_event",
        lambda event, **fields: events.append((event, fields)),
    )

    alerter.process_row(conn, row, state, config, "private-key.pem", {"sub": "mailto:test@example.com"})

    build_recovery_payload.assert_called_once_with(row, 700)
    send_push_to_all.assert_called_once_with(
        conn,
        "recovery-payload",
        "private-key.pem",
        {"sub": "mailto:test@example.com"},
    )
    assert state == alerter.AlertRuntimeState(last_seen_id=9, in_alert=False, last_alert_ts=900)
    assert len(events) == 1
    assert events[0][0] == "recovery_sent"
    assert events[0][1]["in_alert_after"] is False


def test_process_row_clears_alert_when_all_recipients_are_removed(conn, monkeypatch) -> None:
    row = make_row(row_id=10, ts=1200, co2=680.0)
    state = alerter.AlertRuntimeState(last_seen_id=9, in_alert=True, last_alert_ts=900)
    config = AlertConfig(co2_high=1000, co2_clear=700, cooldown_seconds=300)

    monkeypatch.setattr(alerter, "build_recovery_payload", Mock(return_value="recovery-payload"))
    monkeypatch.setattr(
        alerter,
        "send_push_to_all",
        Mock(return_value=PushDeliveryStats(attempted=1, sent=0, removed=1)),
    )
    monkeypatch.setattr(alerter, "log_event", lambda *_args, **_kwargs: None)

    alerter.process_row(conn, row, state, config, "private-key.pem", {"sub": "mailto:test@example.com"})

    assert state == alerter.AlertRuntimeState(last_seen_id=10, in_alert=False, last_alert_ts=900)
