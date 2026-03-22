from __future__ import annotations

import base64
from pathlib import Path

from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from db import get_state, insert_measurement, list_push_subscriptions
import runtime_config as runtime
import server


def make_client(conn, frontend_dir: Path | None = None) -> TestClient:
    app = server.create_app(conn=conn, frontend_dist_dir=frontend_dir)
    return TestClient(app)


def test_sieve_evenly_preserves_first_and_last_rows() -> None:
    rows = [{"id": idx} for idx in range(5)]

    result = server.sieve_evenly(rows, 3)

    assert result == [{"id": 0}, {"id": 2}, {"id": 4}]


def test_api_latest_returns_404_without_measurements(conn) -> None:
    with make_client(conn) as client:
        response = client.get("/api/latest")

    assert response.status_code == 404
    assert response.json() == {"detail": "no data"}


def test_api_latest_returns_latest_measurement(conn) -> None:
    insert_measurement(conn, 100, 500.0, 20.0, 40.0)
    insert_measurement(conn, 200, 900.0, 21.5, 45.0)

    with make_client(conn) as client:
        response = client.get("/api/latest")

    assert response.status_code == 200
    assert response.json()["ts"] == 200
    assert response.json()["co2"] == 900.0


def test_api_data_defaults_to_last_day_and_downsamples(conn, monkeypatch) -> None:
    monkeypatch.setattr(server.time, "time", lambda: 100_000)
    insert_measurement(conn, 13_590, 450.0, 20.0, 40.0)
    insert_measurement(conn, 90_000, 500.0, 20.5, 40.5)
    insert_measurement(conn, 95_000, 700.0, 21.0, 41.0)
    insert_measurement(conn, 100_000, 900.0, 22.0, 42.0)

    with make_client(conn) as client:
        response = client.get("/api/data", params={"points": 2})

    assert response.status_code == 200
    assert [row["ts"] for row in response.json()["data"]] == [90_000, 100_000]


def test_api_data_rejects_start_after_end(conn) -> None:
    with make_client(conn) as client:
        response = client.get("/api/data", params={"start": 20, "end": 10})

    assert response.status_code == 400
    assert response.json() == {"detail": "start must be <= end"}


def test_api_config_returns_defaults_and_persists_them(conn) -> None:
    with make_client(conn) as client:
        response = client.get("/api/config")

    assert response.status_code == 200
    assert response.json() == {
        "co2_high": runtime.DEFAULT_CO2_HIGH,
        "co2_clear": runtime.DEFAULT_CO2_CLEAR,
        "cooldown_seconds": runtime.DEFAULT_COOLDOWN_SECONDS,
        "display_brightness": runtime.DEFAULT_DISPLAY_BRIGHTNESS,
        "night_mode_enabled": runtime.DEFAULT_NIGHT_MODE_ENABLED,
    }
    assert get_state(conn, runtime.CONFIG_KEY_CO2_HIGH) == str(runtime.DEFAULT_CO2_HIGH)


def test_api_put_config_updates_values_and_preserves_optional_display_fields(conn) -> None:
    with make_client(conn) as client:
        response = client.put(
            "/api/config",
            json={
                "co2_high": 1200,
                "co2_clear": 800,
                "cooldown_seconds": 900,
            },
        )
        follow_up = client.get("/api/config")

    assert response.status_code == 200
    assert response.json() == {
        "co2_high": 1200,
        "co2_clear": 800,
        "cooldown_seconds": 900,
        "display_brightness": runtime.DEFAULT_DISPLAY_BRIGHTNESS,
        "night_mode_enabled": runtime.DEFAULT_NIGHT_MODE_ENABLED,
    }
    assert follow_up.json() == response.json()


def test_api_put_config_rejects_invalid_runtime_config(conn) -> None:
    with make_client(conn) as client:
        response = client.put(
            "/api/config",
            json={
                "co2_high": 1000,
                "co2_clear": 1000,
                "cooldown_seconds": 900,
                "display_brightness": 101,
                "night_mode_enabled": True,
            },
        )

    assert response.status_code == 400
    assert response.json() == {"detail": "co2_clear must be lower than co2_high"}


def test_api_push_public_key_returns_base64_encoded_uncompressed_point(
    conn, test_tmp_dir: Path, monkeypatch
) -> None:
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()
    pem_path = test_tmp_dir / "public.pem"
    pem_path.write_bytes(
        public_key.public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
    )
    expected_public_key = base64.urlsafe_b64encode(
        public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    ).rstrip(b"=").decode("ascii")
    monkeypatch.setenv("AIRQMON_VAPID_PUBLIC_KEY_FILE", str(pem_path))

    with make_client(conn) as client:
        response = client.get("/api/push/public-key")

    assert response.status_code == 200
    assert response.json() == {"public_key": expected_public_key}


def test_api_push_public_key_returns_503_when_not_configured(conn, monkeypatch) -> None:
    monkeypatch.delenv("AIRQMON_VAPID_PUBLIC_KEY_FILE", raising=False)

    with make_client(conn) as client:
        response = client.get("/api/push/public-key")

    assert response.status_code == 503
    assert response.json() == {"detail": "AIRQMON_VAPID_PUBLIC_KEY_FILE is not configured"}


def test_api_push_subscribe_validates_and_upserts_subscriptions(conn) -> None:
    with make_client(conn) as client:
        invalid = client.post(
            "/api/push/subscribe",
            json={
                "endpoint": "http://example.com/push",
                "keys": {"p256dh": "abc", "auth": "def"},
            },
        )
        first = client.post(
            "/api/push/subscribe",
            json={
                "endpoint": "https://example.com/push",
                "keys": {"p256dh": "abc", "auth": "def"},
            },
        )
        second = client.post(
            "/api/push/subscribe",
            json={
                "endpoint": "https://example.com/push",
                "keys": {"p256dh": "updated", "auth": "secret"},
            },
        )

    assert invalid.status_code == 400
    assert invalid.json() == {"detail": "endpoint must use https"}
    assert first.status_code == 200
    assert second.status_code == 200
    assert list_push_subscriptions(conn)[0]["p256dh"] == "updated"
    assert list_push_subscriptions(conn)[0]["auth"] == "secret"


def test_api_push_unsubscribe_reports_whether_subscription_existed(conn) -> None:
    with make_client(conn) as client:
        client.post(
            "/api/push/subscribe",
            json={
                "endpoint": "https://example.com/push",
                "keys": {"p256dh": "abc", "auth": "def"},
            },
        )
        deleted = client.post(
            "/api/push/unsubscribe",
            json={"endpoint": "https://example.com/push"},
        )
        missing = client.post(
            "/api/push/unsubscribe",
            json={"endpoint": "https://example.com/push"},
        )

    assert deleted.status_code == 200
    assert deleted.json() == {"ok": True, "deleted": True}
    assert missing.status_code == 200
    assert missing.json() == {"ok": True, "deleted": False}


def test_static_assets_get_expected_cache_headers(conn, test_tmp_dir: Path) -> None:
    frontend_dir = test_tmp_dir / "frontend-dist"
    frontend_dir.mkdir()
    (frontend_dir / "index.html").write_text("<html>ok</html>", encoding="utf-8")
    (frontend_dir / "service-worker.js").write_text("self.__TEST__ = true;", encoding="utf-8")

    with make_client(conn, frontend_dir=frontend_dir) as client:
        index_response = client.get("/")
        worker_response = client.get("/service-worker.js")

    assert index_response.status_code == 200
    assert index_response.headers["Cache-Control"] == "no-cache, max-age=0, must-revalidate"
    assert worker_response.status_code == 200
    assert worker_response.headers["Cache-Control"] == "no-cache, no-store, must-revalidate"
    assert worker_response.headers["Pragma"] == "no-cache"
    assert worker_response.headers["Expires"] == "0"
