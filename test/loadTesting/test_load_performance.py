#!/usr/bin/env python3
"""
Load Performance Testing Script

Tests system performance under various load scenarios.
Uses pre-populated cache to minimize API costs.
"""

import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

import aiohttp
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from test.loadTesting.load_test_scenarios import get_scenario, get_all_scenarios, LOAD_TEST_QUERIES
from test.utils.cost_tracker import get_tracker

API_URL = os.getenv("API_URL", "http://localhost:3000/api/query")
BUDGET = float(os.getenv("LOAD_TEST_BUDGET", "0.60"))


@dataclass
class RequestResult:
    """Result of a single request."""
    timestamp: float
    latency_ms: float
    success: bool
    cache_hit: bool
    status_code: Optional[int]
    error: Optional[str]


@dataclass
class LoadTestResult:
    """Result of a load test scenario."""
    scenario_name: str
    total_requests: int
    successful_requests: int
    failed_requests: int
    cache_hits: int
    cache_misses: int
    cache_hit_rate: float
    avg_latency_ms: float
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    requests_per_second: float
    error_rate: float
    duration_seconds: float


async def send_query(session: aiohttp.ClientSession, query: str) -> RequestResult:
    """Send a query and return result."""
    start_time = time.time()
    
    try:
        async with session.post(
            API_URL,
            json={"query": query, "forceRefresh": False},
            timeout=aiohttp.ClientTimeout(total=30)
        ) as response:
            latency_ms = (time.time() - start_time) * 1000
            
            if response.status == 200:
                data = await response.json()
                metadata = data.get("metadata", {})
                cache_hit = metadata.get("source") == "cache"
                
                return RequestResult(
                    timestamp=start_time,
                    latency_ms=latency_ms,
                    success=True,
                    cache_hit=cache_hit,
                    status_code=200,
                    error=None,
                )
            else:
                text = await response.text()
                return RequestResult(
                    timestamp=start_time,
                    latency_ms=latency_ms,
                    success=False,
                    cache_hit=False,
                    status_code=response.status,
                    error=f"Status {response.status}: {text}",
                )
    except asyncio.TimeoutError:
        latency_ms = (time.time() - start_time) * 1000
        return RequestResult(
            timestamp=start_time,
            latency_ms=latency_ms,
            success=False,
            cache_hit=False,
            status_code=None,
            error="Timeout",
        )
    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        return RequestResult(
            timestamp=start_time,
            latency_ms=latency_ms,
            success=False,
            cache_hit=False,
            status_code=None,
            error=str(e),
        )


async def run_user_simulation(
    session: aiohttp.ClientSession,
    user_id: int,
    scenario,
    queries: List[str],
) -> List[RequestResult]:
    """Simulate a single user making requests."""
    results: List[RequestResult] = []
    request_interval = 1.0 / scenario.request_rate_per_user
    
    for i in range(scenario.requests_per_user):
        query = queries[i % len(queries)]
        result = await send_query(session, query)
        results.append(result)
        
        # Rate limiting
        if i < scenario.requests_per_user - 1:
            await asyncio.sleep(request_interval)
    
    return results


async def run_scenario(scenario, tracker) -> LoadTestResult:
    """Run a load test scenario."""
    print(f"\n{'=' * 80}")
    print(f"Scenario: {scenario.name}")
    print(f"{'=' * 80}")
    print(f"Description: {scenario.description}")
    print(f"Concurrent users: {scenario.concurrent_users}")
    print(f"Requests per user: {scenario.requests_per_user}")
    print(f"Request rate: {scenario.request_rate_per_user} req/sec/user")
    print(f"Expected cache hit rate: {scenario.expected_cache_hit_rate:.1%}")
    print()
    
    async with aiohttp.ClientSession() as session:
        # Create tasks for all users
        tasks = []
        for user_id in range(scenario.concurrent_users):
            task = run_user_simulation(session, user_id, scenario, LOAD_TEST_QUERIES)
            tasks.append(task)
        
        # Run all users concurrently
        print("Running load test...")
        start_time = time.time()
        user_results = await asyncio.gather(*tasks)
        end_time = time.time()
        
        # Flatten results
        all_results: List[RequestResult] = []
        for user_result_list in user_results:
            all_results.extend(user_result_list)
        
        duration = end_time - start_time
        
        # Calculate statistics
        successful = [r for r in all_results if r.success]
        failed = [r for r in all_results if not r.success]
        cache_hits = [r for r in successful if r.cache_hit]
        cache_misses = [r for r in successful if not r.cache_hit]
        
        latencies = [r.latency_ms for r in successful]
        latencies.sort()
        
        total_requests = len(all_results)
        successful_count = len(successful)
        failed_count = len(failed)
        cache_hits_count = len(cache_hits)
        cache_misses_count = len(cache_misses)
        
        cache_hit_rate = cache_hits_count / successful_count if successful_count > 0 else 0.0
        error_rate = failed_count / total_requests if total_requests > 0 else 0.0
        requests_per_second = total_requests / duration if duration > 0 else 0.0
        
        avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
        p50_latency = latencies[len(latencies) // 2] if latencies else 0.0
        p95_latency = latencies[int(len(latencies) * 0.95)] if latencies else 0.0
        p99_latency = latencies[int(len(latencies) * 0.99)] if latencies else 0.0
        
        result = LoadTestResult(
            scenario_name=scenario.name,
            total_requests=total_requests,
            successful_requests=successful_count,
            failed_requests=failed_count,
            cache_hits=cache_hits_count,
            cache_misses=cache_misses_count,
            cache_hit_rate=cache_hit_rate,
            avg_latency_ms=avg_latency,
            p50_latency_ms=p50_latency,
            p95_latency_ms=p95_latency,
            p99_latency_ms=p99_latency,
            requests_per_second=requests_per_second,
            error_rate=error_rate,
            duration_seconds=duration,
        )
        
        # Print results
        print(f"\nResults:")
        print(f"  Total requests: {total_requests}")
        print(f"  Successful: {successful_count} ({successful_count/total_requests*100:.1f}%)")
        print(f"  Failed: {failed_count} ({error_rate*100:.1f}%)")
        print(f"  Cache hits: {cache_hits_count} ({cache_hit_rate*100:.1f}%)")
        print(f"  Cache misses: {cache_misses_count}")
        print(f"  Requests/sec: {requests_per_second:.1f}")
        print(f"  Duration: {duration:.2f}s")
        print(f"\nLatency:")
        print(f"  Average: {avg_latency:.1f}ms")
        print(f"  P50: {p50_latency:.1f}ms")
        print(f"  P95: {p95_latency:.1f}ms")
        print(f"  P99: {p99_latency:.1f}ms")
        
        return result


async def run_all_scenarios():
    """Run all load test scenarios."""
    tracker = get_tracker(budget=BUDGET)
    
    print("=" * 80)
    print("Load Performance Testing Suite")
    print("=" * 80)
    print(f"Budget: ${BUDGET:.2f}")
    print("Using pre-populated cache - minimal API costs")
    print()
    
    # Verify API is accessible
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(API_URL, json={"query": "test"}, timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status != 200:
                    print(f"❌ API not accessible: Status {response.status}")
                    return 1
        except Exception as e:
            print(f"❌ API not accessible: {e}")
            print(f"Make sure the API is running at: {API_URL}")
            return 1
    
    print("✅ API is accessible")
    print()
    
    # Run scenarios
    scenarios = get_all_scenarios()
    results: List[LoadTestResult] = []
    
    for scenario in scenarios:
        try:
            result = await run_scenario(scenario, tracker)
            results.append(result)
            
            # Check budget
            cost_summary = tracker.get_summary()
            if cost_summary.remaining < 0.05:
                print(f"\n⚠️  Budget warning: Only ${cost_summary.remaining:.4f} remaining. Stopping.")
                break
        except Exception as e:
            print(f"\n❌ Error running scenario {scenario.name}: {e}")
            import traceback
            traceback.print_exc()
    
    # Print summary
    print()
    print("=" * 80)
    print("Final Summary")
    print("=" * 80)
    
    for result in results:
        print(f"\n{result.scenario_name}:")
        print(f"  Requests/sec: {result.requests_per_second:.1f}")
        print(f"  Cache hit rate: {result.cache_hit_rate:.1%}")
        print(f"  Error rate: {result.error_rate:.1%}")
        print(f"  P95 latency: {result.p95_latency_ms:.1f}ms")
    
    # Print cost summary
    tracker.print_summary()
    
    # Save results
    results_dir = Path("test/results/load_testing")
    results_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    results_file = results_dir / f"results_{timestamp}.json"
    with open(results_file, "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "results": [asdict(r) for r in results],
        }, f, indent=2)
    
    cost_report_file = results_dir / f"cost_report_{timestamp}.json"
    tracker.save_report(str(cost_report_file))
    
    print()
    print(f"Results saved to: {results_file}")
    print(f"Cost report saved to: {cost_report_file}")
    
    return 0


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(run_all_scenarios())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
