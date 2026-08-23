"""Cache-eligibility accounting for persisted model calls."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class CacheUsageSummary:
    prompt_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    eligible_prompt_tokens: int = 0
    eligible_read_tokens: int = 0
    eligible_estimated_tokens: int = 0
    eligible_requests: int = 0
    prefix_breaks: int = 0

    @property
    def prompt_coverage_ratio(self) -> float | None:
        if self.eligible_prompt_tokens <= 0:
            return None
        return self.eligible_read_tokens / self.eligible_prompt_tokens

    @property
    def eligible_reuse_ratio(self) -> float | None:
        if self.eligible_estimated_tokens <= 0:
            return None
        return min(1.0, self.eligible_read_tokens / self.eligible_estimated_tokens)

    @property
    def eligible_hit_ratio(self) -> float | None:
        """Backward-compatible name for eligible-prefix reuse."""
        return self.eligible_reuse_ratio

    def slo_payload(
        self,
        *,
        minimum_hit_ratio: float,
        minimum_eligible_requests: int,
    ) -> dict[str, int | float | str]:
        if (
            self.eligible_requests < minimum_eligible_requests
            or self.eligible_reuse_ratio is None
        ):
            status = "insufficient_data"
        elif self.eligible_reuse_ratio >= minimum_hit_ratio:
            status = "met"
        else:
            status = "breached"
        return {
            "status": status,
            "minimum_hit_ratio": minimum_hit_ratio,
            "minimum_eligible_requests": minimum_eligible_requests,
        }

    def payload(self) -> dict[str, int | float | None]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_creation_tokens": self.cache_creation_tokens,
            "eligible_prompt_tokens": self.eligible_prompt_tokens,
            "eligible_read_tokens": self.eligible_read_tokens,
            "eligible_estimated_tokens": self.eligible_estimated_tokens,
            "eligible_requests": self.eligible_requests,
            "prefix_breaks": self.prefix_breaks,
            "prompt_coverage_ratio": self.prompt_coverage_ratio,
            "eligible_hit_ratio": self.eligible_hit_ratio,
            "eligible_reuse_ratio": self.eligible_reuse_ratio,
        }


def summarize_llm_calls(calls: Iterable[dict[str, Any]]) -> CacheUsageSummary:
    prompt_tokens = 0
    cache_read_tokens = 0
    cache_creation_tokens = 0
    eligible_prompt_tokens = 0
    eligible_read_tokens = 0
    eligible_estimated_tokens = 0
    eligible_requests = 0
    prefix_breaks = 0
    for call in calls:
        prompt = max(0, int(call.get("prompt_tokens") or 0))
        cache_read = max(0, int(call.get("cache_read_tokens") or 0))
        prompt_tokens += prompt
        cache_read_tokens += cache_read
        cache_creation_tokens += max(
            0,
            int(call.get("cache_creation_tokens") or 0),
        )
        preserved = call.get("prompt_prefix_preserved")
        if preserved is True:
            eligible_requests += 1
            eligible_prompt_tokens += prompt
            eligible_read_tokens += cache_read
            eligible_estimated_tokens += max(
                0,
                int(call.get("cache_eligible_tokens") or 0),
            )
        elif preserved is False:
            prefix_breaks += 1
    return CacheUsageSummary(
        prompt_tokens=prompt_tokens,
        cache_read_tokens=cache_read_tokens,
        cache_creation_tokens=cache_creation_tokens,
        eligible_prompt_tokens=eligible_prompt_tokens,
        eligible_read_tokens=eligible_read_tokens,
        eligible_estimated_tokens=eligible_estimated_tokens,
        eligible_requests=eligible_requests,
        prefix_breaks=prefix_breaks,
    )
