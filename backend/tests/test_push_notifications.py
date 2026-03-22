from __future__ import annotations

import json

import pytest
from pywebpush import WebPushException

from db import list_push_subscriptions, upsert_push_subscription
import push_notifications as push


def make_reading() -> dict[str, float]:
    return {
        "co2": 1525.0,
        "temperature": 23.4,
        "humidity": 44.5,
        "ts": 1_000,
    }


def test_push_delivery_stats_reports_remaining_recipients() -> None:
    assert push.PushDeliveryStats(attempted=3, sent=1, removed=1).has_remaining_recipients is True
    assert push.PushDeliveryStats(attempted=1, sent=0, removed=1).has_remaining_recipients is False


def test_build_high_payload_contains_expected_fields() -> None:
    payload = json.loads(push.build_high_payload(make_reading(), 1500))

    assert payload["type"] == "co2_high"
    assert payload["title"].endswith("AirQMon: High CO2 Alert")
    assert payload["body"] == (
        "CO2 is high: 1525 ppm (threshold 1500 ppm). Temp 23.4 C, humidity 44.5%."
    )
    assert payload["ts"] == 1_000
    assert payload["url"] == "/"


def test_build_recovery_payload_contains_expected_fields() -> None:
    payload = json.loads(push.build_recovery_payload(make_reading(), 700))

    assert payload["type"] == "co2_recovery"
    assert payload["title"].endswith("AirQMon: CO2 Normalized")
    assert payload["body"] == (
        "CO2 is back to normal: 1525 ppm (clear threshold 700 ppm). Temp 23.4 C, humidity 44.5%."
    )
    assert payload["ts"] == 1_000
    assert payload["url"] == "/"


def test_send_push_to_all_sends_to_each_subscription(conn, monkeypatch) -> None:
    upsert_push_subscription(conn, "https://example.com/1", "key-1", "auth-1")
    upsert_push_subscription(conn, "https://example.com/2", "key-2", "auth-2")
    calls: list[dict[str, object]] = []

    def fake_webpush(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(push, "webpush", fake_webpush)

    stats = push.send_push_to_all(
        conn,
        "payload-json",
        "private-key.pem",
        {"sub": "mailto:test@example.com"},
    )

    assert stats == push.PushDeliveryStats(attempted=2, sent=2, removed=0)
    assert len(calls) == 2
    assert calls[0]["data"] == "payload-json"
    assert calls[0]["headers"] == {"Urgency": "high"}
    assert calls[0]["ttl"] == 3600


def test_send_push_to_all_removes_expired_subscriptions(conn, monkeypatch, capsys) -> None:
    expired_endpoint = "https://example.com/expired"
    healthy_endpoint = "https://example.com/healthy"
    upsert_push_subscription(conn, expired_endpoint, "key-1", "auth-1")
    upsert_push_subscription(conn, healthy_endpoint, "key-2", "auth-2")

    def fake_webpush(**kwargs):
        endpoint = kwargs["subscription_info"]["endpoint"]
        if endpoint == expired_endpoint:
            raise WebPushException("gone", response=type("Resp", (), {"status_code": 410})())

    monkeypatch.setattr(push, "webpush", fake_webpush)

    stats = push.send_push_to_all(
        conn,
        "payload-json",
        "private-key.pem",
        {"sub": "mailto:test@example.com"},
    )

    captured = capsys.readouterr()
    endpoints = [row["endpoint"] for row in list_push_subscriptions(conn)]

    assert stats == push.PushDeliveryStats(attempted=2, sent=1, removed=1)
    assert endpoints == [healthy_endpoint]
    assert expired_endpoint in captured.err


def test_send_push_to_all_keeps_subscription_for_non_terminal_errors(conn, monkeypatch, capsys) -> None:
    endpoint = "https://example.com/temporary-error"
    upsert_push_subscription(conn, endpoint, "key-1", "auth-1")

    def fake_webpush(**_kwargs):
        raise WebPushException("temporary", response=type("Resp", (), {"status_code": 503})())

    monkeypatch.setattr(push, "webpush", fake_webpush)

    stats = push.send_push_to_all(
        conn,
        "payload-json",
        "private-key.pem",
        {"sub": "mailto:test@example.com"},
    )

    captured = capsys.readouterr()

    assert stats == push.PushDeliveryStats(attempted=1, sent=0, removed=0)
    assert [row["endpoint"] for row in list_push_subscriptions(conn)] == [endpoint]
    assert endpoint in captured.err


def test_send_push_to_all_handles_empty_subscription_list(conn, monkeypatch) -> None:
    monkeypatch.setattr(
        push,
        "webpush",
        lambda **_kwargs: pytest.fail("webpush should not be called without subscribers"),
    )

    stats = push.send_push_to_all(
        conn,
        "payload-json",
        "private-key.pem",
        {"sub": "mailto:test@example.com"},
    )

    assert stats == push.PushDeliveryStats(attempted=0, sent=0, removed=0)
