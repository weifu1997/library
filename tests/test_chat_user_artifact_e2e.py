"""CHAT-H2: session replay recovers user artifacts; CSV export GET is gated.

Covered here:
  (a) GET /v1/sessions/{id}/messages includes artifacts recovered from
      persisted tool_calls[*].result.__user_only__ (vega_lite + data_export),
      without leaking the server filesystem ``path``;
  (b) GET /v1/conversations/{id}/exports/{filename} serves the CSV when
      that conversation's tool result references the filename;
  (c) path-traversal / non-csv names 404;
  (d) unknown conversation 404.

Run:
    uv run pytest tests/test_chat_user_artifact_e2e.py -q
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

_TEST_PARENT = Path(os.environ.get("LIBRARY_TEST_TMP", Path(__file__).resolve().parent))
_TEST_ROOT = _TEST_PARENT / f"_chat_user_artifact_e2e_data_{os.getpid()}_{uuid4().hex[:8]}"
_TEST_ROOT.mkdir(parents=True)
os.environ["LIBRARY_HOME"] = str(_TEST_ROOT)
os.environ["STORAGE_BACKEND"] = "local"
os.environ["WORKER_ENABLED"] = "false"
os.environ["LLM_DEFAULT_API_KEY"] = "sk-fake"
os.environ["LLM_DEFAULT_MODEL"] = "fake-model"

import httpx
from httpx import ASGITransport

from library.config import get_settings
get_settings.cache_clear()  # type: ignore[attr-defined]

from library.db.engine import get_engine, get_session_factory
from library.db.models import Base, Conversation, Session
from library.main import app
from library.utils.ids import new_id

_CSV_NAME = "qs_artifact1.csv"
_CSV_BODY = "name,role\nalice,engineer\n"
_CHART_SPEC = {
    "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
    "mark": "bar",
    "data": {"values": [{"k": "x", "v": 1}]},
    "encoding": {
        "x": {"field": "k", "type": "nominal"},
        "y": {"field": "v", "type": "quantitative"},
    },
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _create_schema() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _seed() -> dict[str, str]:
    export_dir = Path(get_settings().library_home).expanduser() / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    csv_path = export_dir / _CSV_NAME
    csv_path.write_text(_CSV_BODY, encoding="utf-8-sig")
    # A file on disk that no conversation references — must not be served.
    (export_dir / "qs_unreferenced.csv").write_text("secret\n", encoding="utf-8")

    factory = get_session_factory()
    now = _now()
    async with factory() as s:
        sess = Session(
            id=new_id(), started_at=now, ended_at=None, end_reason=None,
            initiating_user_message="chart?", turn_count=1,
            total_input_tokens=0, total_output_tokens=0, total_cache_read=0,
            total_tool_calls=2, total_llm_calls=0, total_duration_ms=0,
        )
        s.add(sess)
        await s.flush()
        conv = Conversation(
            id=new_id(), session_id=sess.id, turn_index=0,
            started_at=now, ended_at=_now(),
            user_message="chart?",
            agent_response="see chart",
            tool_calls=[
                {
                    "name": "generate_chart",
                    "arguments": {"mark": "bar"},
                    "result": {
                        "ok": True,
                        "chart_id": "ch_abc",
                        "caption": "Counts.",
                        "summary": "chart ch_abc ready",
                        "__user_only__": {
                            "kind": "vega_lite",
                            "chart_id": "ch_abc",
                            "title": "Sample",
                            "caption": "Counts.",
                            "spec": _CHART_SPEC,
                        },
                    },
                    "error": None,
                    "duration_ms": 12,
                },
                {
                    "name": "query_sql",
                    "arguments": {"export_csv": True},
                    "result": {
                        "ok": True,
                        "export": {
                            "filename": _CSV_NAME,
                            "path": str(csv_path),
                            "row_count": 1,
                        },
                        "__user_only__": {
                            "kind": "data_export",
                            "format": "csv",
                            "filename": _CSV_NAME,
                            "path": str(csv_path),
                            "row_count": 1,
                            "truncated": False,
                            "columns": ["name", "role"],
                        },
                    },
                    "error": None,
                    "duration_ms": 8,
                },
            ],
            llm_calls=[],
            total_input_tokens=0, total_output_tokens=0,
            total_tool_calls=2, total_llm_calls=0, total_duration_ms=0,
        )
        s.add(conv)
        await s.commit()
        return {"sid": sess.id, "cid": conv.id, "csv_path": str(csv_path)}


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test",
    )


async def test_session_messages_recovers_user_artifacts() -> None:
    seeded = await _seed()
    async with app.router.lifespan_context(app):
        async with _client() as client:
            r = await client.get(f"/v1/sessions/{seeded['sid']}/messages")
            assert r.status_code == 200, r.text
            turns = r.json()["turns"]
            assert len(turns) == 1, turns
            artifacts = turns[0]["artifacts"]
            assert len(artifacts) == 2, artifacts

            chart = artifacts[0]
            assert chart["kind"] == "vega_lite"
            assert chart["chart_id"] == "ch_abc"
            assert chart["title"] == "Sample"
            assert chart["caption"] == "Counts."
            assert chart["spec"]["mark"] == "bar"
            assert "path" not in chart
            assert "__user_only__" not in chart

            export = artifacts[1]
            assert export == {
                "kind": "data_export",
                "format": "csv",
                "filename": _CSV_NAME,
                "row_count": 1,
                "truncated": False,
                "columns": ["name", "role"],
            }
            assert "path" not in export

            # Replay still does not dump raw tool results onto the GUI.
            for tc in turns[0]["tool_calls"]:
                assert "result" not in tc
                assert "__user_only__" not in tc


async def test_chat_export_download_happy_path() -> None:
    seeded = await _seed()
    async with app.router.lifespan_context(app):
        async with _client() as client:
            r = await client.get(
                f"/v1/conversations/{seeded['cid']}/exports/{_CSV_NAME}",
            )
            assert r.status_code == 200, r.text
            assert "text/csv" in r.headers["content-type"]
            body = r.content.decode("utf-8-sig")
            assert body.startswith("name,role")
            assert "alice,engineer" in body


async def test_chat_export_path_traversal_404() -> None:
    seeded = await _seed()
    async with app.router.lifespan_context(app):
        async with _client() as client:
            cid = seeded["cid"]
            bad_names = (
                quote("../qs_artifact1.csv", safe=""),
                quote("../../etc/passwd", safe=""),
                "not_a_csv.txt",
                "qs_unreferenced.csv",
            )
            for name in bad_names:
                r = await client.get(
                    f"/v1/conversations/{cid}/exports/{name}",
                )
                assert r.status_code == 404, (name, r.status_code, r.text)


async def test_chat_export_unknown_conversation_404() -> None:
    await _seed()
    async with app.router.lifespan_context(app):
        async with _client() as client:
            r = await client.get(
                f"/v1/conversations/{new_id()}/exports/{_CSV_NAME}",
            )
            assert r.status_code == 404, r.text
