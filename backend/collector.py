#!/usr/bin/env python3
"""Data collector: reads sensor and writes to SQLite periodically."""
import time
import argparse
import os
import signal
import sys
from datetime import datetime

from db import get_conn, init_db, insert_measurement, prune_old_measurements
from sensor import read

running = True
PRUNE_EVERY_SECONDS = 3600

def handle_sig(signum, frame):
    global running
    running = False

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', default=os.path.join(os.path.dirname(__file__), 'data.db'))
    parser.add_argument('--interval', type=float, default=10.0, help='seconds between measurements')
    args = parser.parse_args()

    conn = get_conn(args.db)
    init_db(conn)
    last_prune = 0

    signal.signal(signal.SIGINT, handle_sig)
    signal.signal(signal.SIGTERM, handle_sig)

    print('Starting collector, writing to', args.db)
    try:
        while running:
            ts = int(time.time())
            try:
                co2, temp, hum = read()
            except Exception as e:
                print('Sensor read error:', e, file=sys.stderr)
                time.sleep(args.interval)
                continue

            insert_measurement(conn, ts, co2, temp, hum)

            if ts - last_prune >= PRUNE_EVERY_SECONDS:
                deleted = prune_old_measurements(conn)
                if deleted:
                    print(f'Pruned {deleted} rows older than 7 days')
                last_prune = ts

            print(f'{datetime.fromtimestamp(ts).isoformat()}  co2={co2}ppm  temp={temp}C  hum={hum}%')
            slept = 0.0
            while running and slept < args.interval:
                time.sleep(0.5)
                slept += 0.5
    finally:
        conn.close()
        print('Collector stopped')

if __name__ == '__main__':
    main()
