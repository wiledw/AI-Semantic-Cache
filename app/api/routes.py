from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from redis.asyncio import Redis as AsyncRedis

from app.cache.semantic_cache import SemanticCache
from app.llm.openai_client import OpenAIClient
from app.utils.config import get_settings
from app.utils.connection_pool import get_async_redis_client, get_weaviate_client
from app.utils.metrics import MetricsCollector
from app.utils.query_classification import is_time_sensitive
from app.utils.structured_logging import get_logger, log_with_context


logger = get_logger(__name__)
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


class MetricsDataPoint(BaseModel):
    timestamp: str
    timestamp_sec: int
    requests: int
    hits: int
    misses: int
    avg_latency_ms: float
    hit_rate: float
    cumulative_requests: int
    cumulative_hits: int
    cumulative_misses: int
    cumulative_hit_rate: float


class MetricsResponse(BaseModel):
    data: list[MetricsDataPoint]
    current_stats: dict


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
    start_time = time.time()
    request_id = f"req_{int(start_time * 1000)}"
    
    if not settings.openai_api_key:
        log_with_context(
            logger,
            logging.ERROR,
            "OPENAI_API_KEY is not set",
            request_id=request_id,
            operation="query",
        )
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY is not set.")

    cache, openai_client = await _build_clients(embedding_model=payload.embeddingModel)
    # Use shared async Redis client from connection pool
    redis_client = await get_async_redis_client()
    metrics = MetricsCollector(redis_client)
    
    query_text = payload.query.strip()
    time_sensitive = is_time_sensitive(query_text)
    ttl_seconds = (
        settings.short_ttl_seconds if time_sensitive else settings.long_ttl_seconds
    )

    log_with_context(
        logger,
        logging.INFO,
        "Incoming query",
        request_id=request_id,
        operation="query",
        time_sensitive=time_sensitive,
        force_refresh=payload.forceRefresh,
    )
    await _increment_stat(redis_client, "stat:requests")

    is_hit = False
    similarity_score: Optional[float] = None
    operation_type = "query"

    # Request-level caching: Check for exact match before semantic search
    if not payload.forceRefresh:
        exact_match = await cache.get_exact_match(query_text)
        if exact_match:
            latency_ms = (time.time() - start_time) * 1000
            is_hit = True
            similarity_score = 1.0
            operation_type = "exact_match"
            
            log_with_context(
                logger,
                logging.INFO,
                "Exact match cache hit",
                request_id=request_id,
                operation=operation_type,
                hit=True,
                similarity=similarity_score,
                latency_ms=latency_ms,
            )
            
            await _increment_stat(redis_client, "stat:cache_hits")
            await metrics.record_request(
                is_hit=True,
                latency_ms=latency_ms,
                similarity=similarity_score,
                operation=operation_type,
            )
            
            return QueryResponse(
                response=exact_match["response"],
                metadata=ResponseMetadata(source="cache", similarity=1.0),
            )

    try:
        embedding = await cache.get_or_create_embedding(query_text)
    except Exception as exc:
        latency_ms = (time.time() - start_time) * 1000
        log_with_context(
            logger,
            logging.ERROR,
            "Embedding generation failed",
            request_id=request_id,
            operation="embedding",
            latency_ms=latency_ms,
            exception=str(exc),
        )
        raise HTTPException(status_code=502, detail="Embedding service failure.")

    if not payload.forceRefresh:
        # Use custom threshold if provided, otherwise use default
        threshold = payload.similarityThreshold if payload.similarityThreshold is not None else settings.similarity_threshold
        entry, similarity = await cache.find_similar(embedding, threshold=threshold)
        if entry:
            latency_ms = (time.time() - start_time) * 1000
            is_hit = True
            similarity_score = similarity
            operation_type = "semantic_search"
            
            log_with_context(
                logger,
                logging.INFO,
                "Cache hit with similarity",
                request_id=request_id,
                operation=operation_type,
                hit=True,
                similarity=similarity_score,
                latency_ms=latency_ms,
            )
            
            await _increment_stat(redis_client, "stat:cache_hits")
            await metrics.record_request(
                is_hit=True,
                latency_ms=latency_ms,
                similarity=similarity_score,
                operation=operation_type,
            )
            
            return QueryResponse(
                response=entry["response"],
                metadata=ResponseMetadata(source="cache", similarity=similarity),
            )
        
        similarity_score = similarity
        operation_type = "semantic_search"
        log_with_context(
            logger,
            logging.INFO,
            "Cache miss",
            request_id=request_id,
            operation=operation_type,
            miss=True,
            similarity=similarity_score,
        )
        await _increment_stat(redis_client, "stat:cache_misses")
    else:
        await _increment_stat(redis_client, "stat:cache_misses")

    try:
        answer, used_llm = await openai_client.get_completion(query_text)
    except Exception as exc:
        latency_ms = (time.time() - start_time) * 1000
        log_with_context(
            logger,
            logging.ERROR,
            "LLM call failed",
            request_id=request_id,
            operation="llm_call",
            latency_ms=latency_ms,
            exception=str(exc),
        )
        raise HTTPException(status_code=502, detail="LLM service failure.")

    if used_llm:
        await cache.store_response(query_text, embedding, answer, ttl_seconds)
        log_with_context(
            logger,
            logging.INFO,
            "Stored response in cache",
            request_id=request_id,
            operation="store_response",
            ttl_seconds=ttl_seconds,
        )
    else:
        await _increment_stat(redis_client, "stat:llm_fallbacks")
        log_with_context(
            logger,
            logging.WARNING,
            "Fallback response returned due to LLM call cap",
            request_id=request_id,
            operation="fallback",
        )

    latency_ms = (time.time() - start_time) * 1000
    await metrics.record_request(
        is_hit=False,
        latency_ms=latency_ms,
        similarity=similarity_score,
        operation=operation_type,
    )

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


@router.get("/metrics", response_model=MetricsResponse)
async def metrics_endpoint(
    hours: int = 1,
    interval_seconds: int = 10,
) -> MetricsResponse:
    """Get time-series metrics data for cache performance visualization.
    
    Args:
        hours: Number of hours of data to retrieve (default: 1)
        interval_seconds: Aggregation interval in seconds (default: 60)
    """
    from datetime import timedelta
    
    redis_client = await get_async_redis_client()
    metrics = MetricsCollector(redis_client)
    
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=hours)
    
    time_series_data = await metrics.get_time_series_data(
        start_time=start_time,
        end_time=end_time,
        interval_seconds=interval_seconds,
    )
    
    current_stats = await metrics.get_current_stats()
    
    return MetricsResponse(
        data=[MetricsDataPoint(**point) for point in time_series_data],
        current_stats=current_stats,
    )
