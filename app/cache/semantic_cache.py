from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from redis import Redis

from app.llm.openai_client import OpenAIClient
from app.utils.similarity import cosine_similarity, normalize_query


logger = logging.getLogger(__name__)


class SemanticCache:
    def __init__(
        self,
        redis_client: Redis,
        openai_client: OpenAIClient,
        similarity_threshold: float,
        embedding_cache_ttl_seconds: int,
    ) -> None:
        self._redis = redis_client
        self._openai = openai_client
        self._threshold = similarity_threshold
        self._embedding_cache_ttl_seconds = embedding_cache_ttl_seconds

    def get_or_create_embedding(self, query: str) -> list[float]:
        # Use enhanced preprocessing to normalize query for better cache matching
        normalized = normalize_query(query, enhanced=True)
        # Include embedding model in cache key to avoid conflicts between models
        model_name = self._openai._embedding_model
        embed_key = f"embed:{model_name}:{self._hash_text(normalized)}"
        cached = self._redis.get(embed_key)
        if cached:
            return json.loads(cached)

        # Generate embedding from normalized query to maximize similarity matching
        # This ensures similar queries produce similar embeddings
        embedding = self._openai.get_embedding(normalized)
        self._redis.set(
            embed_key,
            json.dumps(embedding),
            ex=self._embedding_cache_ttl_seconds,
        )
        return embedding

    def find_similar(self, query_embedding: list[float], threshold: Optional[float] = None) -> tuple[Optional[dict], float]:
        """Find similar cached entry. Optionally override threshold for testing."""
        threshold_to_use = threshold if threshold is not None else self._threshold
        best_entry = None
        best_score = 0.0
        cache_keys = list(self._redis.smembers("cache_keys"))
        for key in cache_keys:
            payload = self._redis.get(key)
            if not payload:
                self._redis.srem("cache_keys", key)
                continue
            entry = json.loads(payload)
            score = cosine_similarity(query_embedding, entry["embedding"])
            if score > best_score:
                best_score = score
                best_entry = entry

        if best_entry and best_score >= threshold_to_use:
            return best_entry, best_score
        return None, best_score

    def store_response(
        self,
        query: str,
        embedding: list[float],
        response: str,
        ttl_seconds: int,
    ) -> None:
        cache_key = f"cache:{self._hash_text(query)}"
        entry = {
            "query_text": query,
            "embedding": embedding,
            "response": response,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "ttl_seconds": ttl_seconds,
        }
        self._redis.set(cache_key, json.dumps(entry), ex=ttl_seconds)
        self._redis.sadd("cache_keys", cache_key)
        logger.info("Cached response under %s for %ss", cache_key, ttl_seconds)

    @staticmethod
    def _hash_text(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
