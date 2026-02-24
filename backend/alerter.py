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


def handle_sig(signum, frame):
    global running
    running = False


def env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f'Invalid float in {name}: {raw}') from exc


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f'Invalid int in {name}: {raw}') from exc


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', default=os.path.join(os.path.dirname(__file__), 'data.db'))
    parser.add_argument('--poll-interval', type=float, default=env_float('ALERTER_POLL_INTERVAL', 5.0))
    parser.add_argument('--co2-high', type=float, default=env_float('ALERTER_CO2_HIGH', 1500.0))
    parser.add_argument('--co2-clear', type=float, default=env_float('ALERTER_CO2_CLEAR', 500.0))
    parser.add_argument('--cooldown-seconds', type=int, default=env_int('ALERTER_COOLDOWN_SECONDS', 1800))
    return parser.parse_args()


def ensure_ntfy_topic(conn) -> tuple[str, bool]:
    topic = get_state(conn, 'alert:ntfy_topic')
    if topic:
        return topic, False

    alphabet = string.ascii_lowercase + string.digits
    random_part = ''.join(secrets.choice(alphabet) for _ in range(12))
    topic = f'airqmon-{random_part}'
    set_state(conn, 'alert:ntfy_topic', topic)
    return topic, True


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


def send_ntfy(base_url: str, topic: str, body: str, title: str, priority: str, tags: str) -> None:
    url = f"{base_url.rstrip('/')}/{topic}"
    req = urllib.request.Request(url=url, data=body.encode('utf-8'), method='POST')
    req.add_header('Title', title)
    req.add_header('Priority', priority)
    req.add_header('Tags', tags)
    req.add_header('Content-Type', 'text/plain; charset=utf-8')
    with urllib.request.urlopen(req, timeout=10) as resp:
        resp.read()


def send_alert(base_url: str, topic: str, reading: dict, high: float) -> None:
    body = (
        f"CO2 is high: {reading['co2']:.0f} ppm\n"
        f"Threshold: {high:.0f} ppm\n"
        f"Temp: {reading['temperature']:.1f} C\n"
        f"Humidity: {reading['humidity']:.1f}%\n"
        f"At: {datetime.fromtimestamp(reading['ts']).isoformat()}"
    )
    send_ntfy(base_url, topic, body, 'AirQMon: High CO2', NTFY_PRIORITY, 'warning,wind_face')


def send_recovery(base_url: str, topic: str, reading: dict, clear: float) -> None:
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
    if args.co2_clear >= args.co2_high:
        print('--co2-clear must be lower than --co2-high', file=sys.stderr)
        sys.exit(2)

    conn = get_conn(args.db)
    init_db(conn)
    ntfy_topic, created_topic = ensure_ntfy_topic(conn)

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
                'co2_high': args.co2_high,
                'co2_clear': args.co2_clear,
                'cooldown_seconds': args.cooldown_seconds,
                'ntfy_url': NTFY_BASE_URL,
                'ntfy_topic': ntfy_topic,
            }
        )
    )
    if created_topic:
        print(f'Generated ntfy topic: {ntfy_topic}')
    else:
        print(f'Using ntfy topic: {ntfy_topic}')

    try:
        while running:
            rows = query_after_id(conn, last_id)
            if not rows:
                time.sleep(args.poll_interval)
                continue

            for row in rows:
                last_id = row['id']
                ts = int(row['ts'])
                co2 = float(row['co2'])

                should_send_high = False
                if not in_alert and co2 >= args.co2_high:
                    if ts - last_alert_ts >= args.cooldown_seconds:
                        should_send_high = True

                if should_send_high:
                    try:
                        send_alert(
                            NTFY_BASE_URL,
                            ntfy_topic,
                            row,
                            args.co2_high,
                        )
                        in_alert = True
                        last_alert_ts = ts
                        print(json.dumps({'event': 'alert_sent', 'id': row['id'], 'co2': co2, 'ts': ts}))
                    except urllib.error.URLError as exc:
                        print(f'Failed to send ntfy alert: {exc}', file=sys.stderr)

                if in_alert and co2 <= args.co2_clear:
                    try:
                        send_recovery(
                            NTFY_BASE_URL,
                            ntfy_topic,
                            row,
                            args.co2_clear,
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
