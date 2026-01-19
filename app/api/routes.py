from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from redis.asyncio import Redis as AsyncRedis

from app.cache.semantic_cache import SemanticCache
from app.llm.openai_client import OpenAIClient
from app.utils.config import get_settings
from app.utils.connection_pool import get_async_redis_client, get_weaviate_client
from app.utils.query_classification import is_time_sensitive


logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1)
    forceRefresh: bool = False
    similarityThreshold: Optional[float] = Field(None, ge=0.0, le=1.0, description="Override similarity threshold for testing")
    embeddingModel: Optional[str] = Field(None, description="Override embedding model for testing")


class ResponseMetadata(BaseModel):
    source: str
    similarity: float | None = None


class QueryResponse(BaseModel):
    response: str
    metadata: ResponseMetadata


class StatsResponse(BaseModel):
    requests: int
    cache_hits: int
    cache_misses: int
    llm_calls: int
    llm_fallbacks: int
    cache_hit_rate: float
    estimated_llm_cost: float
    estimated_cache_savings: float


async def _build_clients(embedding_model: Optional[str] = None) -> tuple[SemanticCache, OpenAIClient]:
    # Use async connection pool for Redis
    redis_client = await get_async_redis_client()
    
    openai_client = OpenAIClient(
        api_key=settings.openai_api_key,
        max_llm_calls=settings.max_llm_calls,
        redis_client=redis_client,
        system_prompt=settings.llm_system_prompt,
        fallback_response=settings.llm_fallback_response,
        embedding_model=embedding_model or "text-embedding-3-small",
    )
    
    # Use connection pool for Weaviate
    weaviate_client = get_weaviate_client()
    
    cache = SemanticCache(
        redis_client=redis_client,
        openai_client=openai_client,
        similarity_threshold=settings.similarity_threshold,
        embedding_cache_ttl_seconds=settings.embedding_cache_ttl_seconds,
        weaviate_client=weaviate_client,
        use_weaviate=settings.use_weaviate and weaviate_client is not None,
    )
    return cache, openai_client


async def _increment_stat(redis_client: AsyncRedis, key: str) -> None:
    try:
        await redis_client.incr(key)
    except Exception:
        logger.warning("Failed to increment stat %s", key)


async def _get_stat(redis_client: AsyncRedis, key: str) -> int:
    try:
        value = await redis_client.get(key)
        return int(value) if value else 0
    except Exception:
        logger.warning("Failed to read stat %s", key)
        return 0


@router.post("/query", response_model=QueryResponse)
async def query_endpoint(payload: QueryRequest) -> QueryResponse:
    if not settings.openai_api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY is not set.")

    cache, openai_client = await _build_clients(embedding_model=payload.embeddingModel)
    # Use shared async Redis client from connection pool
    redis_client = await get_async_redis_client()
    query_text = payload.query.strip()
    time_sensitive = is_time_sensitive(query_text)
    ttl_seconds = (
        settings.short_ttl_seconds if time_sensitive else settings.long_ttl_seconds
    )

    logger.info(
        "Incoming query. time_sensitive=%s force_refresh=%s",
        time_sensitive,
        payload.forceRefresh,
    )
    await _increment_stat(redis_client, "stat:requests")

    # Request-level caching: Check for exact match before semantic search
    if not payload.forceRefresh:
        exact_match = await cache.get_exact_match(query_text)
        if exact_match:
            logger.info("Exact match cache hit (request-level)")
            await _increment_stat(redis_client, "stat:cache_hits")
            return QueryResponse(
                response=exact_match["response"],
                metadata=ResponseMetadata(source="cache", similarity=1.0),
            )

    try:
        embedding = await cache.get_or_create_embedding(query_text)
    except Exception as exc:
        logger.exception("Embedding generation failed: %s", exc)
        raise HTTPException(status_code=502, detail="Embedding service failure.")

    if not payload.forceRefresh:
        # Use custom threshold if provided, otherwise use default
        threshold = payload.similarityThreshold if payload.similarityThreshold is not None else settings.similarity_threshold
        entry, similarity = await cache.find_similar(embedding, threshold=threshold)
        if entry:
            logger.info("Cache hit with similarity %.4f", similarity)
            await _increment_stat(redis_client, "stat:cache_hits")
            return QueryResponse(
                response=entry["response"],
                metadata=ResponseMetadata(source="cache", similarity=similarity),
            )
        logger.info("Cache miss. Best similarity %.4f", similarity)
        await _increment_stat(redis_client, "stat:cache_misses")
    else:
        await _increment_stat(redis_client, "stat:cache_misses")

    try:
        answer, used_llm = await openai_client.get_completion(query_text)
    except Exception as exc:
        logger.exception("LLM call failed: %s", exc)
        raise HTTPException(status_code=502, detail="LLM service failure.")

    if used_llm:
        await cache.store_response(query_text, embedding, answer, ttl_seconds)
    else:
        await _increment_stat(redis_client, "stat:llm_fallbacks")
        logger.warning("Fallback response returned due to LLM call cap.")

    source = openai_client.chat_model if used_llm else "fallback"
    return QueryResponse(
        response=answer,
        metadata=ResponseMetadata(source=source),
    )


@router.get("/stats", response_model=StatsResponse)
async def stats_endpoint() -> StatsResponse:
    # Use shared async Redis client from connection pool
    redis_client = await get_async_redis_client()
    requests = await _get_stat(redis_client, "stat:requests")
    cache_hits = await _get_stat(redis_client, "stat:cache_hits")
    cache_misses = await _get_stat(redis_client, "stat:cache_misses")
    llm_calls = await _get_stat(redis_client, "llm_call_count")
    llm_fallbacks = await _get_stat(redis_client, "stat:llm_fallbacks")
    hit_rate = (cache_hits / requests) if requests > 0 else 0.0
    estimated_cost = llm_calls * settings.llm_cost_per_call
    estimated_savings = cache_hits * settings.llm_cost_per_call

    return StatsResponse(
        requests=requests,
        cache_hits=cache_hits,
        cache_misses=cache_misses,
        llm_calls=llm_calls,
        llm_fallbacks=llm_fallbacks,
        cache_hit_rate=hit_rate,
        estimated_llm_cost=estimated_cost,
        estimated_cache_savings=estimated_savings,
    )
