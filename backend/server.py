from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from typing import Optional
import os
import time

from db import get_conn, init_db, latest, range_query

APP = app = FastAPI()
DEFAULT_POINTS = 500
MAX_POINTS = 10000

BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, 'data.db')

conn = get_conn(DB_PATH)
init_db(conn)
 


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
