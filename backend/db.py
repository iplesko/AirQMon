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
