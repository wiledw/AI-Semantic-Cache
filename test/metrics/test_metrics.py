#!/usr/bin/env python3
"""
Test script for metrics collection and visualization.
Generates test queries and verifies metrics are being collected.
"""

import asyncio
import aiohttp
import json
import time
from datetime import datetime
from typing import List, Dict


API_URL = "http://localhost:3000/api/query"
METRICS_URL = "http://localhost:3000/api/metrics"
STATS_URL = "http://localhost:3000/api/stats"


async def send_query(session: aiohttp.ClientSession, query: str, force_refresh: bool = False) -> Dict:
    """Send a query to the API."""
    payload = {"query": query}
    if force_refresh:
        payload["forceRefresh"] = True
    
    async with session.post(API_URL, json=payload) as response:
        if response.status == 200:
            return await response.json()
        else:
            text = await response.text()
            return {"error": f"Status {response.status}: {text}"}


async def get_metrics(session: aiohttp.ClientSession, hours: int = 1, interval: int = 60) -> Dict:
    """Get metrics from the API."""
    async with session.get(f"{METRICS_URL}?hours={hours}&interval_seconds={interval}") as response:
        if response.status == 200:
            return await response.json()
        else:
            return {"error": f"Status {response.status}"}


async def get_stats(session: aiohttp.ClientSession) -> Dict:
    """Get stats from the API."""
    async with session.get(STATS_URL) as response:
        if response.status == 200:
            return await response.json()
        else:
            return {"error": f"Status {response.status}"}


async def test_metrics_collection():
    """Test metrics collection by sending various queries."""
    print("=" * 60)
    print("🧪 Testing Metrics Collection and Visualization")
    print("=" * 60)
    print()
    
    # Test queries - designed to test different scenarios
    test_queries = [
        # Group 1: Password reset (exact and similar)
        ("How to reset password?", False),
        ("How do I reset my password?", False),
        ("Password reset instructions", False),
        ("How to reset password?", False),  # Exact match
        
        # Group 2: Weather (time-sensitive)
        ("What is the weather today?", False),
        ("Current weather conditions", False),
        ("What is the weather today?", False),  # Exact match
        
        # Group 3: Profile updates
        ("How to update profile?", False),
        ("Update my profile information", False),
        ("Profile update guide", False),
        
        # Group 4: Force refresh test
        ("How to change email?", False),
        ("How to change email?", True),  # Force refresh
    ]
    
    async with aiohttp.ClientSession() as session:
        print("📤 Phase 1: Sending test queries...")
        print("-" * 60)
        
        results = []
        for i, (query, force_refresh) in enumerate(test_queries, 1):
            print(f"[{i:2d}/{len(test_queries)}] Query: {query[:50]}...", end=" ")
            if force_refresh:
                print("(force refresh)", end=" ")
            
            start_time = time.time()
            result = await send_query(session, query, force_refresh)
            latency = (time.time() - start_time) * 1000
            
            if "error" in result:
                print(f"❌ Error: {result['error']}")
            else:
                source = result.get("metadata", {}).get("source", "unknown")
                similarity = result.get("metadata", {}).get("similarity")
                if similarity:
                    print(f"✅ {source} (similarity: {similarity:.2f}, latency: {latency:.0f}ms)")
                else:
                    print(f"✅ {source} (latency: {latency:.0f}ms)")
            
            results.append({
                "query": query,
                "result": result,
                "latency_ms": latency,
            })
            
            # Small delay between requests
            await asyncio.sleep(0.5)
        
        print()
        print("⏳ Waiting 2 seconds for metrics to aggregate...")
        await asyncio.sleep(2)
        
        print()
        print("📊 Phase 2: Checking metrics...")
        print("-" * 60)
        
        # Get current stats
        stats = await get_stats(session)
        if "error" not in stats:
            print("Current Stats:")
            print(f"  Total Requests: {stats.get('requests', 0)}")
            print(f"  Cache Hits: {stats.get('cache_hits', 0)}")
            print(f"  Cache Misses: {stats.get('cache_misses', 0)}")
            print(f"  Hit Rate: {stats.get('cache_hit_rate', 0) * 100:.1f}%")
            print(f"  LLM Calls: {stats.get('llm_calls', 0)}")
            print(f"  Estimated Savings: ${stats.get('estimated_cache_savings', 0):.4f}")
        else:
            print(f"❌ Error getting stats: {stats['error']}")
        
        print()
        
        # Get time-series metrics
        metrics = await get_metrics(session, hours=1, interval=60)
        if "error" not in metrics:
            data_points = metrics.get("data", [])
            current_stats = metrics.get("current_stats", {})
            
            print(f"Time-Series Metrics:")
            print(f"  Data Points: {len(data_points)}")
            if data_points:
                print(f"  Time Range: {data_points[0].get('timestamp')} to {data_points[-1].get('timestamp')}")
                print()
                print("  Recent Data Points:")
                for point in data_points[-5:]:  # Show last 5 points
                    timestamp = point.get("timestamp", "")
                    requests = point.get("requests", 0)
                    hits = point.get("hits", 0)
                    hit_rate = point.get("hit_rate", 0)
                    avg_latency = point.get("avg_latency_ms", 0)
                    print(f"    {timestamp}: {requests} requests, {hits} hits, "
                          f"{hit_rate*100:.1f}% hit rate, {avg_latency:.1f}ms avg latency")
            
            print()
            print("  Current Aggregate Stats:")
            print(f"    Total Requests: {current_stats.get('total_requests', 0)}")
            print(f"    Total Hits: {current_stats.get('total_hits', 0)}")
            print(f"    Total Misses: {current_stats.get('total_misses', 0)}")
            print(f"    Hit Rate: {current_stats.get('hit_rate', 0) * 100:.1f}%")
            print(f"    Avg Latency: {current_stats.get('avg_latency_ms', 0):.2f}ms")
        else:
            print(f"❌ Error getting metrics: {metrics['error']}")
        
        print()
        print("=" * 60)
        print("✅ Test Complete!")
        print("=" * 60)
        print()
        print("📈 Next Steps:")
        print("   1. Open http://localhost:5173 in your browser")
        print("   2. Check the 'Cache Performance Over Time' chart")
        print("   3. The chart should show:")
        print("      - Hit rate increasing over time")
        print("      - Request volume per time interval")
        print("      - Summary statistics")
        print()
        print("💡 Tip: Run this script multiple times to see the hit rate improve!")


if __name__ == "__main__":
    try:
        asyncio.run(test_metrics_collection())
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
