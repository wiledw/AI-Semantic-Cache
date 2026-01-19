from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from redis.asyncio import Redis as AsyncRedis
import weaviate
from weaviate.classes.query import MetadataQuery, Filter

from app.llm.openai_client import OpenAIClient
from app.utils.similarity import cosine_similarity, normalize_query
from app.utils.query_classification import extract_topic_keywords
from app.cache.weaviate_schema import COLLECTION_NAME


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
        max_age_by_query_type: Optional[dict[str, int]] = None,
    ) -> None:
        self._redis = redis_client
        self._openai = openai_client
        self._threshold = similarity_threshold
        self._embedding_cache_ttl_seconds = embedding_cache_ttl_seconds
        self._weaviate = weaviate_client
        self._use_weaviate = use_weaviate and weaviate_client is not None
        self._max_age_by_query_type = max_age_by_query_type or {}

    async def get_exact_match(self, query: str, topic: Optional[str] = None) -> Optional[dict]:
        """Check for exact query match in cache (request-level caching).
        
        Args:
            query: Query string
            topic: Optional topic for topic-partitioned lookup
        """
        if topic:
            # Try topic-specific cache first
            cache_key = f"cache:{topic}:{self._hash_text(query)}"
            cached = await self._redis.get(cache_key)
            if cached:
                entry = json.loads(cached)
                return entry
        
        # Fallback to global cache (backward compatibility)
        cache_key = f"cache:{self._hash_text(query)}"
        cached = await self._redis.get(cache_key)
        if cached:
            entry = json.loads(cached)
            return entry
        return None
    
    def is_stale(self, entry: dict, query_type: Optional[str] = None) -> bool:
        """Check if a cache entry is stale based on TTL and age-based limits.
        
        Args:
            entry: Cache entry dict with 'created_at' and 'ttl_seconds'
            query_type: Optional query type for age-based invalidation
            
        Returns:
            True if entry is stale, False otherwise
        """
        if "created_at" not in entry:
            return True  # Missing timestamp, consider stale
        
        try:
            created_at_value = entry["created_at"]
            
            # Handle different formats: datetime object (from Weaviate) or string (from Redis)
            if isinstance(created_at_value, datetime):
                created_at = created_at_value
            elif isinstance(created_at_value, str):
                # Handle both Z and +00:00 timezone formats
                if created_at_value.endswith("Z"):
                    created_at = datetime.fromisoformat(created_at_value.replace("Z", "+00:00"))
                else:
                    created_at = datetime.fromisoformat(created_at_value)
            else:
                logger.warning("Unexpected created_at type: %s", type(created_at_value))
                return True  # Consider stale if we can't parse
            
            # Ensure timezone-aware
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            
            now = datetime.now(timezone.utc)
            entry_age = (now - created_at).total_seconds()
            
            # Get TTL from entry
            ttl_seconds = entry.get("ttl_seconds", 0)
            
            # Get max age for query type if available
            max_age = None
            if query_type and self._max_age_by_query_type:
                max_age = self._max_age_by_query_type.get(query_type)
            
            # Entry is stale if age exceeds min(TTL, max_age_for_query_type)
            if max_age is not None:
                effective_max_age = min(ttl_seconds, max_age)
            else:
                effective_max_age = ttl_seconds
            
            return entry_age > effective_max_age
            
        except (ValueError, KeyError) as exc:
            logger.warning("Failed to check staleness: %s", exc)
            return True  # On error, consider stale

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

    async def get_or_create_embeddings_batch(self, queries: list[str]) -> list[list[float]]:
        """Efficiently get or create embeddings for multiple queries.
        
        This method optimizes the process by:
        1. Checking cache for all queries in parallel
        2. Identifying which embeddings need generation
        3. Batch generating missing embeddings in a single API call
        4. Caching all new embeddings
        5. Returning all embeddings in order
        
        Args:
            queries: List of query strings to get embeddings for
            
        Returns:
            List of embedding vectors, one per input query, in the same order
        """
        if not queries:
            return []
        
        # Normalize all queries
        normalized_queries = [normalize_query(query, enhanced=True) for query in queries]
        model_name = self._openai.embedding_model
        
        # Build cache keys for all queries
        cache_keys = [
            f"embed:{model_name}:{self._hash_text(norm)}"
            for norm in normalized_queries
        ]
        
        # Check cache for all queries in parallel
        cached_results = await asyncio.gather(*[
            self._redis.get(key) for key in cache_keys
        ])
        
        # Identify which embeddings need generation
        embeddings_to_generate = []
        indices_to_generate = []
        result_embeddings = [None] * len(queries)
        
        for i, cached in enumerate(cached_results):
            if cached:
                result_embeddings[i] = json.loads(cached)
            else:
                embeddings_to_generate.append(normalized_queries[i])
                indices_to_generate.append(i)
        
        # Batch generate missing embeddings if any
        if embeddings_to_generate:
            logger.info(
                "Cache miss for %d/%d embeddings. Generating batch...",
                len(embeddings_to_generate),
                len(queries),
            )
            new_embeddings = await self._openai.get_embeddings_batch(embeddings_to_generate)
            
            # Cache new embeddings and populate results
            cache_tasks = []
            for idx, embedding in zip(indices_to_generate, new_embeddings):
                result_embeddings[idx] = embedding
                cache_key = cache_keys[idx]
                cache_tasks.append(
                    self._redis.set(
                        cache_key,
                        json.dumps(embedding),
                        ex=self._embedding_cache_ttl_seconds,
                    )
                )
            
            # Cache all new embeddings in parallel
            await asyncio.gather(*cache_tasks)
            logger.info("Cached %d new embeddings", len(new_embeddings))
        else:
            logger.info("All %d embeddings found in cache", len(queries))
        
        # Return embeddings in order (all should be populated now)
        return result_embeddings

    async def find_similar(
        self,
        query_embedding: list[float],
        threshold: Optional[float] = None,
        topic: Optional[str] = None,
        query_type: Optional[str] = None,
    ) -> tuple[Optional[dict], float]:
        """Find similar cached entry. Optionally override threshold for testing.
        
        Args:
            query_embedding: Query embedding vector
            threshold: Optional similarity threshold override
            topic: Optional topic for topic-partitioned search
            query_type: Optional query type for staleness checking
            
        Returns:
            Tuple of (entry dict or None, similarity score)
        """
        threshold_to_use = threshold if threshold is not None else self._threshold
        
        # Use Weaviate if enabled and available
        if self._use_weaviate:
            result = await self._find_similar_weaviate(query_embedding, threshold_to_use, topic, query_type)
            return result
        
        # Fallback to linear scan with topic partitioning
        return await self._find_similar_linear(query_embedding, threshold_to_use, topic, query_type)
    
    async def _find_similar_weaviate(
        self,
        query_embedding: list[float],
        threshold: float,
        topic: Optional[str] = None,
        query_type: Optional[str] = None,
    ) -> tuple[Optional[dict], float]:
        """Find similar cached entry using Weaviate vector search with topic filtering.
        
        This method uses Weaviate's native filtering to search only within the topic
        partition, making topic-based partitioning efficient at the database level.
        
        Args:
            query_embedding: Query embedding vector
            threshold: Similarity threshold
            topic: Optional topic for topic-partitioned search
            query_type: Optional query type for staleness checking
            
        Returns:
            Tuple of (entry dict or None, similarity score)
        """
        try:
            collection = self._weaviate.collections.get("SemanticCache")
            
            # Convert threshold to distance (cosine similarity to distance)
            # cosine similarity: 1.0 = identical, 0.0 = orthogonal
            # cosine distance: 0.0 = identical, 1.0 = orthogonal
            # distance = 1 - similarity
            # So for threshold 0.85, we want distance <= 0.15
            max_distance = 1.0 - threshold
            
            # Build Weaviate filter for topic if provided
            # This filters at the database level, so we only search within the topic partition
            topic_filter = None
            if topic:
                # Filter to only search entries with matching topic
                # This prevents cross-domain cache reuse by filtering before vector search
                topic_filter = Filter.by_property("topic").equal(topic)
                logger.debug("Filtering Weaviate search by topic: %s", topic)
            
            # Query Weaviate for nearest vector with topic filter
            # Note: Weaviate client operations are synchronous, but we're in an async context
            # We'll run them in a thread pool to avoid blocking
            import asyncio
            
            def query_weaviate():
                # Build query with optional topic filter
                # Weaviate v4+ API: filters parameter filters at database level before vector search
                # This prevents cross-domain cache reuse by only searching within topic partition
                if topic_filter:
                    result = collection.query.near_vector(
                        near_vector=query_embedding,
                        limit=1,  # Only need the best match when filtering by topic
                        return_metadata=MetadataQuery(distance=True),
                        filters=topic_filter,  # Database-level filter - prevents cross-domain reuse
                    )
                else:
                    result = collection.query.near_vector(
                        near_vector=query_embedding,
                        limit=1,
                        return_metadata=MetadataQuery(distance=True),
                    )
                return result
            
            result = await asyncio.to_thread(query_weaviate)
            
            # Extract results from Weaviate response
            # The response structure may vary by version, so we handle it flexibly
            objects = None
            if hasattr(result, 'objects'):
                objects = result.objects
            elif isinstance(result, dict) and 'data' in result:
                # Handle GraphQL-style response
                data = result['data']
                if 'Get' in data and COLLECTION_NAME in data['Get']:
                    objects = data['Get'][COLLECTION_NAME]
            
            best_entry = None
            best_similarity = 0.0
            
            if objects and len(objects) > 0:
                for obj in objects:
                    # Handle different response formats
                    if hasattr(obj, 'metadata') and obj.metadata:
                        distance = obj.metadata.distance if hasattr(obj.metadata, 'distance') else 1.0
                    elif isinstance(obj, dict) and '_additional' in obj:
                        distance = obj['_additional'].get('distance', 1.0)
                    else:
                        distance = 1.0
                    
                    similarity = 1.0 - distance
                    
                    if similarity >= threshold:
                        # Extract properties
                        if hasattr(obj, 'properties'):
                            props = obj.properties
                        elif isinstance(obj, dict):
                            props = obj
                        else:
                            continue
                        
                        entry_topic = props.get("topic")
                        
                        # Extract created_at - Weaviate returns it as datetime object
                        created_at_value = props.get("created_at")
                        # Convert datetime to ISO string for consistency with Redis format
                        if isinstance(created_at_value, datetime):
                            created_at_str = created_at_value.isoformat()
                        elif created_at_value:
                            created_at_str = str(created_at_value)
                        else:
                            created_at_str = ""
                        
                        # Convert Weaviate object to dict format
                        entry = {
                            "query_text": props.get("query_text", ""),
                            "response": props.get("response", ""),
                            "created_at": created_at_str,  # Store as ISO string for consistency
                            "ttl_seconds": props.get("ttl_seconds", 0),
                            "topic": entry_topic,
                            "embedding": query_embedding,  # We don't store embedding in response
                        }
                        
                        # Check staleness
                        if self.is_stale(entry, query_type):
                            logger.debug("Found entry but it's stale, skipping")
                            continue
                        
                        if similarity > best_similarity:
                            best_similarity = similarity
                            best_entry = entry
            
            if best_entry:
                logger.debug(
                    "Weaviate found match: topic=%s, similarity=%.3f",
                    best_entry.get("topic"),
                    best_similarity,
                )
                return best_entry, best_similarity
            
            # If no match found in topic partition and topic was specified,
            # optionally fall back to global search (without topic filter)
            if topic:
                logger.debug("No match in topic partition '%s', trying global search", topic)
                # Try without topic filter as fallback
                try:
                    def query_global():
                        return collection.query.near_vector(
                            near_vector=query_embedding,
                            limit=1,
                            return_metadata=MetadataQuery(distance=True),
                        ).do()
                    
                    global_result = await asyncio.to_thread(query_global)
                    # Process global_result similarly (code omitted for brevity)
                    # For now, we'll return None to enforce strict topic partitioning
                except Exception:
                    pass
            
            return None, 0.0
        except Exception as exc:
            logger.warning("Weaviate search failed, falling back to linear scan: %s", exc)
            return await self._find_similar_linear(query_embedding, threshold, topic, query_type)
    
    async def _find_similar_linear(
        self,
        query_embedding: list[float],
        threshold: float,
        topic: Optional[str] = None,
        query_type: Optional[str] = None,
    ) -> tuple[Optional[dict], float]:
        """Find similar cached entry using linear scan with topic partitioning."""
        best_entry = None
        best_score = 0.0
        
        # First, search within topic partition if topic is provided
        if topic:
            topic_keys_key = f"topics:{topic}"
            topic_keys = await self._redis.smembers(topic_keys_key)
            
            for key in topic_keys:
                payload = await self._redis.get(key)
                if not payload:
                    await self._redis.srem(topic_keys_key, key)
                    continue
                
                entry = json.loads(payload)
                
                # Check staleness
                if self.is_stale(entry, query_type):
                    continue
                
                score = cosine_similarity(query_embedding, entry["embedding"])
                if score > best_score:
                    best_score = score
                    best_entry = entry
        
        # If no good match in topic partition, search global cache
        # (for backward compatibility and cross-topic matches)
        if not best_entry or best_score < threshold:
            cache_keys = await self._redis.smembers("cache_keys")
            for key in cache_keys:
                # Skip if we already checked this key in topic partition
                if topic and key.startswith(f"cache:{topic}:"):
                    continue
                
                payload = await self._redis.get(key)
                if not payload:
                    await self._redis.srem("cache_keys", key)
                    continue
                
                entry = json.loads(payload)
                
                # Check staleness
                if self.is_stale(entry, query_type):
                    continue
                
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
        topic: Optional[str] = None,
    ) -> None:
        """Store response in cache with optional topic partitioning.
        
        Args:
            query: Query string
            embedding: Query embedding vector
            response: LLM response
            ttl_seconds: TTL in seconds
            topic: Optional topic for topic-partitioned storage
        """
        # Extract topic if not provided
        if topic is None:
            topic = extract_topic_keywords(query)
        
        # Use topic-prefixed cache key
        cache_key = f"cache:{topic}:{self._hash_text(query)}"
        created_at = datetime.now(timezone.utc).isoformat()
        
        # Always store in Redis for backward compatibility and TTL management
        entry = {
            "query_text": query,
            "embedding": embedding,
            "response": response,
            "created_at": created_at,
            "ttl_seconds": ttl_seconds,
            "topic": topic,
        }
        await self._redis.set(cache_key, json.dumps(entry), ex=ttl_seconds)
        
        # Add to global cache_keys set (for backward compatibility)
        await self._redis.sadd("cache_keys", cache_key)
        
        # Add to topic-specific index
        topic_keys_key = f"topics:{topic}"
        await self._redis.sadd(topic_keys_key, cache_key)
        
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
                    topic=topic,
                )
            except Exception as exc:
                logger.warning("Failed to store in Weaviate: %s", exc)
                # Continue - Redis storage succeeded
        
        logger.info("Cached response under %s (topic: %s) for %ss", cache_key, topic, ttl_seconds)
    
    async def _store_response_weaviate(
        self,
        query: str,
        embedding: list[float],
        response: str,
        created_at: str,
        ttl_seconds: int,
        cache_key: str,
        topic: Optional[str] = None,
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
        properties = {
            "query_text": query,
            "response": response,
            "created_at": created_at_dt,
            "ttl_seconds": ttl_seconds,
            "cache_key": cache_key,
        }
        if topic:
            properties["topic"] = topic
        
        await asyncio.to_thread(
            lambda: collection.data.insert(
                properties=properties,
                vector=embedding,
            )
        )

    @staticmethod
    def _hash_text(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
