from __future__ import annotations

import pytest

from library.config import LlmConfigError, Settings, validate_llm_config


def test_document_vision_rejects_profile_declared_without_image_support() -> None:
    settings = Settings(
        _env_file=None,
        llm_default_api_key="default-key",
        llm_default_model="default-model",
        llm_vision_api_key="vision-key",
        llm_vision_model="vision-model",
        llm_vision_supports_vision=False,
        document_vision_enabled=True,
    )

    with pytest.raises(LlmConfigError, match="declared without image support"):
        validate_llm_config(settings)


def test_disabled_document_vision_allows_text_only_optional_profile() -> None:
    settings = Settings(
        _env_file=None,
        llm_default_api_key="default-key",
        llm_default_model="default-model",
        llm_vision_api_key="vision-key",
        llm_vision_model="vision-model",
        llm_vision_supports_vision=False,
        document_vision_enabled=False,
    )

    validate_llm_config(settings)


def test_provider_managed_ingest_limit_is_allowed_for_openai_shape() -> None:
    settings = Settings(
        _env_file=None,
        llm_default_provider="openai-compatible",
        llm_default_api_key="default-key",
        llm_default_model="default-model",
        llm_ingest_max_tokens=0,
    )

    validate_llm_config(settings)


def test_provider_managed_ingest_limit_is_rejected_for_anthropic() -> None:
    settings = Settings(
        _env_file=None,
        llm_default_provider="anthropic",
        llm_default_api_key="default-key",
        llm_default_model="default-model",
        llm_ingest_max_tokens=0,
    )

    with pytest.raises(LlmConfigError, match="requires max_tokens"):
        validate_llm_config(settings)
