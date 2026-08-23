from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from library.config import Settings, get_settings
from library.model_rate_limit import acquire_model_call_slot
from library.provider_clients import (
    get_openai_compatible_client,
    get_provider_http_client,
)
from library.provider_http import raise_for_provider_status


TextType = Literal["query", "document"]


@dataclass(slots=True)
class EmbeddingResult:
    vectors: list[list[float]]
    total_tokens: int = 0


class EmbeddingConfigError(RuntimeError):
    pass


class EmbeddingProviderError(RuntimeError):
    """The embedding provider failed or returned an invalid response."""


def _resolve_embedding_api_key(settings: Settings) -> str | None:
    return settings.embedding_api_key


class DashScopeEmbeddingClient:
    """Native DashScope text embedding client for Bailian text-embedding-v4."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.api_key = _resolve_embedding_api_key(self.settings)
        if not self.api_key:
            raise EmbeddingConfigError(
                "embedding api key is not configured; set EMBEDDING_API_KEY"
            )
        self.base_url = (
            self.settings.embedding_base_url
            if "/compatible-mode/" not in self.settings.embedding_base_url
            else "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding"
        )
        self.model = self.settings.embedding_model
        self.dimensions = max(1, int(self.settings.embedding_dimensions or 1024))

    async def embed(
        self,
        texts: list[str],
        *,
        text_type: TextType,
    ) -> EmbeddingResult:
        clean = [str(text or "").strip() for text in texts]
        if not clean:
            return EmbeddingResult(vectors=[])
        vectors: list[list[float]] = []
        total_tokens = 0
        for batch in _chunked(clean, self.settings.embedding_batch_size):
            result = await self._embed_batch(batch, text_type=text_type)
            vectors.extend(result.vectors)
            total_tokens += result.total_tokens
        return EmbeddingResult(vectors=vectors, total_tokens=total_tokens)

    async def _embed_batch(
        self,
        clean: list[str],
        *,
        text_type: TextType,
    ) -> EmbeddingResult:
        payload = {
            "model": self.model,
            "input": {
                "texts": clean,
            },
            "parameters": {
                "dimension": self.dimensions,
                "output_type": "dense",
                "text_type": text_type,
            },
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        await acquire_model_call_slot(
            kind="embedding",
            provider=self.settings.embedding_provider,
            base_url=self.settings.embedding_base_url,
            model=self.model,
            tps=self.settings.embedding_tps,
        )
        try:
            client = get_provider_http_client()
            resp = await client.post(self.base_url, headers=headers, json=payload)
            raise_for_provider_status(resp, "embedding")
            obj = resp.json()
            output = obj.get("output") if isinstance(obj, dict) else None
            embeddings = output.get("embeddings") if isinstance(output, dict) else None
            if not isinstance(embeddings, list):
                raise RuntimeError("embedding response missing output.embeddings")
            ordered: list[list[float] | None] = [None] * len(clean)
            for idx, item in enumerate(embeddings):
                if not isinstance(item, dict):
                    continue
                text_index = int(item.get("text_index", idx))
                vector = item.get("embedding")
                if isinstance(vector, list) and 0 <= text_index < len(ordered):
                    ordered[text_index] = [float(v) for v in vector]
            result = EmbeddingResult(
                vectors=[_normalize(vec or []) for vec in ordered],
                total_tokens=(
                    int((obj.get("usage") or {}).get("total_tokens") or 0)
                    if isinstance(obj, dict) and isinstance(obj.get("usage"), dict)
                    else 0
                ),
            )
            _validate_embedding_result(
                result,
                expected=len(clean),
                dimensions=self.dimensions,
            )
            return result
        except EmbeddingProviderError:
            raise
        except Exception as exc:  # noqa: BLE001 - provider clients vary
            raise EmbeddingProviderError(
                f"embedding provider request failed: {exc}"
            ) from exc


class OpenAICompatibleEmbeddingClient:
    """OpenAI-compatible embeddings client, used by Bailian compatible-mode."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.api_key = _resolve_embedding_api_key(self.settings)
        if not self.api_key:
            raise EmbeddingConfigError(
                "embedding api key is not configured; set EMBEDDING_API_KEY"
            )
        self.base_url = self.settings.embedding_base_url
        self.model = self.settings.embedding_model
        self.dimensions = max(1, int(self.settings.embedding_dimensions or 1024))

    async def embed(
        self,
        texts: list[str],
        *,
        text_type: TextType,
    ) -> EmbeddingResult:
        clean = [str(text or "").strip() for text in texts]
        if not clean:
            return EmbeddingResult(vectors=[])
        vectors: list[list[float]] = []
        total_tokens = 0
        for batch in _chunked(clean, self.settings.embedding_batch_size):
            result = await self._embed_batch(batch)
            vectors.extend(result.vectors)
            total_tokens += result.total_tokens
        return EmbeddingResult(vectors=vectors, total_tokens=total_tokens)

    async def _embed_batch(self, clean: list[str]) -> EmbeddingResult:
        kwargs = {
            "model": self.model,
            "input": clean,
            "dimensions": self.dimensions,
            "encoding_format": "float",
        }
        await acquire_model_call_slot(
            kind="embedding",
            provider=self.settings.embedding_provider,
            base_url=self.settings.embedding_base_url,
            model=self.model,
            tps=self.settings.embedding_tps,
        )
        try:
            client = get_openai_compatible_client(
                api_key=self.api_key,
                base_url=self.base_url,
            )
            resp = await client.embeddings.create(**kwargs)
            ordered: list[list[float] | None] = [None] * len(clean)
            for idx, item in enumerate(resp.data):
                text_index = int(getattr(item, "index", idx))
                if 0 <= text_index < len(ordered):
                    ordered[text_index] = [float(v) for v in item.embedding]
            usage = getattr(resp, "usage", None)
            result = EmbeddingResult(
                vectors=[_normalize(vec or []) for vec in ordered],
                total_tokens=int(getattr(usage, "total_tokens", 0) or 0),
            )
            _validate_embedding_result(
                result,
                expected=len(clean),
                dimensions=self.dimensions,
            )
            return result
        except EmbeddingProviderError:
            raise
        except Exception as exc:  # noqa: BLE001 - SDK exception types vary
            raise EmbeddingProviderError(
                f"embedding provider request failed: {exc}"
            ) from exc


def get_embedding_client(
    settings: Settings | None = None,
) -> DashScopeEmbeddingClient | OpenAICompatibleEmbeddingClient:
    settings = settings or get_settings()
    if settings.embedding_provider == "dashscope":
        return DashScopeEmbeddingClient(settings)
    if settings.embedding_provider == "openai-compatible":
        return OpenAICompatibleEmbeddingClient(settings)
    raise EmbeddingConfigError(f"unknown embedding provider: {settings.embedding_provider}")


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vector))
    if norm <= 0:
        return vector
    return [v / norm for v in vector]


def _chunked(values: list[str], size: int) -> list[list[str]]:
    chunk_size = max(1, int(size or 1))
    return [values[index:index + chunk_size] for index in range(0, len(values), chunk_size)]


def _validate_embedding_result(
    result: EmbeddingResult,
    *,
    expected: int,
    dimensions: int,
) -> None:
    if len(result.vectors) != expected:
        raise EmbeddingProviderError(
            "embedding response count mismatch: "
            f"expected {expected}, received {len(result.vectors)}"
        )
    for index, vector in enumerate(result.vectors):
        if len(vector) != dimensions:
            raise EmbeddingProviderError(
                "embedding response dimension mismatch at index "
                f"{index}: expected {dimensions}, received {len(vector)}"
            )
