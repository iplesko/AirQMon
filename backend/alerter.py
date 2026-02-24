#!/usr/bin/env python3
"""Alert worker: watches DB for new readings and pushes Web Push notifications."""
import argparse
import json
import os
import signal
import sys
import time

from alert_runtime import (
    AlertConfig,
    AlertRuntimeState,
    ensure_runtime_config,
    load_runtime_state,
    persist_runtime_state,
)
from db import get_conn, init_db, query_after_id
from push_notifications import build_high_payload, build_recovery_payload, send_push_to_all

running = True
DEFAULT_POLL_INTERVAL = 5.0


def handle_sig(signum, frame):
    global running
    running = False


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', default=os.path.join(os.path.dirname(__file__), 'data.db'))
    parser.add_argument('--poll-interval', type=float, default=DEFAULT_POLL_INTERVAL)
    return parser.parse_args()


def get_vapid_credentials() -> tuple[str, dict]:
    private_key = os.getenv('AIRQMON_VAPID_PRIVATE_KEY_FILE', '').strip()
    subject = os.getenv('AIRQMON_VAPID_SUBJECT', '').strip()
    if not private_key:
        raise RuntimeError('AIRQMON_VAPID_PRIVATE_KEY_FILE is not configured')
    if not os.path.isfile(private_key):
        raise RuntimeError('AIRQMON_VAPID_PRIVATE_KEY_FILE does not point to an existing file')
    if not subject:
        raise RuntimeError('AIRQMON_VAPID_SUBJECT is not configured')
    return private_key, {'sub': subject}


def log_event(event: str, **fields) -> None:
    print(json.dumps({'event': event, **fields}))


def should_send_high_alert(ts: int, co2: float, state: AlertRuntimeState, config: AlertConfig) -> bool:
    if state.in_alert:
        return False
    if co2 < config.co2_high:
        return False
    return ts - state.last_alert_ts >= config.cooldown_seconds


def process_row(conn, row: dict, state: AlertRuntimeState, config: AlertConfig, vapid_private_key: str, vapid_claims: dict) -> None:
    state.last_seen_id = row['id']
    ts = int(row['ts'])
    co2 = float(row['co2'])

    if should_send_high_alert(ts, co2, state, config):
        payload = build_high_payload(row, config.co2_high)
        stats = send_push_to_all(conn, payload, vapid_private_key, vapid_claims)
        if stats.sent > 0:
            state.in_alert = True
            state.last_alert_ts = ts
            log_event(
                'alert_sent',
                id=row['id'],
                co2=co2,
                ts=ts,
                push_sent=stats.sent,
                push_attempted=stats.attempted,
                subscriptions_removed=stats.removed,
            )
        else:
            log_event(
                'alert_not_sent',
                id=row['id'],
                co2=co2,
                ts=ts,
                push_sent=stats.sent,
                push_attempted=stats.attempted,
                subscriptions_removed=stats.removed,
            )

    if state.in_alert and co2 <= config.co2_clear:
        payload = build_recovery_payload(row, config.co2_clear)
        stats = send_push_to_all(conn, payload, vapid_private_key, vapid_claims)
        if stats.sent > 0 or not stats.has_remaining_recipients:
            state.in_alert = False
        log_event(
            'recovery_sent',
            id=row['id'],
            co2=co2,
            ts=ts,
            push_sent=stats.sent,
            push_attempted=stats.attempted,
            subscriptions_removed=stats.removed,
            in_alert_after=state.in_alert,
        )


def main():
    args = parse_args()

    conn = get_conn(args.db)
    init_db(conn)
    try:
        config = ensure_runtime_config(conn)
        vapid_private_key, vapid_claims = get_vapid_credentials()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(2)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(2)

    signal.signal(signal.SIGINT, handle_sig)
    signal.signal(signal.SIGTERM, handle_sig)

    state = load_runtime_state(conn)

    log_event(
        'alerter_started',
        db=args.db,
        poll_interval=args.poll_interval,
        co2_high=config.co2_high,
        co2_clear=config.co2_clear,
        cooldown_seconds=config.cooldown_seconds,
    )
    print(
        'Using config:\n'
        f'  co2_high={config.co2_high}\n'
        f'  co2_clear={config.co2_clear}\n'
        f'  cooldown_seconds={config.cooldown_seconds}'
    )

    try:
        while running:
            try:
                config = ensure_runtime_config(conn)
            except ValueError as exc:
                print(str(exc), file=sys.stderr)
                time.sleep(args.poll_interval)
                continue

            rows = query_after_id(conn, state.last_seen_id)
            if not rows:
                time.sleep(args.poll_interval)
                continue

            for row in rows:
                process_row(conn, row, state, config, vapid_private_key, vapid_claims)

            persist_runtime_state(conn, state)
    finally:
        conn.close()
        print('Alerter stopped')


if __name__ == '__main__':
    main()
