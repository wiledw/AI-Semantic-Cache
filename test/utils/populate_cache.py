#!/usr/bin/env python3
"""
Cache Pre-population Script

Pre-populates the cache with diverse test queries to minimize API costs during testing.
This script should be run once before running test suites to populate the cache.
"""

import asyncio
import os
import sys
import aiohttp
from typing import List, Tuple
from pathlib import Path

# Add project root to path to import app modules
# Get the project root (2 levels up from this file)
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

# Verify we can import test modules
try:
    from test.utils.cost_tracker import get_tracker
except ImportError as e:
    print(f"❌ Import error: {e}")
    print(f"   Current directory: {os.getcwd()}")
    print(f"   Project root: {project_root}")
    print(f"   Python path: {sys.path[:3]}")
    print("\n💡 Tip: Run this script from the project root directory:")
    print(f"   cd {project_root}")
    print("   python3 test/utils/populate_cache.py")
    sys.exit(1)

API_URL = os.getenv("API_URL", "http://localhost:3000/api/query")
BUDGET = float(os.getenv("POPULATE_CACHE_BUDGET", "1.50"))  # Budget for cache population


# Diverse query dataset covering all test patterns
QUERY_DATASET: List[Tuple[str, str]] = [
    # Exact duplicates (will be tested with same queries)
    ("What's the weather today?", "weather"),
    ("What's the weather today?", "weather"),  # Duplicate
    ("How do I reset my password?", "general"),
    ("How do I reset my password?", "general"),  # Duplicate
    
    # Semantically similar queries
    ("What's the weather like right now?", "weather"),
    ("How's the weather today?", "weather"),
    ("Current weather conditions", "weather"),
    ("I need to change my password", "general"),
    ("Where can I update my password?", "general"),
    ("Password reset instructions", "general"),
    
    # Time-sensitive queries
    ("What's the current Bitcoin price?", "price"),
    ("Latest news headlines", "news"),
    ("Today's weather forecast", "weather"),
    ("Current stock prices", "price"),
    ("Game score update", "score"),
    
    # Evergreen queries
    ("What is Python programming?", "tech"),
    ("How does machine learning work?", "tech"),
    ("History of computers", "tech"),
    ("What is the capital of France?", "general"),
    ("How to bake a cake?", "general"),
    
    # Varying complexity
    ("Weather?", "weather"),  # Short
    ("What's the weather like in New York City today?", "weather"),  # Medium
    ("Can you tell me what the current weather conditions are in New York City, including temperature, humidity, wind speed, and any precipitation expected?", "weather"),  # Long
    
    # Different languages
    ("¿Cuál es el clima?", "weather"),  # Spanish
    ("Quel est le temps?", "weather"),  # French
    ("天气怎么样？", "weather"),  # Chinese
    ("天気はどうですか？", "weather"),  # Japanese
    
    # Special characters
    ("What's the weather in São Paulo?", "weather"),  # Unicode
    ("Weather 🌤️", "weather"),  # Emoji
    ("What's the weather?!", "weather"),  # Special punctuation
    
    # Tech queries
    ("How to write Python code?", "tech"),
    ("What is an API?", "tech"),
    ("How to debug code?", "tech"),
    ("REST API tutorial", "tech"),
    
    # News queries
    ("What's the latest news?", "news"),
    ("Breaking news headlines", "news"),
    ("Today's news", "news"),
    
    # Price queries
    ("What's the price of gold?", "price"),
    ("Bitcoin price today", "price"),
    ("Stock market prices", "price"),
    
    # Score queries
    ("Latest game scores", "score"),
    ("Football match results", "score"),
    ("Basketball scores today", "score"),
    
    # Unrelated queries (for testing no false positives)
    ("How to bake a chocolate cake?", "general"),
    ("Best restaurants in NYC", "general"),
    ("Travel tips for Europe", "general"),
    ("Movie recommendations", "general"),
]


async def send_query(session: aiohttp.ClientSession, query: str, force_refresh: bool = False) -> dict:
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


async def populate_cache():
    """Populate cache with test queries."""
    tracker = get_tracker(budget=BUDGET)
    
    print("=" * 80)
    print("Cache Pre-population Script")
    print("=" * 80)
    print(f"Budget: ${BUDGET:.2f}")
    print(f"Queries to populate: {len(QUERY_DATASET)}")
    print()
    
    async with aiohttp.ClientSession() as session:
        success_count = 0
        error_count = 0
        
        # First, verify API is accessible
        print("Checking API connectivity...")
        test_result = await send_query(session, "test", force_refresh=True)
        if "error" in test_result:
            print(f"❌ API not accessible: {test_result['error']}")
            print("Make sure the API is running at:", API_URL)
            return
        print("✅ API is accessible")
        print()
        
        print("Populating cache...")
        print("-" * 80)
        
        for i, (query, topic) in enumerate(QUERY_DATASET, 1):
            print(f"[{i}/{len(QUERY_DATASET)}] [{topic:8s}] {query[:60]}...", end=" ")
            
            result = await send_query(session, query, force_refresh=True)
            
            if "error" in result:
                print(f"❌ Error: {result['error']}")
                error_count += 1
            else:
                source = result.get("metadata", {}).get("source", "unknown")
                similarity = result.get("metadata", {}).get("similarity")
                
                if source == "cache":
                    similarity_str = f"{similarity:.2f}" if similarity is not None else "N/A"
                    print(f"✅ Cache hit (similarity: {similarity_str})")
                else:
                    print(f"✅ {source}")
                    success_count += 1
                
                # Small delay to avoid rate limiting
                await asyncio.sleep(0.2)
            
            # Check budget
            summary = tracker.get_summary()
            if summary.remaining < 0.10:
                print(f"\n⚠️  Budget warning: Only ${summary.remaining:.4f} remaining. Stopping.")
                break
        
        print()
        print("-" * 80)
        print(f"Completed: {success_count} successful, {error_count} errors")
        print()
        
        # Print cost summary
        tracker.print_summary()
        
        # Save report
        report_path = "test/results/cache_population_cost.json"
        tracker.save_report(report_path)
        
        print()
        print("✅ Cache population complete!")
        print(f"   Cost report saved to: {report_path}")
        print()
        print("You can now run test suites with minimal API costs.")
        print("Most tests will use cached data (95%+ cache hit rate).")


if __name__ == "__main__":
    try:
        asyncio.run(populate_cache())
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
