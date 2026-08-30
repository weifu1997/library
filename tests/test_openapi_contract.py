"""OpenAPI / response-model contract checks for the MVP allowlist."""
from __future__ import annotations

from fastapi.routing import APIRoute
from pydantic import BaseModel

from library import __version__
from library.api.routes_settings import llm_settings, server_settings
from library.main import app
from library.openapi_export import assert_no_secrets, render
from library.schemas.chat import SSE_EVENT_CATALOG
from library.schemas.settings import (
    LlmModelsResponse,
    LlmProbeVerdict,
    LlmSettingsPutResponse,
    LlmSettingsResponse,
    LlmTestResponse,
    ServerSettingsResponse,
)
from library.schemas.stats import StatsOverviewResponse
from library.schemas.tasks import (
    ActiveTasksResponse,
    RecentTasksResponse,
    RunningCountResponse,
    TaskThroughputResponse,
)
from library.schemas.upload import UploadResponse
from library.schemas.user_files import SearchResponse

MVP_OPERATIONS: tuple[tuple[str, str], ...] = (
    ("/v1/settings/server", "get"),
    ("/v1/settings/llm", "get"),
    ("/v1/settings/llm", "put"),
    ("/v1/settings/llm/test", "post"),
    ("/v1/settings/llm/models", "post"),
    ("/v1/stats/overview", "get"),
    ("/v1/search", "get"),
    ("/v1/upload", "post"),
    ("/v1/tasks/running-count", "get"),
    ("/v1/tasks/active", "get"),
    ("/v1/tasks/recent", "get"),
    ("/v1/tasks/throughput", "get"),
    ("/v1/chat/{session_id}", "post"),
    ("/v1/conversations/{conversation_id}/events", "get"),
    ("/v1/sessions", "post"),
    ("/v1/sessions", "get"),
    ("/v1/sessions/{session_id}/close", "post"),
    ("/v1/sessions/{session_id}", "delete"),
    ("/v1/sessions/{session_id}/messages", "get"),
    ("/v1/folders", "get"),
    ("/v1/folders", "post"),
    ("/v1/folders/{folder_id}", "get"),
    ("/v1/folders/{folder_id}", "patch"),
    ("/v1/folders/{folder_id}", "delete"),
    ("/v1/sync/webdav/status", "get"),
    ("/v1/sync/webdav/config", "put"),
    ("/v1/sync/webdav/test", "post"),
    ("/v1/sync/webdav/remote-status", "post"),
    ("/v1/sync/webdav/publish", "post"),
    ("/v1/sync/webdav/upload-plan", "get"),
    ("/v1/sync/webdav/publish-selected", "post"),
    ("/v1/sync/webdav/pull", "post"),
    ("/v1/sync/webdav/download-plan", "get"),
    ("/v1/sync/webdav/download", "post"),
    ("/v1/sync/webdav/download-selected", "post"),
    ("/v1/sync/webdav/hydrate/{entry_id}", "post"),
)

NO_JSON_BODY = {
    ("/v1/sessions/{session_id}", "delete"),
}

CREATED_OPERATIONS = {
    ("/v1/upload", "post"),
    ("/v1/sessions", "post"),
    ("/v1/folders", "post"),
}

SSE_PATHS = {
    "/v1/chat/{session_id}",
    "/v1/conversations/{conversation_id}/events",
}

# Non-MVP paths may keep additionalProperties:true success bodies.
# This list is the freeze line: adding a precise schema is a later task.
UNTYPED_SUCCESS_PATHS = {
    "/health",
    "/live",
    "/ready",
    "/v1/conversations/latest",
    "/v1/conversations/{conversation_id}/attachments/{name}",
    "/v1/conversations/{conversation_id}/cancel",
    "/v1/conversations/{conversation_id}/export",
    "/v1/conversations/{conversation_id}/export.md",
    "/v1/discover/{entry_id}",
    "/v1/file-entries/{entry_id}",
    "/v1/file-entries/{entry_id}/content",
    "/v1/file-entries/{entry_id}/download",
    "/v1/file-entries/{entry_id}/folder",
    "/v1/file-entries/{entry_id}/lifecycle",
    "/v1/file-entries/{entry_id}/metadata",
    "/v1/file-entries/{entry_id}/name",
    "/v1/file-entries/{entry_id}/path",
    "/v1/file-entries/{entry_id}/preview-text",
    "/v1/files/reprocess",
    "/v1/files/{file_id}/reprocess",
    "/v1/folders/{folder_id}/download",
    "/v1/mcp/tools",
    "/v1/mcp/tools/{name}/call",
    "/v1/semantic-index/rebuild",
    "/v1/semantic-index/status",

    "/v1/tend",
    "/v1/tend/{run_id}",
}


def _spec() -> dict:
    return app.openapi()


def _success_schema(spec: dict, path: str, method: str) -> dict:
    op = spec["paths"][path][method]
    if (path, method) in NO_JSON_BODY:
        return {}
    status = "201" if (path, method) in CREATED_OPERATIONS else "200"
    content = op["responses"][status]["content"]
    return content


def test_openapi_info_version_matches_package() -> None:
    spec = _spec()
    assert spec["info"]["title"] == "Library"
    assert spec["info"]["version"] == __version__


def test_mvp_operations_exist() -> None:
    spec = _spec()
    for path, method in MVP_OPERATIONS:
        assert path in spec["paths"], path
        assert method in spec["paths"][path], (path, method)


def test_mvp_json_success_schemas_are_named() -> None:
    spec = _spec()
    for path, method in MVP_OPERATIONS:
        if path in SSE_PATHS or (path, method) in NO_JSON_BODY:
            continue
        content = _success_schema(spec, path, method)
        schema = content["application/json"]["schema"]
        assert "$ref" in schema or (
            schema.get("type") == "object" and schema.get("title")
            and schema.get("additionalProperties") is not True
        ), (path, method, schema)


def test_sse_routes_are_event_stream() -> None:
    spec = _spec()
    expected_events = {
        "conversation", "planning", "plan", "thinking", "tool_call",
        "tool_result", "user_artifact", "answer", "error", "done", "session",
    }
    assert set(SSE_EVENT_CATALOG) == expected_events
    for path, method in MVP_OPERATIONS:
        if path not in SSE_PATHS:
            continue
        op = spec["paths"][path][method]
        content = _success_schema(spec, path, method)
        assert "text/event-stream" in content, (path, content.keys())
        assert "application/json" not in content, (path, content.keys())
        extra = op.get("x-sse-events") or {}
        assert set(extra) == expected_events
        assert extra["session"]["emitted"] is False
        assert extra["user_artifact"]["emitted"] is True
    sse_routes = [
        route for route in app.routes
        if isinstance(route, APIRoute) and route.path in SSE_PATHS
    ]
    assert {route.path for route in sse_routes} == SSE_PATHS
    for route in sse_routes:
        model = route.response_model
        assert not (isinstance(model, type) and issubclass(model, BaseModel)), (
            route.path, model
        )


def test_untyped_non_mvp_paths_are_frozen() -> None:
    spec = _spec()
    mvp_paths = {path for path, _method in MVP_OPERATIONS}
    actual = set(spec["paths"]) - mvp_paths
    assert actual == UNTYPED_SUCCESS_PATHS


def test_exported_spec_has_no_secret_values() -> None:
    assert_no_secrets(render(_spec()))


def test_server_settings_keyset_matches_model() -> None:
    payload = server_settings()
    assert set(payload) == set(ServerSettingsResponse.model_fields)
    model = ServerSettingsResponse.model_validate(payload)
    dumped = model.model_dump(mode="json")
    assert set(dumped) == set(payload)
    assert "documents" in dumped["semantic_index"]
    assert "section_entries" in dumped["semantic_index"]
    for key, value in dumped.items():
        if isinstance(value, str):
            assert "sk-" not in value
            assert "postgresql+asyncpg://" not in value


def test_llm_settings_profiles_are_not_defaults() -> None:
    payload = llm_settings()
    assert set(payload) == {"profiles", "overlay", "defaults"}
    assert set(payload["profiles"]) == {"chat", "reflect", "ingest", "vision"}
    assert "default" not in payload["profiles"]
    assert "audio" not in payload["profiles"]
    LlmSettingsResponse.model_validate(payload)
    put_only = LlmSettingsPutResponse.model_validate(payload)
    dumped = put_only.model_dump(mode="json")
    assert "worker_error" not in dumped
    assert "reprocessed_failed" not in dumped
    with_extra = LlmSettingsPutResponse.model_validate(
        {**payload, "worker_error": "start/stop failed; see server log"}
    )
    extra_dump = with_extra.model_dump(mode="json")
    assert extra_dump["worker_error"] == "start/stop failed; see server log"
    assert "reprocessed_failed" not in extra_dump


def test_upload_folder_id_may_be_null() -> None:
    body = UploadResponse.model_validate({
        "file_id": "f",
        "entry_id": "e",
        "folder_id": None,
        "display_name": "a.txt",
        "deduped": False,
        "auto_renamed": False,
        "skipped": False,
    }).model_dump(mode="json")
    assert body["folder_id"] is None
    assert set(body) == {
        "file_id", "entry_id", "folder_id", "display_name",
        "deduped", "auto_renamed", "skipped",
    }
    spec = _spec()
    folder_id = spec["components"]["schemas"]["UploadResponse"]["properties"]["folder_id"]
    assert "null" in {item.get("type") for item in folder_id.get("anyOf", [])}


def test_search_schema_has_no_summary() -> None:
    spec = _spec()
    entry = spec["components"]["schemas"]["SearchEntry"]["properties"]
    assert "summary" not in entry
    assert "score" not in entry
    related = spec["components"]["schemas"]["SearchRelatedEntry"]["properties"]
    assert set(related) == {"entry_id", "display_name", "score"}


def test_probe_and_put_variants_omit_unset_keys() -> None:
    success = LlmProbeVerdict.model_validate({
        "ok": True, "model": "m", "provider": "p", "duration_ms": 1.0, "mode": "text",
    }).model_dump(mode="json")
    assert set(success) == {"ok", "model", "provider", "duration_ms", "mode"}

    failure = LlmProbeVerdict.model_validate({
        "ok": False, "error": "x", "duration_ms": 1.0,
    }).model_dump(mode="json")
    assert set(failure) == {"ok", "error", "duration_ms"}

    unconfigured = LlmProbeVerdict.model_validate({
        "ok": None, "configured": False,
    }).model_dump(mode="json")
    assert set(unconfigured) == {"ok", "configured"}

    default_test = LlmTestResponse.model_validate({
        "profiles": {"default": {"ok": True, "model": "m", "provider": "p", "duration_ms": 1.0}},
        "duration_ms": 5.0,
    }).model_dump(mode="json")
    assert set(default_test) == {"profiles", "duration_ms"}
    assert set(default_test["profiles"]) == {"default"}

    models_fail = LlmModelsResponse.model_validate({
        "ok": False, "error": "backup model not configured", "duration_ms": 0.0,
    }).model_dump(mode="json")
    assert set(models_fail) == {"ok", "error", "duration_ms"}


def test_remaining_mvp_models_round_trip_keysets() -> None:
    stats = {
        "totals": {"entries": 1, "folders": 0, "tags": 0},
        "tasks": {"running": 0, "pending": 0},
        "recent": [{
            "entry_id": "e", "display_name": "a.txt", "folder_path": None,
            "created_at": None, "ingest_status": None,
        }],
        "storage_backend": "local",
        "semantic": {"enabled": False, "configured": False, "index_ready": False},
    }
    assert set(StatsOverviewResponse.model_validate(stats).model_dump(mode="json")) == set(stats)

    search = {
        "q": "raft",
        "count": 1,
        "entries": [{
            "entry_id": "e", "display_name": "raft.md", "folder_id": None,
            "folder_path": None, "lifecycle": "active", "mime_type": "text/markdown",
            "size_bytes": 1, "ingest_status": "done", "created_at": None,
            "updated_at": None, "related_entries": [],
        }],
    }
    dumped_search = SearchResponse.model_validate(search).model_dump(mode="json")
    assert set(dumped_search) == set(search)
    assert "summary" not in dumped_search["entries"][0]

    running = {"running": 0, "pending": 1}
    assert set(RunningCountResponse.model_validate(running).model_dump(mode="json")) == set(running)

    active = {
        "running": [{
            "id": "t", "kind": "ingest_file", "label": "a.txt",
            "file_id": None, "entry_id": None, "attempts": 0, "age_s": 1,
        }],
        "pending": [],
    }
    assert set(ActiveTasksResponse.model_validate(active).model_dump(mode="json")) == set(active)

    recent = {
        "items": [{
            "id": "t", "kind": "ingest_file", "status": "done", "label": "a.txt",
            "file_id": None, "entry_id": None, "started_at": None, "finished_at": None,
            "last_error": None, "duration_ms": None, "tokens_in": None,
            "prompt_tokens": None, "tokens_out": None, "cache_read": None,
            "cache_creation": None, "llm_calls": None, "stages_ms": {},
        }],
        "next_cursor": None,
    }
    assert set(RecentTasksResponse.model_validate(recent).model_dump(mode="json")) == set(recent)

    throughput = {
        "window_minutes": 60,
        "since": "2026-01-01T00:00:00+00:00",
        "queue": {"pending": 0, "running": 0, "total": 0, "oldest_pending_age_seconds": 0},
        "completed": {"done": 0, "failed": 0, "success_rate": None, "files_per_minute": 0.0},
        "by_kind": [{
            "kind": "ingest_file", "pending": 0, "running": 0, "done": 0, "failed": 0,
            "oldest_pending_age_seconds": 0, "average_duration_seconds": None,
            "success_rate": None, "completed_per_minute": 0.0,
        }],
    }
    assert set(TaskThroughputResponse.model_validate(throughput).model_dump(mode="json")) == set(throughput)


def test_mvp_error_status_codes_are_documented() -> None:
    spec = _spec()
    expected = {
        ("/v1/settings/server", "get"): {"401"},
        ("/v1/settings/llm", "get"): {"401"},
        ("/v1/settings/llm", "put"): {"401", "422"},
        ("/v1/settings/llm/test", "post"): {"401"},
        ("/v1/settings/llm/models", "post"): {"401", "422"},
        ("/v1/stats/overview", "get"): {"401"},
        ("/v1/search", "get"): {"401", "422"},
        ("/v1/upload", "post"): {"400", "401", "404", "409", "413", "422", "429"},
        ("/v1/tasks/running-count", "get"): {"401"},
        ("/v1/tasks/active", "get"): {"401"},
        ("/v1/tasks/recent", "get"): {"401", "422"},
        ("/v1/tasks/throughput", "get"): {"401"},
        ("/v1/chat/{session_id}", "post"): {"400", "401", "404", "413", "422", "429"},
        ("/v1/conversations/{conversation_id}/events", "get"): {"401", "404", "422"},
        ("/v1/sessions", "post"): {"401"},
        ("/v1/sessions", "get"): {"401", "422"},
        ("/v1/sessions/{session_id}/close", "post"): {"401", "404"},
        ("/v1/sessions/{session_id}", "delete"): {"401", "404"},
        ("/v1/sessions/{session_id}/messages", "get"): {"401", "404"},
        ("/v1/folders", "get"): {"401"},
        ("/v1/folders", "post"): {"400", "401", "404", "409"},
        ("/v1/folders/{folder_id}", "get"): {"401", "404"},
        ("/v1/folders/{folder_id}", "patch"): {"400", "401", "404", "409"},
        ("/v1/folders/{folder_id}", "delete"): {"401", "404", "422"},
        ("/v1/sync/webdav/status", "get"): {"401"},
        ("/v1/sync/webdav/config", "put"): {"401", "422"},
        ("/v1/sync/webdav/test", "post"): {"400", "401", "502"},
        ("/v1/sync/webdav/remote-status", "post"): {"400", "401", "502"},
        ("/v1/sync/webdav/publish", "post"): {"400", "401"},
        ("/v1/sync/webdav/upload-plan", "get"): {"400", "401", "502"},
        ("/v1/sync/webdav/publish-selected", "post"): {"400", "401", "502"},
        ("/v1/sync/webdav/pull", "post"): {"400", "401", "502"},
        ("/v1/sync/webdav/download-plan", "get"): {"400", "401", "502"},
        ("/v1/sync/webdav/download", "post"): {"400", "401", "502"},
        ("/v1/sync/webdav/download-selected", "post"): {"400", "401", "502"},
        ("/v1/sync/webdav/hydrate/{entry_id}", "post"): {"400", "401", "404", "502"},
    }
    for path, method in MVP_OPERATIONS:
        documented = set(spec["paths"][path][method]["responses"]) - {"200", "201", "204"}
        missing = expected[(path, method)] - documented
        assert not missing, (path, method, missing, documented)
        assert "416" not in documented, (path, method)
