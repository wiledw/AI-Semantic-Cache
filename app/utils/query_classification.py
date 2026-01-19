from __future__ import annotations

import json
import logging
from typing import Optional

from redis.asyncio import Redis as AsyncRedis

from app.utils.similarity import cosine_similarity

logger = logging.getLogger(__name__)


TIME_SENSITIVE_KEYWORDS = {
    "today",
    "now",
    "current",
    "weather",
    "news",
    "price",
    "score",
}

# Topic keywords for topic-based cache partitioning
# Each topic maps to a list of keywords that indicate that topic
TOPIC_KEYWORDS: dict[str, list[str]] = {
    "weather": ["weather", "temperature", "forecast", "rain", "snow", "sunny", "cloudy", "humidity", "wind"],
    "tech": ["python", "code", "api", "programming", "software", "algorithm", "function", "variable", "debug", "git"],
    "news": ["news", "article", "headline", "breaking", "report", "story"],
    "price": ["price", "cost", "expensive", "cheap", "buy", "purchase", "discount", "sale"],
    "score": ["score", "game", "match", "team", "player", "win", "lose", "championship"],
    "general": [],  # Fallback topic
}

# Query type classification for age-based invalidation
# Maps query types to their classification keywords
QUERY_TYPE_KEYWORDS: dict[str, list[str]] = {
    "weather": ["weather", "temperature", "forecast", "rain", "snow"],
    "news": ["news", "article", "headline", "breaking"],
    "price": ["price", "cost", "buy", "purchase"],
    "score": ["score", "game", "match", "team"],
}


def is_time_sensitive(query: str) -> bool:
    lowered = query.lower()
    return any(keyword in lowered for keyword in TIME_SENSITIVE_KEYWORDS)


def extract_topic_keywords(query: str) -> str:
    """Extract topic from query using keyword matching.
    
    Args:
        query: Input query string
        
    Returns:
        Topic name (e.g., "weather", "tech", "general")
    """
    lowered = query.lower()
    
    # Check each topic's keywords
    for topic, keywords in TOPIC_KEYWORDS.items():
        if topic == "general":
            continue  # Skip general, it's the fallback
        if any(keyword in lowered for keyword in keywords):
            return topic
    
    # No match found, return general topic
    return "general"


def get_query_type(query: str) -> Optional[str]:
    """Get query type for age-based invalidation.
    
    Args:
        query: Input query string
        
    Returns:
        Query type string (e.g., "weather", "news", "price", "score") or None if not classified
    """
    lowered = query.lower()
    
    for query_type, keywords in QUERY_TYPE_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return query_type
    
    return None


def get_max_age_for_query_type(query_type: Optional[str], max_age_by_query_type: dict[str, int]) -> Optional[int]:
    """Get max age in seconds for a given query type.
    
    Args:
        query_type: Query type string (e.g., "weather", "news") or None
        max_age_by_query_type: Dictionary mapping query types to max age in seconds
        
    Returns:
        Max age in seconds, or None if query_type is None or not in config
    """
    if query_type is None:
        return None
    return max_age_by_query_type.get(query_type)


async def extract_topic_embedding(
    query: str,
    query_embedding: list[float],
    redis_client: Optional[AsyncRedis],
    similarity_threshold: float = 0.7,
) -> str:
    """Extract topic using embedding-based similarity to topic centroids.
    
    This is a fallback when keyword-based extraction doesn't find a match.
    Compares query embedding to stored topic centroids and returns the most similar topic.
    
    Args:
        query: Query string (for logging)
        query_embedding: Query embedding vector
        redis_client: Redis client for accessing topic centroids
        similarity_threshold: Minimum similarity to assign a topic (default: 0.7)
        
    Returns:
        Topic name (e.g., "weather", "tech", "general")
    """
    if redis_client is None:
        logger.debug("Redis client not available, using general topic")
        return "general"
    
    try:
        best_topic = "general"
        best_similarity = 0.0
        
        # Check each topic's centroid
        for topic in TOPIC_KEYWORDS.keys():
            if topic == "general":
                continue  # Skip general, it's the fallback
            
            centroid_key = f"topic_centroid:{topic}"
            centroid_json = await redis_client.get(centroid_key)
            
            if centroid_json:
                try:
                    centroid = json.loads(centroid_json)
                    similarity = cosine_similarity(query_embedding, centroid)
                    
                    if similarity > best_similarity:
                        best_similarity = similarity
                        best_topic = topic
                except (json.JSONDecodeError, ValueError, TypeError) as exc:
                    logger.warning("Failed to parse centroid for topic %s: %s", topic, exc)
                    continue
        
        # Only assign topic if similarity is above threshold
        if best_similarity >= similarity_threshold:
            logger.debug(
                "Assigned topic '%s' via embedding similarity (%.3f) for query: %s",
                best_topic,
                best_similarity,
                query[:50],
            )
            return best_topic
        else:
            logger.debug(
                "No topic centroid match above threshold (best: %.3f), using general",
                best_similarity,
            )
            return "general"
            
    except Exception as exc:
        logger.warning("Failed to extract topic via embedding: %s", exc)
        return "general"


async def extract_topic_hybrid(
    query: str,
    query_embedding: Optional[list[float]] = None,
    redis_client: Optional[AsyncRedis] = None,
) -> str:
    """Extract topic using hybrid approach: keywords first, then embedding fallback.
    
    Args:
        query: Query string
        query_embedding: Optional query embedding vector (for embedding fallback)
        redis_client: Optional Redis client (for accessing topic centroids)
        
    Returns:
        Topic name
    """
    # First try keyword-based extraction
    topic = extract_topic_keywords(query)
    
    # If keyword extraction returned "general" and we have embedding, try embedding-based
    if topic == "general" and query_embedding is not None and redis_client is not None:
        topic = await extract_topic_embedding(query, query_embedding, redis_client)
    
    return topic
