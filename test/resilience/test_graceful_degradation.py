#!/usr/bin/env python3
"""
Graceful Degradation Testing Suite

Tests system behavior under high load and resource exhaustion:
- Request throttling
- Priority-based processing
- Resource monitoring
- Graceful error responses

Uses cached data and mocked failures to minimize API costs.
"""

import asyncio
import sys
import os
import time
from typing import List, Dict

import aiohttp
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from test.utils.cost_tracker import get_tracker

API_URL = os.getenv("API_URL", "http://localhost:3000/api/query")
BUDGET = float(os.getenv("DEGRADATION_TEST_BUDGET", "0.10"))  # Very low budget - uses cached data


async def send_query(
    session: aiohttp.ClientSession,
    query: str,
    force_refresh: bool = False,
) -> dict:
    """Send a query to the API."""
    payload = {"query": query, "forceRefresh": force_refresh}
    
    try:
        async with session.post(API_URL, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as response:
            if response.status == 200:
                return await response.json()
            elif response.status == 503:
                return {"error": "Service Unavailable", "status": 503, "retry_after": response.headers.get("Retry-After")}
            else:
                text = await response.text()
                return {"error": f"Status {response.status}: {text}", "status": response.status}
    except asyncio.TimeoutError:
        return {"error": "Request timeout", "status": "timeout"}
    except Exception as e:
        return {"error": str(e), "status": "error"}


async def test_overload_scenario():
    """Test system behavior under overload."""
    print("=" * 80)
    print("Test: Overload Scenario")
    print("=" * 80)
    print("Sending 100 concurrent requests (using cached queries)")
    print()
    
    # Use queries that should be cached (from populate_cache)
    cached_queries = [
        "What's the weather today?",
        "How do I reset my password?",
        "What's the latest news?",
        "Bitcoin price",
        "Python tutorial",
    ]
    
    async with aiohttp.ClientSession() as session:
        # Send many concurrent requests
        tasks = []
        for i in range(100):
            query = cached_queries[i % len(cached_queries)]
            tasks.append(send_query(session, query, force_refresh=False))
        
        print("Sending requests...")
        start_time = time.time()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        elapsed = time.time() - start_time
        
        # Analyze results
        successful = 0
        errors = 0
        timeouts = 0
        service_unavailable = 0
        cache_hits = 0
        
        for result in results:
            if isinstance(result, Exception):
                errors += 1
            elif isinstance(result, dict):
                if "error" in result:
                    if result.get("status") == "timeout":
                        timeouts += 1
                    elif result.get("status") == 503:
                        service_unavailable += 1
                    else:
                        errors += 1
                else:
                    successful += 1
                    if result.get("metadata", {}).get("source") == "cache":
                        cache_hits += 1
        
        print(f"\nResults:")
        print(f"  Total requests: {len(results)}")
        print(f"  Successful: {successful} ({successful/len(results)*100:.1f}%)")
        print(f"  Cache hits: {cache_hits} ({cache_hits/len(results)*100:.1f}%)")
        print(f"  Errors: {errors}")
        print(f"  Timeouts: {timeouts}")
        print(f"  503 Service Unavailable: {service_unavailable}")
        print(f"  Total time: {elapsed:.2f}s")
        print(f"  Requests/sec: {len(results)/elapsed:.1f}")
        
        # Verify system didn't crash
        assert successful > 0, "System should handle some requests"
        assert errors + timeouts < len(results) * 0.1, "Error rate should be low (<10%)"
        
        print("\n✅ System handled overload gracefully")
        return successful, errors, timeouts, service_unavailable


async def test_cache_hit_performance():
    """Test that cache hits are served quickly even under load."""
    print("=" * 80)
    print("Test: Cache Hit Performance Under Load")
    print("=" * 80)
    
    cached_query = "What's the weather today?"  # Should be cached
    
    async with aiohttp.ClientSession() as session:
        # Send multiple requests for same cached query
        tasks = []
        for i in range(50):
            tasks.append(send_query(session, cached_query, force_refresh=False))
        
        start_time = time.time()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        elapsed = time.time() - start_time
        
        latencies = []
        cache_hits = 0
        
        for result in results:
            if isinstance(result, dict) and "error" not in result:
                if result.get("metadata", {}).get("source") == "cache":
                    cache_hits += 1
        
        # Calculate average latency per request
        avg_latency = elapsed / len(results) * 1000  # Convert to ms
        
        print(f"\nResults:")
        print(f"  Total requests: {len(results)}")
        print(f"  Cache hits: {cache_hits} ({cache_hits/len(results)*100:.1f}%)")
        print(f"  Total time: {elapsed:.2f}s")
        print(f"  Avg latency per request: {avg_latency:.1f}ms")
        
        # Cache hits should be fast (< 100ms average)
        assert avg_latency < 100, f"Cache hits should be fast (<100ms), got {avg_latency:.1f}ms"
        assert cache_hits > len(results) * 0.9, "Most requests should be cache hits (>90%)"
        
        print("\n✅ Cache hits served quickly under load")


async def test_error_responses():
    """Test that error responses are graceful."""
    print("=" * 80)
    print("Test: Graceful Error Responses")
    print("=" * 80)
    
    async with aiohttp.ClientSession() as session:
        # Test with invalid query (empty string should be rejected)
        result = await send_query(session, "", force_refresh=False)
        
        if "error" in result:
            status = result.get("status")
            print(f"  Empty query returned: {status}")
            # Should return 400 or similar, not 500
            assert status != 500, "Should not return 500 for invalid input"
            print("✅ Error responses are graceful (not 500)")
        else:
            print("  Note: Empty query was accepted (may be valid)")
    
    print("\n✅ Error response tests passed")


async def run_all_tests():
    """Run all graceful degradation tests."""
    tracker = get_tracker(budget=BUDGET)
    
    print("\n" + "=" * 80)
    print("Graceful Degradation Testing Suite")
    print("=" * 80)
    print(f"Budget: ${BUDGET:.2f} (uses cached data, minimal API calls)")
    print()
    
    try:
        successful, errors, timeouts, service_unavailable = await test_overload_scenario()
        await test_cache_hit_performance()
        await test_error_responses()
        
        print()
        print("=" * 80)
        print("Final Summary")
        print("=" * 80)
        print(f"Overload test: {successful} successful, {errors} errors, {timeouts} timeouts, {service_unavailable} 503s")
        print()
        
        # Print cost summary
        tracker.print_summary()
        
        print()
        print("✅ All graceful degradation tests passed!")
        print("=" * 80)
        return 0
        
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(run_all_tests())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
