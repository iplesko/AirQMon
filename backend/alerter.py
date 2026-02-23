#!/usr/bin/env python3
"""Alert worker: watches DB for new readings and pushes ntfy notifications."""
import argparse
import json
import os
import signal
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import Optional

from db import get_conn, get_state, init_db, query_after_id, set_state

running = True


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
    parser.add_argument('--repeat-seconds', type=int, default=env_int('ALERTER_REPEAT_SECONDS', 0))
    parser.add_argument('--ntfy-url', default=os.getenv('NTFY_URL', 'https://ntfy.sh'))
    parser.add_argument('--ntfy-topic', default=os.getenv('NTFY_TOPIC'))
    parser.add_argument('--ntfy-token', default=os.getenv('NTFY_TOKEN'))
    parser.add_argument('--ntfy-priority-high', default=os.getenv('NTFY_PRIORITY_HIGH', '3'))
    parser.add_argument('--ntfy-priority-clear', default=os.getenv('NTFY_PRIORITY_CLEAR', '3'))
    return parser.parse_args()


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


def send_ntfy(base_url: str, topic: str, token: Optional[str], body: str, title: str, priority: str, tags: str) -> None:
    url = f"{base_url.rstrip('/')}/{topic}"
    req = urllib.request.Request(url=url, data=body.encode('utf-8'), method='POST')
    req.add_header('Title', title)
    req.add_header('Priority', priority)
    req.add_header('Tags', tags)
    req.add_header('Content-Type', 'text/plain; charset=utf-8')
    if token:
        req.add_header('Authorization', f'Bearer {token}')
    with urllib.request.urlopen(req, timeout=10) as resp:
        resp.read()


def send_alert(base_url: str, topic: str, token: Optional[str], reading: dict, high: float, priority: str) -> None:
    body = (
        f"CO2 is high: {reading['co2']:.0f} ppm\n"
        f"Threshold: {high:.0f} ppm\n"
        f"Temp: {reading['temperature']:.1f} C\n"
        f"Humidity: {reading['humidity']:.1f}%\n"
        f"At: {datetime.fromtimestamp(reading['ts']).isoformat()}"
    )
    send_ntfy(base_url, topic, token, body, 'AirQMon: High CO2', priority, 'warning,wind_face')


def send_recovery(base_url: str, topic: str, token: Optional[str], reading: dict, clear: float, priority: str) -> None:
    body = (
        f"CO2 back to normal: {reading['co2']:.0f} ppm\n"
        f"Clear threshold: {clear:.0f} ppm\n"
        f"Temp: {reading['temperature']:.1f} C\n"
        f"Humidity: {reading['humidity']:.1f}%\n"
        f"At: {datetime.fromtimestamp(reading['ts']).isoformat()}"
    )
    send_ntfy(base_url, topic, token, body, 'AirQMon: CO2 Normalized', priority, 'white_check_mark,wind_face')


def main():
    args = parse_args()
    if not args.ntfy_topic:
        print('Missing ntfy topic. Set NTFY_TOPIC or pass --ntfy-topic', file=sys.stderr)
        sys.exit(2)
    if args.co2_clear >= args.co2_high:
        print('--co2-clear must be lower than --co2-high', file=sys.stderr)
        sys.exit(2)

    conn = get_conn(args.db)
    init_db(conn)

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
                'repeat_seconds': args.repeat_seconds,
                'ntfy_url': args.ntfy_url,
                'ntfy_topic': args.ntfy_topic,
            }
        )
    )

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
                elif in_alert and args.repeat_seconds > 0 and co2 >= args.co2_high:
                    if ts - last_alert_ts >= args.repeat_seconds:
                        should_send_high = True

                if should_send_high:
                    try:
                        send_alert(
                            args.ntfy_url,
                            args.ntfy_topic,
                            args.ntfy_token,
                            row,
                            args.co2_high,
                            args.ntfy_priority_high,
                        )
                        in_alert = True
                        last_alert_ts = ts
                        print(json.dumps({'event': 'alert_sent', 'id': row['id'], 'co2': co2, 'ts': ts}))
                    except urllib.error.URLError as exc:
                        print(f'Failed to send ntfy alert: {exc}', file=sys.stderr)

                if in_alert and co2 <= args.co2_clear:
                    try:
                        send_recovery(
                            args.ntfy_url,
                            args.ntfy_topic,
                            args.ntfy_token,
                            row,
                            args.co2_clear,
                            args.ntfy_priority_clear,
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
