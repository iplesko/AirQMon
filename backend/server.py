from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
import os
import time

from db import get_conn, get_state, init_db, latest, range_query, set_state

APP = app = FastAPI()
DEFAULT_POINTS = 500
MAX_POINTS = 10000
DEFAULT_CO2_HIGH = 1500
DEFAULT_CO2_CLEAR = 500
DEFAULT_COOLDOWN_SECONDS = 1800

BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, 'data.db')

conn = get_conn(DB_PATH)
init_db(conn)


def int_from_state(raw: Optional[str], default: int) -> int:
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def read_alert_config():
    return {
        'co2_high': int_from_state(get_state(conn, 'alert:co2_high'), DEFAULT_CO2_HIGH),
        'co2_clear': int_from_state(get_state(conn, 'alert:co2_clear'), DEFAULT_CO2_CLEAR),
        'cooldown_seconds': int_from_state(get_state(conn, 'alert:cooldown_seconds'), DEFAULT_COOLDOWN_SECONDS),
    }


class ConfigPatchRequest(BaseModel):
    ntfy_topic: str
    co2_high: int
    co2_clear: int
    cooldown_seconds: int


@app.get('/api/latest')
def api_latest():
    row = latest(conn)
    if not row:
        raise HTTPException(status_code=404, detail='no data')
    return row


@app.get('/api/data')
def api_data(
    start: Optional[int] = None,
    end: Optional[int] = None,
    points: int = Query(DEFAULT_POINTS, ge=1, le=MAX_POINTS),
):
    now = int(time.time())
    if end is None:
        end = now
    if start is None:
        # default to last 24 hours
        start = end - 24 * 3600
    if start > end:
        raise HTTPException(status_code=400, detail='start must be <= end')

    rows = range_query(conn, int(start), int(end))
    rows = sieve_evenly(rows, points)
    return {'data': rows}


@app.get('/api/config')
def api_config():
    alert_config = read_alert_config()
    return {
        'ntfy_topic': get_state(conn, 'alert:ntfy_topic'),
        'co2_high': alert_config['co2_high'],
        'co2_clear': alert_config['co2_clear'],
        'cooldown_seconds': alert_config['cooldown_seconds'],
    }


@app.put('/api/config')
def api_put_config(payload: ConfigPatchRequest):
    topic = payload.ntfy_topic.strip()
    if not topic:
        raise HTTPException(status_code=400, detail='ntfy_topic must not be empty')
    if payload.co2_clear >= payload.co2_high:
        raise HTTPException(status_code=400, detail='co2_clear must be lower than co2_high')
    if payload.cooldown_seconds < 0:
        raise HTTPException(status_code=400, detail='cooldown_seconds must be >= 0')

    set_state(conn, 'alert:ntfy_topic', topic)
    set_state(conn, 'alert:co2_high', str(payload.co2_high))
    set_state(conn, 'alert:co2_clear', str(payload.co2_clear))
    set_state(conn, 'alert:cooldown_seconds', str(payload.cooldown_seconds))

    alert_config = read_alert_config()
    return {
        'ntfy_topic': topic,
        'co2_high': alert_config['co2_high'],
        'co2_clear': alert_config['co2_clear'],
        'cooldown_seconds': alert_config['cooldown_seconds'],
    }


def sieve_evenly(rows, target_points: int):
    count = len(rows)
    if target_points >= count:
        return rows
    if target_points == 1:
        return [rows[-1]]

    # Pick evenly distributed points and always include first and last.
    last_index = count - 1
    step_count = target_points - 1
    indices = [i * last_index // step_count for i in range(target_points)]
    return [rows[i] for i in indices]


# Serve frontend static files from ../frontend/dist (mount after API routes so API works)
dist_path = os.path.abspath(os.path.join(BASE_DIR, '..', 'frontend', 'dist'))
if os.path.isdir(dist_path):
    app.mount('/', StaticFiles(directory=dist_path, html=True), name='static')

