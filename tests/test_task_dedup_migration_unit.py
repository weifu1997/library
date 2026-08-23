from __future__ import annotations

import sqlite3

from library.db.bootstrap import COLLAPSE_ACTIVE_TASK_DUPLICATES_SQL


def test_duplicate_task_migration_keeps_the_most_executable_delivery() -> None:
    connection = sqlite3.connect(":memory:")
    connection.executescript(
        """
        CREATE TABLE tasks (
            id TEXT PRIMARY KEY,
            dedup_key TEXT,
            status TEXT NOT NULL,
            attempts INTEGER NOT NULL,
            max_attempts INTEGER NOT NULL,
            lease_expires_at TEXT,
            created_at TEXT NOT NULL,
            finished_at TEXT,
            last_heartbeat_at TEXT,
            locked_by TEXT,
            last_error TEXT
        );

        INSERT INTO tasks VALUES
            ('live-running', 'live-vs-pending', 'running', 5, 5,
             '2026-07-10T13:00:00+00:00', '2026-07-10T10:00:00+00:00',
             NULL, NULL, 'worker-live', NULL),
            ('pending-behind-live', 'live-vs-pending', 'pending', 0, 5,
             NULL, '2026-07-10T09:00:00+00:00', NULL, NULL, NULL, NULL),
            ('healthy-pending', 'pending-vs-retry', 'pending', 1, 5,
             NULL, '2026-07-10T10:00:00+00:00', NULL, NULL, NULL, NULL),
            ('retryable-expired', 'pending-vs-retry', 'running', 2, 5,
             '2026-07-10T11:00:00+00:00', '2026-07-10T09:00:00+00:00',
             NULL, NULL, 'worker-stale', NULL),
            ('retryable-winner', 'retry-vs-exhausted', 'running', 2, 5,
             '2026-07-10T11:00:00+00:00', '2026-07-10T10:00:00+00:00',
             NULL, NULL, 'worker-retry', NULL),
            ('exhausted-expired', 'retry-vs-exhausted', 'running', 5, 5,
             '2026-07-10T11:00:00+00:00', '2026-07-10T09:00:00+00:00',
             NULL, NULL, 'worker-exhausted', NULL),
            ('pending-over-exhausted', 'pending-vs-exhausted', 'pending', 0, 5,
             NULL, '2026-07-10T10:00:00+00:00', NULL, NULL, NULL, NULL),
            ('older-exhausted', 'pending-vs-exhausted', 'running', 5, 5,
             '2026-07-10T11:00:00+00:00', '2026-07-10T09:00:00+00:00',
             NULL, NULL, 'worker-exhausted', NULL);
        """
    )
    now = "2026-07-10T12:00:00+00:00"
    try:
        connection.execute(
            COLLAPSE_ACTIVE_TASK_DUPLICATES_SQL,
            {"now": now, "error": "duplicate active dedup key"},
        )
        rows = list(connection.execute(
            "SELECT id, status, locked_by, lease_expires_at, last_error FROM tasks"
        ))
    finally:
        connection.close()

    active_ids = {row[0] for row in rows if row[1] in {"pending", "running"}}
    assert active_ids == {
        "live-running",
        "healthy-pending",
        "retryable-winner",
        "pending-over-exhausted",
    }
    losers = [row for row in rows if row[1] == "dead"]
    assert all(row[2] is None and row[3] is None for row in losers)
    assert all(row[4] == "duplicate active dedup key" for row in losers)
