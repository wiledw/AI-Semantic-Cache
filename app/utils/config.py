from __future__ import annotations

import os
from dataclasses import dataclass


def _get_env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _get_env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    similarity_threshold: float
    max_llm_calls: int
    redis_url: str
    short_ttl_seconds: int
    long_ttl_seconds: int
    embedding_cache_ttl_seconds: int
    llm_system_prompt: str
    llm_fallback_response: str
    llm_cost_per_call: float
    weaviate_url: str
    weaviate_api_key: str
    use_weaviate: bool


def _get_env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in ("true", "1", "yes", "on")


def get_settings() -> Settings:
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        similarity_threshold=_get_env_float("SIMILARITY_THRESHOLD", 0.85),
        max_llm_calls=_get_env_int("MAX_LLM_CALLS", 100),
        redis_url=os.getenv("REDIS_URL", "redis://redis:6379/0"),
        short_ttl_seconds=_get_env_int("SHORT_TTL_SECONDS", 600),
        long_ttl_seconds=_get_env_int("LONG_TTL_SECONDS", 86400),
        embedding_cache_ttl_seconds=_get_env_int("EMBEDDING_CACHE_TTL_SECONDS", 604800),
        llm_system_prompt=os.getenv(
            "LLM_SYSTEM_PROMPT",
            "You are a concise assistant. Answer briefly and factually.",
        ),
        llm_fallback_response=os.getenv(
            "LLM_FALLBACK_RESPONSE",
            "LLM call limit reached. Please try again later.",
        ),
        llm_cost_per_call=_get_env_float("LLM_COST_PER_CALL", 0.01),
        weaviate_url=os.getenv("WEAVIATE_URL", "http://weaviate:8080"),
        weaviate_api_key=os.getenv("WEAVIATE_API_KEY", ""),
        use_weaviate=_get_env_bool("USE_WEAVIATE", False),
    )
