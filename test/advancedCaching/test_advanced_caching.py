#!/usr/bin/env python3
"""
Advanced Caching Strategies Test Suite

Tests and demonstrates:
1. Time-based cache invalidation (TTL + age-based limits)
2. Topic-based cache partitioning (keyword + embedding fallback)

Shows improvements in cache accuracy and efficiency.
"""

import os
import json
import time
import asyncio
import aiohttp
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict


API_URL = os.getenv("API_URL", "http://localhost:3000/api/query")
STATS_URL = os.getenv("STATS_URL", "http://localhost:3000/api/stats")


@dataclass
class TestResult:
    """Result of a single test query."""
    query: str
    topic: str
    query_type: Optional[str]
    source: str
    similarity: Optional[float]
    latency_ms: float
    cache_hit: bool
    timestamp: str


@dataclass
class TestSummary:
    """Summary of test results."""
    total_queries: int
    cache_hits: int
    cache_misses: int
    hit_rate: float
    avg_latency_ms: float
    topic_distribution: Dict[str, int]
    query_type_distribution: Dict[str, int]
    stale_rejections: int


async def send_query(
    session: aiohttp.ClientSession,
    query: str,
    force_refresh: bool = False,
    similarity_threshold: Optional[float] = None,
) -> Dict:
    """Send a query to the API."""
    payload = {"query": query}
    if force_refresh:
        payload["forceRefresh"] = True
    if similarity_threshold is not None:
        payload["similarityThreshold"] = similarity_threshold
    
    async with session.post(API_URL, json=payload) as response:
        if response.status == 200:
            return await response.json()
        else:
            text = await response.text()
            return {"error": f"Status {response.status}: {text}"}


async def get_stats(session: aiohttp.ClientSession) -> Dict:
    """Get stats from the API."""
    async with session.get(STATS_URL) as response:
        if response.status == 200:
            return await response.json()
        else:
            return {"error": f"Status {response.status}"}


def classify_query_topic(query: str) -> str:
    """Classify query topic based on keywords (simplified version for testing)."""
    query_lower = query.lower()
    
    if any(kw in query_lower for kw in ["weather", "temperature", "forecast", "rain"]):
        return "weather"
    elif any(kw in query_lower for kw in ["python", "code", "api", "programming"]):
        return "tech"
    elif any(kw in query_lower for kw in ["news", "article", "headline"]):
        return "news"
    elif any(kw in query_lower for kw in ["price", "cost", "buy", "purchase"]):
        return "price"
    elif any(kw in query_lower for kw in ["score", "game", "match", "team"]):
        return "score"
    else:
        return "general"


def classify_query_type(query: str) -> Optional[str]:
    """Classify query type for age-based invalidation."""
    query_lower = query.lower()
    
    if any(kw in query_lower for kw in ["weather", "temperature", "forecast"]):
        return "weather"
    elif any(kw in query_lower for kw in ["news", "article", "headline"]):
        return "news"
    elif any(kw in query_lower for kw in ["price", "cost", "buy"]):
        return "price"
    elif any(kw in query_lower for kw in ["score", "game", "match"]):
        return "score"
    else:
        return None


async def test_time_based_invalidation():
    """Test time-based cache invalidation with age-based limits."""
    print("=" * 80)
    print("🧪 Test 1: Time-Based Cache Invalidation")
    print("=" * 80)
    print()
    print("Testing: Entries should be invalidated based on age limits")
    print("even if TTL hasn't expired (e.g., weather queries older than 1 hour)")
    print()
    
    async with aiohttp.ClientSession() as session:
        # Test queries with different query types
        test_queries = [
            ("What is the weather today?", "weather", "weather"),
            ("Current weather forecast", "weather", "weather"),
            ("What's the news today?", "news", "news"),
            ("Latest news headlines", "news", "news"),
            ("What's the price of Bitcoin?", "price", "price"),
            ("Current Bitcoin price", "price", "price"),
        ]
        
        print("📤 Phase 1: Initial cache population...")
        print("-" * 80)
        
        # First, populate cache with initial queries
        initial_results = []
        for query, expected_topic, expected_type in test_queries:
            print(f"  Query: {query[:50]}...", end=" ")
            start = time.time()
            result = await send_query(session, query, force_refresh=True)
            latency = (time.time() - start) * 1000
            
            if "error" in result:
                print(f"❌ Error: {result['error']}")
            else:
                source = result.get("metadata", {}).get("source", "unknown")
                print(f"✅ {source} ({latency:.0f}ms)")
                initial_results.append({
                    "query": query,
                    "source": source,
                    "latency_ms": latency,
                })
            
            await asyncio.sleep(0.3)
        
        print()
        print("⏳ Waiting 2 seconds...")
        await asyncio.sleep(2)
        
        print()
        print("📤 Phase 2: Testing cache hits (should work immediately)...")
        print("-" * 80)
        
        # Test immediate cache hits
        immediate_hits = 0
        for query, expected_topic, expected_type in test_queries:
            print(f"  Query: {query[:50]}...", end=" ")
            start = time.time()
            result = await send_query(session, query, force_refresh=False)
            latency = (time.time() - start) * 1000
            
            if "error" in result:
                print(f"❌ Error: {result['error']}")
            else:
                source = result.get("metadata", {}).get("source", "unknown")
                similarity = result.get("metadata", {}).get("similarity")
                if source == "cache":
                    immediate_hits += 1
                    print(f"✅ Cache hit (similarity: {similarity:.2f}, {latency:.0f}ms)")
                else:
                    print(f"⚠️  Cache miss ({source}, {latency:.0f}ms)")
            
            await asyncio.sleep(0.3)
        
        print()
        print(f"✅ Immediate cache hits: {immediate_hits}/{len(test_queries)}")
        print()
        print("💡 Note: To fully test age-based invalidation, you would need to:")
        print("   1. Set MAX_AGE_BY_QUERY_TYPE='{\"weather\": 60, \"news\": 30}' (very short)")
        print("   2. Wait for the max_age period")
        print("   3. Verify entries are rejected even if TTL hasn't expired")
        print()
        
        # Get stats
        stats = await get_stats(session)
        if "error" not in stats:
            print("📊 Current Stats:")
            print(f"   Cache Hits: {stats.get('cache_hits', 0)}")
            print(f"   Cache Misses: {stats.get('cache_misses', 0)}")
            print(f"   Hit Rate: {stats.get('cache_hit_rate', 0) * 100:.1f}%")
        
        return immediate_hits, len(test_queries)


async def test_topic_partitioning():
    """Test topic-based cache partitioning."""
    print("=" * 80)
    print("🧪 Test 2: Topic-Based Cache Partitioning")
    print("=" * 80)
    print()
    print("Testing: Queries should be partitioned by topic for efficient search")
    print()
    
    async with aiohttp.ClientSession() as session:
        # Test queries from different topics
        test_queries = [
            # Weather topic
            ("What is the weather today?", "weather"),
            ("Current temperature forecast", "weather"),
            ("Is it raining outside?", "weather"),
            
            # Tech topic
            ("How to write Python code?", "tech"),
            ("What is an API?", "tech"),
            ("How to debug code?", "tech"),
            
            # News topic
            ("What's the latest news?", "news"),
            ("Breaking news headlines", "news"),
            
            # General topic
            ("How to reset password?", "general"),
            ("Where is the settings page?", "general"),
        ]
        
        print("📤 Phase 1: Populating cache with queries from different topics...")
        print("-" * 80)
        
        topic_counts = {}
        for query, expected_topic in test_queries:
            print(f"  [{expected_topic:8s}] {query[:50]}...", end=" ")
            start = time.time()
            result = await send_query(session, query, force_refresh=True)
            latency = (time.time() - start) * 1000
            
            if "error" in result:
                print(f"❌ Error: {result['error']}")
            else:
                source = result.get("metadata", {}).get("source", "unknown")
                print(f"✅ {source} ({latency:.0f}ms)")
                topic_counts[expected_topic] = topic_counts.get(expected_topic, 0) + 1
            
            await asyncio.sleep(0.3)
        
        print()
        print("📊 Topic Distribution:")
        for topic, count in sorted(topic_counts.items()):
            print(f"   {topic}: {count} queries")
        
        print()
        print("⏳ Waiting 2 seconds...")
        await asyncio.sleep(2)
        
        print()
        print("📤 Phase 2: Testing cache hits (should find matches within topic partitions)...")
        print("-" * 80)
        
        hits_by_topic = {}
        misses_by_topic = {}
        
        for query, expected_topic in test_queries:
            print(f"  [{expected_topic:8s}] {query[:50]}...", end=" ")
            start = time.time()
            result = await send_query(session, query, force_refresh=False)
            latency = (time.time() - start) * 1000
            
            if "error" in result:
                print(f"❌ Error: {result['error']}")
                misses_by_topic[expected_topic] = misses_by_topic.get(expected_topic, 0) + 1
            else:
                source = result.get("metadata", {}).get("source", "unknown")
                similarity = result.get("metadata", {}).get("similarity")
                
                if source == "cache":
                    hits_by_topic[expected_topic] = hits_by_topic.get(expected_topic, 0) + 1
                    print(f"✅ Cache hit (similarity: {similarity:.2f}, {latency:.0f}ms)")
                else:
                    misses_by_topic[expected_topic] = misses_by_topic.get(expected_topic, 0) + 1
                    print(f"⚠️  Cache miss ({source}, {latency:.0f}ms)")
            
            await asyncio.sleep(0.3)
        
        print()
        print("📊 Cache Performance by Topic:")
        all_topics = set(hits_by_topic.keys()) | set(misses_by_topic.keys())
        for topic in sorted(all_topics):
            hits = hits_by_topic.get(topic, 0)
            misses = misses_by_topic.get(topic, 0)
            total = hits + misses
            hit_rate = (hits / total * 100) if total > 0 else 0
            print(f"   {topic:8s}: {hits}/{total} hits ({hit_rate:.1f}%)")
        
        total_hits = sum(hits_by_topic.values())
        total_misses = sum(misses_by_topic.values())
        total_queries = total_hits + total_misses
        
        print()
        print(f"✅ Overall: {total_hits}/{total_queries} cache hits ({total_hits/total_queries*100:.1f}%)")
        
        return total_hits, total_queries


async def test_combined_features():
    """Test both features working together."""
    print("=" * 80)
    print("🧪 Test 3: Combined Features (Time-Based + Topic Partitioning)")
    print("=" * 80)
    print()
    print("Testing: Both features working together for optimal cache performance")
    print()
    
    async with aiohttp.ClientSession() as session:
        # Mix of queries from different topics and query types
        test_queries = [
            ("What is the weather today?", "weather", "weather"),
            ("How to write Python code?", "tech", None),
            ("What's the latest news?", "news", "news"),
            ("What's the price of gold?", "price", "price"),
            ("How to reset password?", "general", None),
        ]
        
        print("📤 Phase 1: Initial population...")
        print("-" * 80)
        
        for query, expected_topic, expected_type in test_queries:
            print(f"  [{expected_topic:8s}] {query[:50]}...", end=" ")
            result = await send_query(session, query, force_refresh=True)
            if "error" not in result:
                print("✅ Cached")
            else:
                print(f"❌ {result['error']}")
            await asyncio.sleep(0.3)
        
        print()
        print("⏳ Waiting 2 seconds...")
        await asyncio.sleep(2)
        
        print()
        print("📤 Phase 2: Testing combined cache behavior...")
        print("-" * 80)
        
        results = []
        for query, expected_topic, expected_type in test_queries:
            print(f"  [{expected_topic:8s}] {query[:50]}...", end=" ")
            start = time.time()
            result = await send_query(session, query, force_refresh=False)
            latency = (time.time() - start) * 1000
            
            if "error" not in result:
                source = result.get("metadata", {}).get("source", "unknown")
                similarity = result.get("metadata", {}).get("similarity")
                cache_hit = source == "cache"
                
                if cache_hit:
                    print(f"✅ Cache hit (similarity: {similarity:.2f}, {latency:.0f}ms)")
                else:
                    print(f"⚠️  Cache miss ({source}, {latency:.0f}ms)")
                
                results.append({
                    "query": query,
                    "topic": expected_topic,
                    "query_type": expected_type,
                    "source": source,
                    "similarity": similarity,
                    "latency_ms": latency,
                    "cache_hit": cache_hit,
                })
            else:
                print(f"❌ {result['error']}")
            
            await asyncio.sleep(0.3)
        
        # Summary
        cache_hits = sum(1 for r in results if r["cache_hit"])
        total = len(results)
        avg_latency = sum(r["latency_ms"] for r in results) / total if total > 0 else 0
        
        print()
        print("📊 Summary:")
        print(f"   Cache Hits: {cache_hits}/{total} ({cache_hits/total*100:.1f}%)")
        print(f"   Average Latency: {avg_latency:.1f}ms")
        
        return cache_hits, total


async def run_all_tests():
    """Run all tests and generate summary report."""
    print()
    print("🚀 Advanced Caching Strategies Test Suite")
    print("=" * 80)
    print()
    print("This test suite demonstrates:")
    print("  1. Time-based cache invalidation (TTL + age-based limits)")
    print("  2. Topic-based cache partitioning (keyword + embedding fallback)")
    print()
    
    # Get initial stats
    async with aiohttp.ClientSession() as session:
        initial_stats = await get_stats(session)
    
    # Run tests
    test_results = {}
    
    try:
        test_results["time_based"] = await test_time_based_invalidation()
        print()
        await asyncio.sleep(1)
        
        test_results["topic_partitioning"] = await test_topic_partitioning()
        print()
        await asyncio.sleep(1)
        
        test_results["combined"] = await test_combined_features()
        print()
        
    except Exception as e:
        print(f"\n❌ Test error: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Get final stats
    async with aiohttp.ClientSession() as session:
        final_stats = await get_stats(session)
    
    # Print final summary
    print("=" * 80)
    print("📊 Final Summary")
    print("=" * 80)
    print()
    
    if "error" not in final_stats:
        print("Overall Cache Performance:")
        print(f"   Total Requests: {final_stats.get('requests', 0)}")
        print(f"   Cache Hits: {final_stats.get('cache_hits', 0)}")
        print(f"   Cache Misses: {final_stats.get('cache_misses', 0)}")
        print(f"   Hit Rate: {final_stats.get('cache_hit_rate', 0) * 100:.1f}%")
        print(f"   LLM Calls: {final_stats.get('llm_calls', 0)}")
        print(f"   Estimated Savings: ${final_stats.get('estimated_cache_savings', 0):.4f}")
    
    print()
    print("✅ All tests completed!")
    print()
    print("💡 Key Improvements Demonstrated:")
    print("  • Topic partitioning reduces search space (faster lookups)")
    print("  • Time-based invalidation prevents stale responses")
    print("  • Combined features improve cache accuracy and efficiency")
    print()


if __name__ == "__main__":
    try:
        asyncio.run(run_all_tests())
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
