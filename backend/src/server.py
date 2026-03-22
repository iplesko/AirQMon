from dataclasses import asdict
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from pydantic import BaseModel
from typing import Optional
import base64
import os
import time

from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, load_pem_public_key

from db import (
    delete_push_subscription,
    get_conn,
    init_db,
    latest,
    range_query,
    upsert_push_subscription,
)
from paths import DEFAULT_DB_PATH, FRONTEND_DIST_DIR
from runtime_config import RuntimeConfig, persist_runtime_config, read_runtime_config, validate_runtime_config

DEFAULT_POINTS = 500
MAX_POINTS = 10000

DB_PATH = os.getenv('AIRQMON_DB_PATH', str(DEFAULT_DB_PATH))


class ConfigPatchRequest(BaseModel):
    co2_high: int
    co2_clear: int
    cooldown_seconds: int
    display_brightness: Optional[int] = None
    night_mode_enabled: Optional[bool] = None


class PushSubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscriptionRequest(BaseModel):
    endpoint: str
    keys: PushSubscriptionKeys


class PushUnsubscribeRequest(BaseModel):
    endpoint: str


def get_vapid_public_key() -> str:
    key_file = os.getenv('AIRQMON_VAPID_PUBLIC_KEY_FILE', '').strip()
    if not key_file:
        raise HTTPException(status_code=503, detail='AIRQMON_VAPID_PUBLIC_KEY_FILE is not configured')
    if not os.path.isfile(key_file):
        raise HTTPException(status_code=503, detail='VAPID public key file not found')

    with open(key_file, 'rb') as f:
        pem = f.read()

    public_key = load_pem_public_key(pem)
    public_bytes = public_key.public_bytes(
        encoding=Encoding.X962,
        format=PublicFormat.UncompressedPoint,
    )
    return base64.urlsafe_b64encode(public_bytes).rstrip(b'=').decode('ascii')


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


def create_app(*, conn=None, frontend_dist_dir: Optional[Path] = FRONTEND_DIST_DIR) -> FastAPI:
    app = FastAPI()
    db_conn = conn if conn is not None else get_conn(DB_PATH)
    init_db(db_conn)
    app.state.db_conn = db_conn

    @app.middleware('http')
    async def set_static_cache_headers(request: Request, call_next):
        response = await call_next(request)
        path = request.url.path

        if path == '/service-worker.js':
            # Service worker scripts must be revalidated aggressively to pick up updates.
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        elif path in {'/', '/index.html'}:
            # HTML shell should revalidate so clients discover new asset hashes quickly.
            response.headers['Cache-Control'] = 'no-cache, max-age=0, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'

        return response

    @app.get('/api/latest')
    def api_latest():
        row = latest(db_conn)
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

        rows = range_query(db_conn, int(start), int(end))
        rows = sieve_evenly(rows, points)
        return {'data': rows}

    @app.get('/api/config')
    def api_config():
        return asdict(read_runtime_config(db_conn, persist_defaults=True))

    @app.put('/api/config')
    def api_put_config(payload: ConfigPatchRequest):
        current_config = read_runtime_config(db_conn, persist_defaults=True)
        updated_config = RuntimeConfig(
            co2_high=payload.co2_high,
            co2_clear=payload.co2_clear,
            cooldown_seconds=payload.cooldown_seconds,
            display_brightness=current_config.display_brightness if payload.display_brightness is None else payload.display_brightness,
            night_mode_enabled=current_config.night_mode_enabled if payload.night_mode_enabled is None else payload.night_mode_enabled,
        )
        try:
            validate_runtime_config(updated_config)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        persist_runtime_config(db_conn, updated_config)
        return asdict(updated_config)

    @app.get('/api/push/public-key')
    def api_push_public_key():
        return {'public_key': get_vapid_public_key()}

    @app.post('/api/push/subscribe')
    def api_push_subscribe(payload: PushSubscriptionRequest):
        endpoint = payload.endpoint.strip()
        p256dh = payload.keys.p256dh.strip()
        auth = payload.keys.auth.strip()

        if not endpoint or not p256dh or not auth:
            raise HTTPException(status_code=400, detail='endpoint and keys must not be empty')
        if not endpoint.startswith('https://'):
            raise HTTPException(status_code=400, detail='endpoint must use https')

        upsert_push_subscription(db_conn, endpoint, p256dh, auth)
        return {'ok': True}

    @app.post('/api/push/unsubscribe')
    def api_push_unsubscribe(payload: PushUnsubscribeRequest):
        endpoint = payload.endpoint.strip()
        if not endpoint:
            raise HTTPException(status_code=400, detail='endpoint must not be empty')

        deleted = delete_push_subscription(db_conn, endpoint)
        return {'ok': True, 'deleted': deleted > 0}

    frontend_dir = None if frontend_dist_dir is None else Path(frontend_dist_dir)
    # Serve frontend static files from ../frontend/dist (mount after API routes so API works)
    if frontend_dir is not None and frontend_dir.is_dir():
        app.mount('/', StaticFiles(directory=str(frontend_dir), html=True), name='static')

    return app


APP = app = create_app()

