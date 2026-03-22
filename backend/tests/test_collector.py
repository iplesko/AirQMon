from __future__ import annotations

import collector
from db import latest, range_query


def test_collect_once_inserts_measurement_and_keeps_recent_prune_time(conn, capsys) -> None:
    last_prune, collected = collector.collect_once(
        conn,
        last_prune=5_000,
        ts=5_000,
        read_sensor=lambda: (800.0, 22.5, 45.0),
    )

    captured = capsys.readouterr()
    row = latest(conn)

    assert collected is True
    assert last_prune == 5_000
    assert row is not None
    assert row["ts"] == 5_000
    assert row["co2"] == 800.0
    assert "co2=800.0ppm" in captured.out


def test_collect_once_prunes_when_interval_has_elapsed(conn, monkeypatch, capsys) -> None:
    prune_calls: list[object] = []

    def fake_prune(passed_conn):
        prune_calls.append(passed_conn)
        return 2

    monkeypatch.setattr(collector, "prune_old_measurements", fake_prune)

    last_prune, collected = collector.collect_once(
        conn,
        last_prune=1_000,
        ts=1_000 + collector.PRUNE_EVERY_SECONDS,
        read_sensor=lambda: (900.0, 23.0, 46.0),
    )

    captured = capsys.readouterr()

    assert collected is True
    assert last_prune == 1_000 + collector.PRUNE_EVERY_SECONDS
    assert prune_calls == [conn]
    assert "Pruned 2 rows older than 7 days" in captured.out


def test_collect_once_skips_prune_when_window_not_elapsed(conn, monkeypatch) -> None:
    prune_calls: list[object] = []

    monkeypatch.setattr(
        collector,
        "prune_old_measurements",
        lambda passed_conn: prune_calls.append(passed_conn),
    )

    last_prune, collected = collector.collect_once(
        conn,
        last_prune=2_000,
        ts=2_100,
        read_sensor=lambda: (700.0, 21.0, 40.0),
    )

    assert collected is True
    assert last_prune == 2_000
    assert prune_calls == []


def test_collect_once_reports_sensor_errors_without_inserting(conn, capsys) -> None:
    def failing_read():
        raise RuntimeError("sensor offline")

    last_prune, collected = collector.collect_once(
        conn,
        last_prune=123,
        ts=5_000,
        read_sensor=failing_read,
    )

    captured = capsys.readouterr()

    assert collected is False
    assert last_prune == 123
    assert range_query(conn, 0, 10_000) == []
    assert "Sensor read error: sensor offline" in captured.err
