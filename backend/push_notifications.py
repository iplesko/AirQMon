import json
import sys
from dataclasses import dataclass

from pywebpush import WebPushException, webpush

from db import delete_push_subscription, list_push_subscriptions


@dataclass(frozen=True)
class PushDeliveryStats:
    attempted: int
    sent: int
    removed: int

    @property
    def has_remaining_recipients(self) -> bool:
        return (self.attempted - self.removed) > 0


def build_high_payload(reading: dict, high: int) -> str:
    return json.dumps(
        {
            'type': 'co2_high',
            'title': '⚠️ AirQMon: High CO2 Alert',
            'body': (
                f"CO2 is high: {reading['co2']:.0f} ppm "
                f"(threshold {high:.0f} ppm). "
                f"Temp {reading['temperature']:.1f} C, humidity {reading['humidity']:.1f}%."
            ),
            'ts': int(reading['ts']),
            'url': '/',
        }
    )


def build_recovery_payload(reading: dict, clear: int) -> str:
    return json.dumps(
        {
            'type': 'co2_recovery',
            'title': '✅ AirQMon: CO2 Normalized',
            'body': (
                f"CO2 is back to normal: {reading['co2']:.0f} ppm "
                f"(clear threshold {clear:.0f} ppm). "
                f"Temp {reading['temperature']:.1f} C, humidity {reading['humidity']:.1f}%."
            ),
            'ts': int(reading['ts']),
            'url': '/',
        }
    )


def send_push_to_all(conn, payload: str, vapid_private_key: str, vapid_claims: dict) -> PushDeliveryStats:
    subscriptions = list_push_subscriptions(conn)
    attempted = len(subscriptions)
    sent = 0
    removed = 0

    for subscription in subscriptions:
        subscription_info = {
            'endpoint': subscription['endpoint'],
            'keys': {
                'p256dh': subscription['p256dh'],
                'auth': subscription['auth'],
            },
        }

        try:
            webpush(
                subscription_info=subscription_info,
                data=payload,
                vapid_private_key=vapid_private_key,
                vapid_claims=vapid_claims,
                ttl=3600,
            )
            sent += 1
        except WebPushException as exc:
            status_code = getattr(exc.response, 'status_code', None)
            if status_code in (404, 410):
                delete_push_subscription(conn, subscription['endpoint'])
                removed += 1
            print(f"Failed to send push to endpoint {subscription['endpoint']}: {exc}", file=sys.stderr)

    return PushDeliveryStats(attempted=attempted, sent=sent, removed=removed)
