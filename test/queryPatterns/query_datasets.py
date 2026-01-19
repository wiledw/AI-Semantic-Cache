#!/usr/bin/env python3
"""
Query Datasets for Pattern Testing

Comprehensive query datasets covering all test pattern categories.
Includes expected behavior annotations for validation.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class QueryPattern:
    """Represents a query pattern with metadata."""
    query: str
    category: str
    expected_cache_hit: bool
    expected_similarity_min: Optional[float] = None
    expected_similarity_max: Optional[float] = None
    expected_topic: Optional[str] = None
    expected_query_type: Optional[str] = None
    notes: Optional[str] = None


# Exact Duplicate Queries
EXACT_DUPLICATES = [
    QueryPattern("What's the weather today?", "exact_duplicate", True, expected_similarity_min=1.0, expected_topic="weather"),
    QueryPattern("What's the weather today?", "exact_duplicate", True, expected_similarity_min=1.0, expected_topic="weather"),
    QueryPattern("What's the weather today?", "exact_duplicate", True, expected_similarity_min=1.0, expected_topic="weather"),
    QueryPattern("How do I reset my password?", "exact_duplicate", True, expected_similarity_min=1.0, expected_topic="general"),
    QueryPattern("How do I reset my password?", "exact_duplicate", True, expected_similarity_min=1.0, expected_topic="general"),
]


# Semantically Similar Queries (different wording, same intent)
SEMANTIC_VARIATIONS = [
    # Weather variations
    QueryPattern("What's the weather today?", "semantic_similar", True, expected_similarity_min=0.85, expected_topic="weather", expected_query_type="weather"),
    QueryPattern("How's the weather right now?", "semantic_similar", True, expected_similarity_min=0.85, expected_topic="weather", expected_query_type="weather"),
    QueryPattern("Current weather conditions", "semantic_similar", True, expected_similarity_min=0.85, expected_topic="weather", expected_query_type="weather"),
    QueryPattern("What's the weather like?", "semantic_similar", True, expected_similarity_min=0.85, expected_topic="weather", expected_query_type="weather"),
    
    # Password reset variations
    QueryPattern("How do I reset my password?", "semantic_similar", True, expected_similarity_min=0.85, expected_topic="general"),
    QueryPattern("I need to change my password", "semantic_similar", True, expected_similarity_min=0.85, expected_topic="general"),
    QueryPattern("Where can I update my password?", "semantic_similar", True, expected_similarity_min=0.85, expected_topic="general"),
    QueryPattern("Password reset instructions", "semantic_similar", True, expected_similarity_min=0.85, expected_topic="general"),
    
    # News variations
    QueryPattern("What's the latest news?", "semantic_similar", True, expected_similarity_min=0.85, expected_topic="news", expected_query_type="news"),
    QueryPattern("Breaking news headlines", "semantic_similar", True, expected_similarity_min=0.85, expected_topic="news", expected_query_type="news"),
    QueryPattern("Today's news", "semantic_similar", True, expected_similarity_min=0.85, expected_topic="news", expected_query_type="news"),
]


# Completely Unrelated Queries (different topics, no semantic similarity)
# These queries are intentionally unrelated to anything cached during population
# Topics: car maintenance, music, science, pets, cooking (different), health, travel (different)
UNRELATED_QUERIES = [
    QueryPattern("How to change a tire?", "unrelated", False, expected_similarity_max=0.5, expected_topic="general", notes="Car maintenance - not cached"),
    QueryPattern("How to learn guitar?", "unrelated", False, expected_similarity_max=0.5, expected_topic="general", notes="Music - not cached"),
    QueryPattern("What is quantum physics?", "unrelated", False, expected_similarity_max=0.5, expected_topic="general", notes="Science - not cached"),
    QueryPattern("How to train a dog?", "unrelated", False, expected_similarity_max=0.5, expected_topic="general", notes="Pets - not cached"),
    QueryPattern("Best restaurants in Tokyo?", "unrelated", False, expected_similarity_max=0.5, expected_topic="general", notes="Travel/dining - different location than cached"),
    QueryPattern("How to make pasta?", "unrelated", False, expected_similarity_max=0.5, expected_topic="general", notes="Cooking - different from cached cake recipe"),
]


# Time-Sensitive Queries
TIME_SENSITIVE_QUERIES = [
    QueryPattern("What's the current Bitcoin price?", "time_sensitive", True, expected_topic="price", expected_query_type="price", notes="Should have short TTL"),
    QueryPattern("Latest news headlines", "time_sensitive", True, expected_topic="news", expected_query_type="news", notes="Should have short TTL"),
    QueryPattern("Today's weather forecast", "time_sensitive", True, expected_topic="weather", expected_query_type="weather", notes="Should have short TTL"),
    QueryPattern("Current stock prices", "time_sensitive", True, expected_topic="price", expected_query_type="price", notes="Should have short TTL"),
    QueryPattern("Game score update", "time_sensitive", True, expected_topic="score", expected_query_type="score", notes="Should have very short TTL"),
]


# Evergreen Queries
EVERGREEN_QUERIES = [
    QueryPattern("What is Python programming?", "evergreen", True, expected_topic="tech", notes="Should have long TTL"),
    QueryPattern("How does machine learning work?", "evergreen", True, expected_topic="tech", notes="Should have long TTL"),
    QueryPattern("History of computers", "evergreen", True, expected_topic="tech", notes="Should have long TTL"),
    QueryPattern("What is the capital of France?", "evergreen", True, expected_topic="general", notes="Should have long TTL"),
    QueryPattern("How to bake a cake?", "evergreen", True, expected_topic="general", notes="Should have long TTL"),
]


# Varying Complexity and Length
VARYING_COMPLEXITY = [
    QueryPattern("Weather?", "short", True, expected_topic="weather", notes="Very short query"),
    QueryPattern("What's the weather like in New York City today?", "medium", True, expected_topic="weather", notes="Medium length query"),
    QueryPattern("Can you tell me what the current weather conditions are in New York City, including temperature, humidity, wind speed, and any precipitation expected?", "long", True, expected_topic="weather", notes="Long query"),
]


# Different Languages
MULTILINGUAL_QUERIES = [
    QueryPattern("What's the weather?", "english", True, expected_topic="weather", notes="English"),
    QueryPattern("¿Cuál es el clima?", "spanish", True, expected_topic="weather", notes="Spanish"),
    QueryPattern("Quel est le temps?", "french", True, expected_topic="weather", notes="French"),
    QueryPattern("天气怎么样？", "chinese", True, expected_topic="weather", notes="Chinese"),
    QueryPattern("天気はどうですか？", "japanese", True, expected_topic="weather", notes="Japanese"),
]


# Special Characters
SPECIAL_CHARACTER_QUERIES = [
    QueryPattern("What's the weather in São Paulo?", "unicode", True, expected_topic="weather", notes="Unicode characters"),
    QueryPattern("Weather 🌤️", "emoji", True, expected_topic="weather", notes="Emoji characters"),
    QueryPattern("What's the weather?!", "punctuation", True, expected_topic="weather", notes="Special punctuation"),
    QueryPattern("'; DROP TABLE--", "sql_injection", False, expected_topic="general", notes="SQL injection attempt - should be handled safely"),
    QueryPattern("<script>alert('xss')</script>", "xss", False, expected_topic="general", notes="XSS attempt - should be handled safely"),
]


# Rapid Succession Queries (for load testing)
RAPID_SUCCESSION_BASE = [
    "What's the weather today?",
    "How do I reset my password?",
    "What's the latest news?",
    "Bitcoin price",
    "Python tutorial",
]


# All queries combined
ALL_QUERIES = (
    EXACT_DUPLICATES +
    SEMANTIC_VARIATIONS +
    UNRELATED_QUERIES +
    TIME_SENSITIVE_QUERIES +
    EVERGREEN_QUERIES +
    VARYING_COMPLEXITY +
    MULTILINGUAL_QUERIES +
    SPECIAL_CHARACTER_QUERIES
)


def get_queries_by_category(category: str) -> list[QueryPattern]:
    """
    Get queries by category.
    
    Args:
        category: Category name
        
    Returns:
        List of QueryPattern objects
    """
    category_map = {
        "exact_duplicate": EXACT_DUPLICATES,
        "semantic_similar": SEMANTIC_VARIATIONS,
        "unrelated": UNRELATED_QUERIES,
        "time_sensitive": TIME_SENSITIVE_QUERIES,
        "evergreen": EVERGREEN_QUERIES,
        "varying_complexity": VARYING_COMPLEXITY,
        "multilingual": MULTILINGUAL_QUERIES,
        "special_characters": SPECIAL_CHARACTER_QUERIES,
    }
    
    return category_map.get(category, [])


def get_all_queries() -> list[QueryPattern]:
    """Get all queries."""
    return ALL_QUERIES.copy()
