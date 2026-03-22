from __future__ import annotations

from unittest.mock import patch

import db


def test_init_db_creates_expected_tables(conn) -> None:
    tables = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }

    assert {"measurements", "kv_state", "push_subscriptions"} <= tables


def test_insert_and_latest_return_most_recent_measurement(conn) -> None:
    first_id = db.insert_measurement(conn, 100, 500.0, 21.5, 40.0)
    second_id = db.insert_measurement(conn, 200, 900.0, 23.0, 45.0)

    latest_row = db.latest(conn)

    assert second_id > first_id
    assert latest_row == {
        "id": second_id,
        "ts": 200,
        "co2": 900.0,
        "temperature": 23.0,
        "humidity": 45.0,
    }


def test_range_query_returns_rows_sorted_by_timestamp(conn) -> None:
    db.insert_measurement(conn, 200, 800.0, 22.0, 40.0)
    db.insert_measurement(conn, 100, 600.0, 21.0, 41.0)
    db.insert_measurement(conn, 300, 1000.0, 23.0, 42.0)

    rows = db.range_query(conn, 100, 300)

    assert [row["ts"] for row in rows] == [100, 200, 300]


def test_query_after_id_respects_last_id_and_limit(conn) -> None:
    first_id = db.insert_measurement(conn, 100, 500.0, 21.0, 40.0)
    second_id = db.insert_measurement(conn, 200, 600.0, 22.0, 41.0)
    third_id = db.insert_measurement(conn, 300, 700.0, 23.0, 42.0)

    rows = db.query_after_id(conn, first_id, limit=1)

    assert rows == [
        {
            "id": second_id,
            "ts": 200,
            "co2": 600.0,
            "temperature": 22.0,
            "humidity": 41.0,
        }
    ]
    assert third_id > second_id


def test_prune_old_measurements_deletes_rows_before_cutoff(conn) -> None:
    with patch.object(db.time, "time", return_value=1_000_000):
        db.insert_measurement(conn, 999_700, 550.0, 20.0, 40.0)
        db.insert_measurement(conn, 999_950, 650.0, 21.0, 41.0)

        deleted = db.prune_old_measurements(conn, keep_seconds=100)

    remaining_rows = db.range_query(conn, 0, 2_000_000)

    assert deleted == 1
    assert [row["ts"] for row in remaining_rows] == [999_950]


def test_state_values_can_be_written_and_read_back(conn) -> None:
    assert db.get_state(conn, "missing", "fallback") == "fallback"

    db.set_state(conn, "alert:flag", "1")
    db.set_state(conn, "alert:flag", "0")

    assert db.get_state(conn, "alert:flag") == "0"


def test_push_subscription_upsert_updates_existing_row(conn) -> None:
    endpoint = "https://example.com/push"

    with patch.object(db.time, "time", return_value=100):
        db.upsert_push_subscription(conn, endpoint, "key-1", "auth-1")

    with patch.object(db.time, "time", return_value=200):
        db.upsert_push_subscription(conn, endpoint, "key-2", "auth-2")

    subscriptions = db.list_push_subscriptions(conn)

    assert subscriptions == [
        {
            "endpoint": endpoint,
            "p256dh": "key-2",
            "auth": "auth-2",
            "created_ts": 100,
            "updated_ts": 200,
        }
    ]
    assert db.delete_push_subscription(conn, endpoint) == 1
    assert db.list_push_subscriptions(conn) == []
