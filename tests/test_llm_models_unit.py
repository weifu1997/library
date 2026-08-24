"""Unit tests for `_list_llm_models` — the model-listing helper behind
POST /v1/settings/llm/models.

Locks in: the provider branch (OpenAI family vs Anthropic), the Anthropic
`limit=1000` pagination requirement (the SDK defaults to 20 results),
result sorting, timeout mapping, and api_key redaction in error text.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from library.api import routes_settings as rs


def _model(model_id: str) -> SimpleNamespace:
    # OpenAI `Model` objects only carry `id`; Anthropic also has
    # `display_name`. SimpleNamespace is enough for both.
    return SimpleNamespace(id=model_id, display_name=f"Display {model_id}")


class _Page:
    def __init__(self, data: list[object]) -> None:
        self.data = data


class _FakeModelsResource:
    """Stand-in for the SDK `models` resource. Records kwargs so tests can
    assert `limit=1000` is passed for Anthropic."""

    def __init__(self, models: list[object], *, exc: Exception | None = None) -> None:
        self._models = models
        self._exc = exc
        self.kwargs: dict[str, object] = {}

    async def list(self, **kwargs: object) -> _Page:
        self.kwargs.update(kwargs)
        if self._exc is not None:
            raise self._exc
        return _Page(self._models)


def _patch_client(monkeypatch: pytest.MonkeyPatch, resource: _FakeModelsResource) -> None:
    """Route both provider getters to a fake SDK client sharing `resource`."""
    client = SimpleNamespace(models=resource)

    def _fake_openai(**_kwargs: object) -> object:
        return client

    def _fake_anthropic(**_kwargs: object) -> object:
        return client

    monkeypatch.setattr(rs, "get_openai_compatible_client", _fake_openai)
    monkeypatch.setattr(rs, "get_anthropic_client", _fake_anthropic)


async def test_openai_family_returns_sorted_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    resource = _FakeModelsResource([_model("zebra"), _model("alpha"), _model("mango")])
    _patch_client(monkeypatch, resource)

    res = await rs._list_llm_models("openai", "https://api.openai.com/v1", "sk-secret")

    assert res["ok"] is True
    assert [m["id"] for m in res["models"]] == ["alpha", "mango", "zebra"]
    # OpenAI has no display_name — the helper must not invent one.
    assert all(m["display_name"] is None for m in res["models"])
    assert res["provider"] == "openai"
    assert res["base_url"] == "https://api.openai.com/v1"
    # The OpenAI path must not send the Anthropic `limit` kwarg.
    assert resource.kwargs == {}


async def test_openai_compatible_uses_same_sdk_path(monkeypatch: pytest.MonkeyPatch) -> None:
    resource = _FakeModelsResource([_model("deepseek-chat")])
    _patch_client(monkeypatch, resource)

    res = await rs._list_llm_models(
        "openai-compatible", "http://localhost:11434/v1", "not-a-real-key"
    )

    assert res["ok"] is True
    assert [m["id"] for m in res["models"]] == ["deepseek-chat"]


async def test_anthropic_passes_limit_and_maps_display_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resource = _FakeModelsResource([_model("claude-sonnet-5")])
    _patch_client(monkeypatch, resource)

    res = await rs._list_llm_models("anthropic", "https://api.anthropic.com", "sk-ant-secret")

    assert res["ok"] is True
    # Anthropic's list endpoint defaults to 20 results — fetch the full catalog.
    assert resource.kwargs == {"limit": 1000}
    model = res["models"][0]
    assert model["id"] == "claude-sonnet-5"
    assert model["display_name"] == "Display claude-sonnet-5"


async def test_timeout_maps_to_ok_false(monkeypatch: pytest.MonkeyPatch) -> None:
    resource = _FakeModelsResource([], exc=asyncio.TimeoutError())
    _patch_client(monkeypatch, resource)

    res = await rs._list_llm_models("openai", None, "sk-secret")

    assert res["ok"] is False
    assert res["error"] == "timed out after 15s"


async def test_error_text_redacts_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "sk-super-secret-key"
    resource = _FakeModelsResource(
        [], exc=RuntimeError(f"401 {secret} is not valid"),
    )
    _patch_client(monkeypatch, resource)

    res = await rs._list_llm_models("openai", None, secret)

    assert res["ok"] is False
    assert secret not in res["error"]
    assert "***" in res["error"]
