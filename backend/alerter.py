#!/usr/bin/env python3
"""Alert worker: watches DB for new readings and pushes ntfy notifications."""
import argparse
import json
import os
import secrets
import signal
import string
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import Optional

from db import get_conn, get_state, init_db, query_after_id, set_state

running = True
NTFY_BASE_URL = 'https://ntfy.sh'
NTFY_PRIORITY = '3'
DEFAULT_POLL_INTERVAL = 5.0
DEFAULT_CO2_HIGH = 1500
DEFAULT_CO2_CLEAR = 500
DEFAULT_COOLDOWN_SECONDS = 1800


def handle_sig(signum, frame):
    global running
    running = False


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', default=os.path.join(os.path.dirname(__file__), 'data.db'))
    parser.add_argument('--poll-interval', type=float, default=DEFAULT_POLL_INTERVAL)
    return parser.parse_args()


def ensure_ntfy_topic(conn) -> str:
    topic = get_state(conn, 'alert:ntfy_topic')
    if topic:
        return topic

    alphabet = string.ascii_lowercase + string.digits
    random_part = ''.join(secrets.choice(alphabet) for _ in range(12))
    topic = f'airqmon-{random_part}'
    set_state(conn, 'alert:ntfy_topic', topic)
    return topic


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


def ensure_alert_config(conn) -> tuple[int, int, int]:
    co2_high_raw = get_state(conn, 'alert:co2_high')
    co2_clear_raw = get_state(conn, 'alert:co2_clear')
    cooldown_raw = get_state(conn, 'alert:cooldown_seconds')

    co2_high = int_from_state(co2_high_raw, DEFAULT_CO2_HIGH)
    co2_clear = int_from_state(co2_clear_raw, DEFAULT_CO2_CLEAR)
    cooldown_seconds = int_from_state(cooldown_raw, DEFAULT_COOLDOWN_SECONDS)

    if co2_high_raw is None:
        set_state(conn, 'alert:co2_high', str(co2_high))
    if co2_clear_raw is None:
        set_state(conn, 'alert:co2_clear', str(co2_clear))
    if cooldown_raw is None:
        set_state(conn, 'alert:cooldown_seconds', str(cooldown_seconds))

    return co2_high, co2_clear, cooldown_seconds


def ensure_runtime_config(conn) -> tuple[str, int, int, int]:
    ntfy_topic = ensure_ntfy_topic(conn)
    co2_high, co2_clear, cooldown_seconds = ensure_alert_config(conn)
    if co2_clear >= co2_high:
        raise ValueError('Configured co2_clear must be lower than co2_high')
    return ntfy_topic, co2_high, co2_clear, cooldown_seconds


def send_ntfy(base_url: str, topic: str, body: str, title: str, priority: str, tags: str) -> None:
    url = f"{base_url.rstrip('/')}/{topic}"
    req = urllib.request.Request(url=url, data=body.encode('utf-8'), method='POST')
    req.add_header('Title', title)
    req.add_header('Priority', priority)
    req.add_header('Tags', tags)
    req.add_header('Content-Type', 'text/plain; charset=utf-8')
    with urllib.request.urlopen(req, timeout=10) as resp:
        resp.read()


def send_alert(base_url: str, topic: str, reading: dict, high: int) -> None:
    body = (
        f"CO2 is high: {reading['co2']:.0f} ppm\n"
        f"Threshold: {high:.0f} ppm\n"
        f"Temp: {reading['temperature']:.1f} C\n"
        f"Humidity: {reading['humidity']:.1f}%\n"
        f"At: {datetime.fromtimestamp(reading['ts']).isoformat()}"
    )
    send_ntfy(base_url, topic, body, 'AirQMon: High CO2', NTFY_PRIORITY, 'warning,wind_face')


def send_recovery(base_url: str, topic: str, reading: dict, clear: int) -> None:
    body = (
        f"CO2 back to normal: {reading['co2']:.0f} ppm\n"
        f"Clear threshold: {clear:.0f} ppm\n"
        f"Temp: {reading['temperature']:.1f} C\n"
        f"Humidity: {reading['humidity']:.1f}%\n"
        f"At: {datetime.fromtimestamp(reading['ts']).isoformat()}"
    )
    send_ntfy(base_url, topic, body, 'AirQMon: CO2 Normalized', NTFY_PRIORITY, 'white_check_mark,wind_face')


def main():
    args = parse_args()

    conn = get_conn(args.db)
    init_db(conn)
    try:
        ntfy_topic, co2_high, co2_clear, cooldown_seconds = ensure_runtime_config(conn)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(2)

    signal.signal(signal.SIGINT, handle_sig)
    signal.signal(signal.SIGTERM, handle_sig)

    last_id = int_from_state(get_state(conn, 'alert:last_seen_id'), 0)
    in_alert = bool_from_state(get_state(conn, 'alert:in_alert'), False)
    last_alert_ts = int_from_state(get_state(conn, 'alert:last_alert_ts'), 0)

    print(
        json.dumps(
            {
                'event': 'alerter_started',
                'db': args.db,
                'poll_interval': args.poll_interval,
                'co2_high': co2_high,
                'co2_clear': co2_clear,
                'cooldown_seconds': cooldown_seconds,
                'ntfy_url': NTFY_BASE_URL,
                'ntfy_topic': ntfy_topic,
            }
        )
    )
    print(
        'Using config:\n'
        f'  ntfy_topic={ntfy_topic}\n'
        f'  co2_high={co2_high}\n'
        f'  co2_clear={co2_clear}\n'
        f'  cooldown_seconds={cooldown_seconds}'
    )

    try:
        while running:
            try:
                ntfy_topic, co2_high, co2_clear, cooldown_seconds = ensure_runtime_config(conn)
            except ValueError as exc:
                print(str(exc), file=sys.stderr)
                time.sleep(args.poll_interval)
                continue

            rows = query_after_id(conn, last_id)
            if not rows:
                time.sleep(args.poll_interval)
                continue

            for row in rows:
                last_id = row['id']
                ts = int(row['ts'])
                co2 = float(row['co2'])

                should_send_high = False
                if not in_alert and co2 >= co2_high:
                    if ts - last_alert_ts >= cooldown_seconds:
                        should_send_high = True

                if should_send_high:
                    try:
                        send_alert(
                            NTFY_BASE_URL,
                            ntfy_topic,
                            row,
                            co2_high,
                        )
                        in_alert = True
                        last_alert_ts = ts
                        print(json.dumps({'event': 'alert_sent', 'id': row['id'], 'co2': co2, 'ts': ts}))
                    except urllib.error.URLError as exc:
                        print(f'Failed to send ntfy alert: {exc}', file=sys.stderr)

                if in_alert and co2 <= co2_clear:
                    try:
                        send_recovery(
                            NTFY_BASE_URL,
                            ntfy_topic,
                            row,
                            co2_clear,
                        )
                        in_alert = False
                        print(json.dumps({'event': 'recovery_sent', 'id': row['id'], 'co2': co2, 'ts': ts}))
                    except urllib.error.URLError as exc:
                        print(f'Failed to send ntfy recovery: {exc}', file=sys.stderr)

            set_state(conn, 'alert:last_seen_id', str(last_id))
            set_state(conn, 'alert:in_alert', '1' if in_alert else '0')
            set_state(conn, 'alert:last_alert_ts', str(last_alert_ts))
    finally:
        conn.close()
        print('Alerter stopped')


if __name__ == '__main__':
    main()
