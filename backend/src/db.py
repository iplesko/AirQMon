import sqlite3
import time
from typing import List, Dict, Optional

SCHEMA = '''
CREATE TABLE IF NOT EXISTS measurements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    co2 REAL,
    temperature REAL,
    humidity REAL
);
CREATE INDEX IF NOT EXISTS idx_measurements_ts ON measurements(ts);
CREATE TABLE IF NOT EXISTS kv_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS push_subscriptions (
    endpoint TEXT PRIMARY KEY,
    p256dh TEXT NOT NULL,
    auth TEXT NOT NULL,
    created_ts INTEGER NOT NULL,
    updated_ts INTEGER NOT NULL
);
'''

def get_conn(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()

def insert_measurement(conn: sqlite3.Connection, ts: int, co2: float, temperature: float, humidity: float) -> int:
    cur = conn.cursor()
    cur.execute('INSERT INTO measurements (ts, co2, temperature, humidity) VALUES (?, ?, ?, ?)', (ts, co2, temperature, humidity))
    conn.commit()
    return cur.lastrowid

def prune_old_measurements(conn: sqlite3.Connection, keep_seconds: int = 7 * 24 * 3600) -> int:
    cutoff = int(time.time()) - keep_seconds
    cur = conn.cursor()
    cur.execute('DELETE FROM measurements WHERE ts < ?', (cutoff,))
    conn.commit()
    return cur.rowcount

def latest(conn: sqlite3.Connection) -> Optional[Dict]:
    cur = conn.cursor()
    row = cur.execute('SELECT * FROM measurements ORDER BY ts DESC LIMIT 1').fetchone()
    return dict(row) if row else None

def range_query(conn: sqlite3.Connection, start_ts: int, end_ts: int) -> List[Dict]:
    cur = conn.cursor()
    rows = cur.execute('SELECT * FROM measurements WHERE ts BETWEEN ? AND ? ORDER BY ts ASC', (start_ts, end_ts)).fetchall()
    return [dict(r) for r in rows]


def query_after_id(conn: sqlite3.Connection, last_id: int, limit: int = 500) -> List[Dict]:
    cur = conn.cursor()
    rows = cur.execute(
        'SELECT * FROM measurements WHERE id > ? ORDER BY id ASC LIMIT ?',
        (last_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def get_state(conn: sqlite3.Connection, key: str, default: Optional[str] = None) -> Optional[str]:
    cur = conn.cursor()
    row = cur.execute('SELECT value FROM kv_state WHERE key = ?', (key,)).fetchone()
    if row is None:
        return default
    return row['value']


def set_state(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        '''
        INSERT INTO kv_state(key, value)
        VALUES(?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        ''',
        (key, value),
    )
    conn.commit()


def upsert_push_subscription(conn: sqlite3.Connection, endpoint: str, p256dh: str, auth: str) -> None:
    now = int(time.time())
    conn.execute(
        '''
        INSERT INTO push_subscriptions(endpoint, p256dh, auth, created_ts, updated_ts)
        VALUES(?, ?, ?, ?, ?)
        ON CONFLICT(endpoint) DO UPDATE SET
            p256dh = excluded.p256dh,
            auth = excluded.auth,
            updated_ts = excluded.updated_ts
        ''',
        (endpoint, p256dh, auth, now, now),
    )
    conn.commit()


def delete_push_subscription(conn: sqlite3.Connection, endpoint: str) -> int:
    cur = conn.cursor()
    cur.execute('DELETE FROM push_subscriptions WHERE endpoint = ?', (endpoint,))
    conn.commit()
    return cur.rowcount


def list_push_subscriptions(conn: sqlite3.Connection) -> List[Dict]:
    cur = conn.cursor()
    rows = cur.execute(
        '''
        SELECT endpoint, p256dh, auth, created_ts, updated_ts
        FROM push_subscriptions
        ORDER BY updated_ts DESC
        '''
    ).fetchall()
    return [dict(r) for r in rows]
