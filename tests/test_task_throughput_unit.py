from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from library.api.routes_tasks import _task_throughput_payload


def test_task_throughput_payload_reports_backlog_failures_and_durations() -> None:
    now = datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc)
    active = [
        SimpleNamespace(
            kind="ingest_file",
            status="pending",
            scheduled_at=now - timedelta(seconds=90),
        ),
        SimpleNamespace(
            kind="reprocess_file",
            status="running",
            scheduled_at=now - timedelta(seconds=30),
        ),
    ]
    terminal = [
        SimpleNamespace(
            kind="ingest_file",
            status="done",
            started_at=now - timedelta(seconds=20),
            finished_at=now - timedelta(seconds=10),
        ),
        SimpleNamespace(
            kind="ingest_file",
            status="dead",
            started_at=now - timedelta(seconds=8),
            finished_at=now - timedelta(seconds=4),
        ),
    ]

    payload = _task_throughput_payload(
        active=active,  # type: ignore[arg-type]
        terminal=terminal,  # type: ignore[arg-type]
        now=now,
        window_minutes=60,
    )

    assert payload["queue"] == {
        "pending": 1,
        "running": 1,
        "total": 2,
        "oldest_pending_age_seconds": 90,
    }
    assert payload["completed"]["done"] == 1
    assert payload["completed"]["failed"] == 1
    assert payload["completed"]["success_rate"] == 0.5
    ingest = payload["by_kind"][0]
    assert ingest["average_duration_seconds"] == 7.0


def test_task_throughput_classifies_reprocess_from_ingest_payload() -> None:
    now = datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc)
    terminal = [
        SimpleNamespace(
            kind="ingest_file",
            status="done",
            payload={"file_id": "f1", "scheduled_by": "api:single"},
            started_at=now - timedelta(seconds=5),
            finished_at=now,
        ),
        SimpleNamespace(
            kind="ingest_file",
            status="done",
            payload={"file_id": "f2"},
            started_at=now - timedelta(seconds=4),
            finished_at=now,
        ),
    ]

    payload = _task_throughput_payload(
        active=[],
        terminal=terminal,  # type: ignore[arg-type]
        now=now,
        window_minutes=60,
    )

    by_kind = {row["kind"]: row for row in payload["by_kind"]}
    assert by_kind["reprocess_file"]["done"] == 1
    assert by_kind["ingest_file"]["done"] == 1
