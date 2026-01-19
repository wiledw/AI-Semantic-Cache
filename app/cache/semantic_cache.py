from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from redis.asyncio import Redis as AsyncRedis
import weaviate
from weaviate.classes.query import MetadataQuery

from app.llm.openai_client import OpenAIClient
from app.utils.similarity import cosine_similarity, normalize_query


logger = logging.getLogger(__name__)


class SemanticCache:
    def __init__(
        self,
        redis_client: AsyncRedis,
        openai_client: OpenAIClient,
        similarity_threshold: float,
        embedding_cache_ttl_seconds: int,
        weaviate_client: Optional[weaviate.WeaviateClient] = None,
        use_weaviate: bool = False,
    ) -> None:
        self._redis = redis_client
        self._openai = openai_client
        self._threshold = similarity_threshold
        self._embedding_cache_ttl_seconds = embedding_cache_ttl_seconds
        self._weaviate = weaviate_client
        self._use_weaviate = use_weaviate and weaviate_client is not None

    async def get_or_create_embedding(self, query: str) -> list[float]:
        # Use enhanced preprocessing to normalize query for better cache matching
        normalized = normalize_query(query, enhanced=True)
        # Include embedding model in cache key to avoid conflicts between models
        model_name = self._openai.embedding_model
        embed_key = f"embed:{model_name}:{self._hash_text(normalized)}"
        cached = await self._redis.get(embed_key)
        if cached:
            return json.loads(cached)

        # Generate embedding from normalized query to maximize similarity matching
        # This ensures similar queries produce similar embeddings
        embedding = await self._openai.get_embedding(normalized)
        await self._redis.set(
            embed_key,
            json.dumps(embedding),
            ex=self._embedding_cache_ttl_seconds,
        )
        return embedding

    async def find_similar(self, query_embedding: list[float], threshold: Optional[float] = None) -> tuple[Optional[dict], float]:
        """Find similar cached entry. Optionally override threshold for testing."""
        threshold_to_use = threshold if threshold is not None else self._threshold
        
        # Use Weaviate if enabled and available
        if self._use_weaviate:
            return await self._find_similar_weaviate(query_embedding, threshold_to_use)
        
        # Fallback to linear scan
        return await self._find_similar_linear(query_embedding, threshold_to_use)
    
    async def _find_similar_weaviate(self, query_embedding: list[float], threshold: float) -> tuple[Optional[dict], float]:
        """Find similar cached entry using Weaviate vector search."""
        try:
            collection = self._weaviate.collections.get("SemanticCache")
            
            # Convert threshold to distance (cosine similarity to distance)
            # cosine similarity: 1.0 = identical, 0.0 = orthogonal
            # cosine distance: 0.0 = identical, 1.0 = orthogonal
            # distance = 1 - similarity
            # So for threshold 0.85, we want distance <= 0.15
            max_distance = 1.0 - threshold
            
            # Query Weaviate for nearest vector
            # Note: Weaviate client operations are synchronous, but we're in an async context
            # We'll run them in a thread pool to avoid blocking
            import asyncio
            result = await asyncio.to_thread(
                lambda: collection.query.near_vector(
                    near_vector=query_embedding,
                    limit=1,
                    return_metadata=MetadataQuery(distance=True),
                )
            )
            
            if result.objects and len(result.objects) > 0:
                obj = result.objects[0]
                distance = obj.metadata.distance if obj.metadata and obj.metadata.distance else 1.0
                similarity = 1.0 - distance
                
                if similarity >= threshold:
                    # Convert Weaviate object to dict format
                    entry = {
                        "query_text": obj.properties.get("query_text", ""),
                        "response": obj.properties.get("response", ""),
                        "created_at": obj.properties.get("created_at", ""),
                        "ttl_seconds": obj.properties.get("ttl_seconds", 0),
                        "embedding": query_embedding,  # We don't store embedding in response
                    }
                    return entry, similarity
            
            return None, 0.0
        except Exception as exc:
            logger.warning("Weaviate search failed, falling back to linear scan: %s", exc)
            return await self._find_similar_linear(query_embedding, threshold)
    
    async def _find_similar_linear(self, query_embedding: list[float], threshold: float) -> tuple[Optional[dict], float]:
        """Find similar cached entry using linear scan (original implementation)."""
        best_entry = None
        best_score = 0.0
        cache_keys = await self._redis.smembers("cache_keys")
        for key in cache_keys:
            payload = await self._redis.get(key)
            if not payload:
                await self._redis.srem("cache_keys", key)
                continue
            entry = json.loads(payload)
            score = cosine_similarity(query_embedding, entry["embedding"])
            if score > best_score:
                best_score = score
                best_entry = entry

        if best_entry and best_score >= threshold:
            return best_entry, best_score
        return None, best_score

    async def store_response(
        self,
        query: str,
        embedding: list[float],
        response: str,
        ttl_seconds: int,
    ) -> None:
        cache_key = f"cache:{self._hash_text(query)}"
        created_at = datetime.now(timezone.utc).isoformat()
        
        # Always store in Redis for backward compatibility and TTL management
        entry = {
            "query_text": query,
            "embedding": embedding,
            "response": response,
            "created_at": created_at,
            "ttl_seconds": ttl_seconds,
        }
        await self._redis.set(cache_key, json.dumps(entry), ex=ttl_seconds)
        await self._redis.sadd("cache_keys", cache_key)
        
        # Also store in Weaviate if enabled
        if self._use_weaviate:
            try:
                await self._store_response_weaviate(
                    query=query,
                    embedding=embedding,
                    response=response,
                    created_at=created_at,
                    ttl_seconds=ttl_seconds,
                    cache_key=cache_key,
                )
            except Exception as exc:
                logger.warning("Failed to store in Weaviate: %s", exc)
                # Continue - Redis storage succeeded
        
        logger.info("Cached response under %s for %ss", cache_key, ttl_seconds)
    
    async def _store_response_weaviate(
        self,
        query: str,
        embedding: list[float],
        response: str,
        created_at: str,
        ttl_seconds: int,
        cache_key: str,
    ) -> None:
        """Store response in Weaviate."""
        collection = self._weaviate.collections.get("SemanticCache")
        
        # Parse ISO format date for Weaviate (convert to datetime object)
        from datetime import datetime as dt
        # Handle both Z and +00:00 timezone formats
        if created_at.endswith("Z"):
            created_at_dt = dt.fromisoformat(created_at.replace("Z", "+00:00"))
        else:
            created_at_dt = dt.fromisoformat(created_at)
        
        # Run Weaviate insert in thread pool to avoid blocking
        import asyncio
        await asyncio.to_thread(
            lambda: collection.data.insert(
                properties={
                    "query_text": query,
                    "response": response,
                    "created_at": created_at_dt,
                    "ttl_seconds": ttl_seconds,
                    "cache_key": cache_key,
                },
                vector=embedding,
            )
        )

    @staticmethod
    def _hash_text(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
