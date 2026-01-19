#!/usr/bin/env python3
"""
Query Pattern Testing Suite

Tests the semantic cache against diverse query patterns including:
- Exact duplicate queries
- Semantically similar queries
- Completely unrelated queries
- Time-sensitive vs evergreen queries
- Varying complexity and length
- Different languages
- Special characters
"""

import asyncio
import os
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import List, Dict, Optional

import aiohttp
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from test.queryPatterns.query_datasets import (
    get_queries_by_category,
    get_all_queries,
    QueryPattern,
)
from test.utils.cost_tracker import get_tracker

API_URL = os.getenv("API_URL", "http://localhost:3000/api/query")
STATS_URL = os.getenv("STATS_URL", "http://localhost:3000/api/stats")
BUDGET = float(os.getenv("QUERY_PATTERN_BUDGET", "1.50"))


@dataclass
class TestResult:
    """Result of a single query test."""
    query: str
    category: str
    expected_cache_hit: bool
    actual_cache_hit: bool
    similarity: Optional[float]
    latency_ms: float
    source: str
    passed: bool
    error: Optional[str] = None


@dataclass
class CategorySummary:
    """Summary for a query category."""
    category: str
    total: int
    passed: int
    failed: int
    cache_hits: int
    cache_misses: int
    hit_rate: float
    avg_latency_ms: float
    avg_similarity: Optional[float]


async def send_query(
    session: aiohttp.ClientSession,
    query: str,
    force_refresh: bool = False,
) -> dict:
    """Send a query to the API."""
    payload = {"query": query, "forceRefresh": force_refresh}
    
    try:
        async with session.post(API_URL, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as response:
            if response.status == 200:
                return await response.json()
            else:
                text = await response.text()
                return {"error": f"Status {response.status}: {text}"}
    except Exception as e:
        return {"error": str(e)}


async def get_stats(session: aiohttp.ClientSession) -> dict:
    """Get stats from the API."""
    try:
        async with session.get(STATS_URL, timeout=aiohttp.ClientTimeout(total=10)) as response:
            if response.status == 200:
                return await response.json()
            else:
                return {"error": f"Status {response.status}"}
    except Exception as e:
        return {"error": str(e)}


async def test_category(
    session: aiohttp.ClientSession,
    category: str,
    queries: List[QueryPattern],
    tracker,
) -> tuple[List[TestResult], CategorySummary]:
    """Test a category of queries."""
    print(f"\n{'=' * 80}")
    print(f"Testing Category: {category}")
    print(f"{'=' * 80}")
    print(f"Queries: {len(queries)}")
    print()
    
    results: List[TestResult] = []
    
    for i, pattern in enumerate(queries, 1):
        print(f"  [{i}/{len(queries)}] {pattern.query[:70]}...", end=" ")
        
        start_time = time.time()
        # Use force_refresh=False to test semantic similarity matching
        # Note: If queries were cached from previous runs, they may match exactly (similarity 1.0)
        # For unrelated queries, ensure cache is cleared before running tests
        result = await send_query(session, pattern.query, force_refresh=False)
        latency_ms = (time.time() - start_time) * 1000
        
        if "error" in result:
            print(f"❌ Error: {result['error']}")
            results.append(TestResult(
                query=pattern.query,
                category=category,
                expected_cache_hit=pattern.expected_cache_hit,
                actual_cache_hit=False,
                similarity=None,
                latency_ms=latency_ms,
                source="error",
                passed=False,
                error=result["error"],
            ))
        else:
            metadata = result.get("metadata", {})
            source = metadata.get("source", "unknown")
            similarity = metadata.get("similarity")
            actual_cache_hit = source == "cache"
            
            # Detect if unrelated query matched exactly (likely cached from previous run)
            is_exact_match_on_unrelated = (
                category == "Completely Unrelated Queries" 
                and not pattern.expected_cache_hit 
                and similarity == 1.0
            )
            
            # Validate result
            passed = True
            if pattern.expected_cache_hit != actual_cache_hit:
                passed = False
            
            if pattern.expected_similarity_min and similarity:
                if similarity < pattern.expected_similarity_min:
                    passed = False
            
            if pattern.expected_similarity_max and similarity:
                if similarity > pattern.expected_similarity_max:
                    passed = False
            
            status = "✅" if passed else "❌"
            similarity_str = f"{similarity:.2f}" if similarity is not None else "N/A"
            
            # Add warning for exact matches on unrelated queries
            warning = ""
            if is_exact_match_on_unrelated:
                warning = " ⚠️ (exact match - likely cached from previous run, clear cache and retest)"
            
            print(f"{status} {source} (similarity: {similarity_str}, {latency_ms:.0f}ms){warning}")
            
            results.append(TestResult(
                query=pattern.query,
                category=category,
                expected_cache_hit=pattern.expected_cache_hit,
                actual_cache_hit=actual_cache_hit,
                similarity=similarity,
                latency_ms=latency_ms,
                source=source,
                passed=passed,
            ))
        
        # Small delay to avoid overwhelming the API
        await asyncio.sleep(0.1)
    
    # Calculate summary
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    cache_hits = sum(1 for r in results if r.actual_cache_hit)
    cache_misses = total - cache_hits
    hit_rate = (cache_hits / total) if total > 0 else 0.0
    avg_latency = sum(r.latency_ms for r in results) / total if total > 0 else 0.0
    
    similarities = [r.similarity for r in results if r.similarity is not None]
    avg_similarity = sum(similarities) / len(similarities) if similarities else None
    
    summary = CategorySummary(
        category=category,
        total=total,
        passed=passed,
        failed=failed,
        cache_hits=cache_hits,
        cache_misses=cache_misses,
        hit_rate=hit_rate,
        avg_latency_ms=avg_latency,
        avg_similarity=avg_similarity,
    )
    
    print()
    print(f"Summary: {passed}/{total} passed, {cache_hits}/{total} cache hits ({hit_rate:.1%}), avg latency: {avg_latency:.0f}ms")
    
    return results, summary


async def run_all_tests():
    """Run all query pattern tests."""
    tracker = get_tracker(budget=BUDGET)
    
    print("=" * 80)
    print("Query Pattern Testing Suite")
    print("=" * 80)
    print(f"Budget: ${BUDGET:.2f}")
    print()
    
    async with aiohttp.ClientSession() as session:
        # Verify API is accessible
        print("Checking API connectivity...")
        test_result = await send_query(session, "test", force_refresh=False)
        if "error" in test_result:
            print(f"❌ API not accessible: {test_result['error']}")
            print("Make sure the API is running at:", API_URL)
            return
        print("✅ API is accessible")
        print()
        print("⚠️  Note: For accurate 'unrelated queries' test results, ensure cache is cleared.")
        print("   If unrelated queries show similarity 1.00, they were cached from a previous run.")
        print("   Run './test/reset_and_retest.sh' to clear cache before testing.")
        print()
        
        # Test categories
        categories = [
            ("exact_duplicate", "Exact Duplicate Queries"),
            ("semantic_similar", "Semantically Similar Queries"),
            ("unrelated", "Completely Unrelated Queries"),
            ("time_sensitive", "Time-Sensitive Queries"),
            ("evergreen", "Evergreen Queries"),
            ("varying_complexity", "Varying Complexity and Length"),
            ("multilingual", "Different Languages"),
            ("special_characters", "Special Characters"),
        ]
        
        all_results: List[TestResult] = []
        all_summaries: List[CategorySummary] = []
        
        for category_key, category_name in categories:
            queries = get_queries_by_category(category_key)
            
            if not queries:
                print(f"Skipping {category_name} - no queries")
                continue
            
            results, summary = await test_category(
                session,
                category_name,
                queries,
                tracker,
            )
            
            all_results.extend(results)
            all_summaries.append(summary)
            
            # Check budget
            cost_summary = tracker.get_summary()
            if cost_summary.remaining < 0.10:
                print(f"\n⚠️  Budget warning: Only ${cost_summary.remaining:.4f} remaining. Stopping.")
                break
        
        # Print final summary
        print()
        print("=" * 80)
        print("Final Summary")
        print("=" * 80)
        
        total_queries = len(all_results)
        total_passed = sum(1 for r in all_results if r.passed)
        total_failed = total_queries - total_passed
        total_cache_hits = sum(1 for r in all_results if r.actual_cache_hit)
        overall_hit_rate = (total_cache_hits / total_queries) if total_queries > 0 else 0.0
        
        print(f"Total Queries: {total_queries}")
        print(f"Passed: {total_passed} ({total_passed/total_queries*100:.1f}%)")
        print(f"Failed: {total_failed}")
        print(f"Cache Hits: {total_cache_hits} ({overall_hit_rate:.1%})")
        print()
        
        print("By Category:")
        for summary in all_summaries:
            print(f"  {summary.category:30s}: {summary.passed:3d}/{summary.total:3d} passed, "
                  f"{summary.cache_hits:3d}/{summary.total:3d} hits ({summary.hit_rate:.1%})")
        
        print()
        
        # Print cost summary
        tracker.print_summary()
        
        # Save results
        results_dir = Path("test/results/query_patterns")
        results_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save detailed results
        results_file = results_dir / f"results_{timestamp}.json"
        with open(results_file, "w") as f:
            import json
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "results": [asdict(r) for r in all_results],
                "summaries": [asdict(s) for s in all_summaries],
            }, f, indent=2)
        
        # Save cost report
        cost_report_file = results_dir / f"cost_report_{timestamp}.json"
        tracker.save_report(str(cost_report_file))
        
        print()
        print(f"Results saved to: {results_file}")
        print(f"Cost report saved to: {cost_report_file}")
        print()
        
        # Exit code based on results
        if total_failed > 0:
            print(f"⚠️  {total_failed} tests failed")
            return 1
        else:
            print("✅ All tests passed!")
            return 0


if __name__ == "__main__":
    from pathlib import Path
    
    try:
        exit_code = asyncio.run(run_all_tests())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
