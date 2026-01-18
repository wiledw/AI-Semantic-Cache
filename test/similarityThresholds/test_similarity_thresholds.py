#!/usr/bin/env python3
"""
Similarity Threshold Testing Script

Tests different similarity thresholds (0.75, 0.80, 0.85, 0.90) to evaluate
cache hit rates, response acceptability, and cost savings.
"""

import os
import json
import time
import requests
import argparse
import subprocess
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict

# Visualization imports
try:
    import matplotlib.pyplot as plt
    import seaborn as sns
    import pandas as pd
    HAS_VISUALIZATION = True
except ImportError:
    HAS_VISUALIZATION = False

API_URL = os.getenv("API_URL", "http://localhost:3000/api")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Available embedding models
AVAILABLE_MODELS = [
    "text-embedding-3-small",
    "text-embedding-3-large",
    "text-embedding-ada-002",
]

# Default embedding model
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"

# Similarity thresholds to test
THRESHOLDS = [0.75, 0.80, 0.85, 0.90]

# LLM cost per call (gpt-4o-mini estimate)
LLM_COST_PER_CALL = 0.03  # $0.03 per 1K tokens, ~1K tokens per response

# Embedding model pricing (per 1K tokens)
EMBEDDING_PRICING = {
    "text-embedding-3-small": 0.00002,
    "text-embedding-3-large": 0.00013,
    "text-embedding-ada-002": 0.0001,
}

# Test dataset - Redesigned with more varied wording to produce diverse similarity scores
# Base queries use specific, concrete language
BASE_QUERIES = {
    "password_management": [
        "How do I change my password?",
        "I need to reset my login credentials.",
        "Where can I update my password?",
    ],
    "billing_management": [
        "How do I change my billing address?",
        "I want to update my payment method.",
        "Where is the billing settings page?",
    ],
    "account_settings": [
        "How do I update my profile information?",
        "I need to change my email address.",
        "Where can I edit my account details?",
    ],
    "product_features": [
        "What are the new features in the v2.0 update?",
        "Tell me about the latest product updates.",
        "What's new in version 2.0?",
    ],
}

# Test queries designed with progressively different wording to produce varied similarity scores:
# - Group A: High similarity (0.85-0.95) - semantically equivalent, different wording
# - Group B: Medium similarity (0.75-0.85) - related but different intent/scope
# - Group C: Low similarity (0.60-0.75) - completely different topics/domains
TEST_QUERIES = {
    "Group A - High Similarity (Should Hit at 0.75+)": [
        # Semantically equivalent to password_management base queries - different wording only
        ("I want to update my password", "password_management", "should_hit"),
        ("Reset my login credentials please", "password_management", "should_hit"),
        ("Where is the password change option?", "password_management", "should_hit"),
        # Edge cases - slightly different phrasing but same intent
        ("Can you help me change my password?", "password_management", "edge_case"),
        ("I'd like to modify my login password", "password_management", "edge_case"),
        ("How can I reset my account password?", "password_management", "edge_case"),
    ],
    "Group B - Medium Similarity (Should Hit at 0.75, Miss at 0.85+)": [
        # Related to account security but broader scope - should have medium similarity (0.75-0.85)
        ("I need help with account security settings", "password_management", "should_miss"),  # Broader scope than just password
        ("What steps are involved in updating login credentials?", "password_management", "should_miss"),  # More formal, process-oriented
        ("Can I modify my authentication information?", "password_management", "should_miss"),  # Different terminology (auth vs password)
        ("Where would I find options to update my secret code?", "password_management", "should_miss"),  # Different wording (secret code vs password)
    ],
    "Group C - Low Similarity (Should Miss at All Thresholds)": [
        # Completely different topics/domains - should have low similarity (0.50-0.75)
        # These should NOT match password_management base queries
        ("What are the latest product features and improvements in version 3.0?", "product_features", "should_miss"),  # Product features - different domain
        ("Tell me about recent software updates and new releases for the application", "product_features", "should_miss"),  # Software updates - different domain
        ("How do I update my credit card information for monthly billing?", "billing_management", "should_miss"),  # Billing/payment - different domain
        ("I need to change my shipping address for package deliveries", "billing_management", "should_miss"),  # Shipping - completely different
        ("What is the weather forecast for tomorrow?", "unrelated", "should_miss"),  # Weather - completely unrelated
        ("How do I prepare a delicious pasta dish?", "unrelated", "should_miss"),  # Cooking - completely unrelated
    ],
}


@dataclass
class TestResult:
    """Result for a single query"""
    threshold: float
    query: str
    group: str
    expected_behavior: str
    cache_hit: bool
    similarity_score: Optional[float]
    response: str
    source: str
    acceptable: Optional[bool] = None


@dataclass
class ThresholdSummary:
    """Summary for a single threshold"""
    threshold: float
    embedding_model: str
    total_queries: int
    cache_hits: int
    cache_misses: int
    hit_rate: float
    acceptable_responses: int
    acceptability_rate: float
    llm_calls: int
    estimated_cost: float
    estimated_savings: float
    avg_similarity_on_hit: float
    min_similarity_on_hit: float
    max_similarity_on_hit: float


def get_stats_from_api() -> dict:
    """Get current stats from API"""
    try:
        response = requests.get(f"{API_URL}/stats", timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"  Warning: Could not get stats from API: {e}")
        return {
            "requests": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "llm_calls": 0,
            "estimated_llm_cost": 0.0,
            "estimated_cache_savings": 0.0,
        }


def clear_cache() -> None:
    """
    Clear cache using Redis directly - ensures complete isolation between threshold tests.
    
    IMPORTANT: This clears both:
    1. Response cache (cached query-response pairs): cache:{hash(query)}
    2. Embedding cache (cached embeddings): embed:{model_name}:{hash(normalized_query)}
    3. LLM call counter: llm_call_count
    4. All stats: stat:requests, stat:cache_hits, stat:cache_misses, stat:llm_fallbacks
    
    Uses multiple methods:
    1. Docker command (docker compose exec redis redis-cli FLUSHDB) - most reliable for Docker setup
    2. Redis Python library connection - fallback method
    """
    cleared = False
    
    # Method 1: Use Docker command (most reliable for Docker Compose setup)
    # This directly accesses the Redis instance that the API uses
    try:
        result = subprocess.run(
            ["docker", "compose", "exec", "-T", "redis", "redis-cli", "FLUSHDB"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),  # Go to project root
        )
        if result.returncode == 0:
            print(f"  ✓ Cleared Redis via Docker command (FLUSHDB)")
            cleared = True
        else:
            # Docker command failed, try other methods
            pass
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError) as e:
        # Docker not available or command failed, try other methods
        pass
    
    # Method 2: Use Redis Python library (fallback)
    if not cleared:
        try:
            import redis
            
            # Try both Redis URLs - API might use Docker service name, test uses localhost
            # Both should point to the same Redis instance, but accessed differently
            redis_urls_to_try = [
                REDIS_URL,  # Test's Redis URL (usually localhost)
                "redis://localhost:6379/0",  # Explicit localhost (same as REDIS_URL usually)
            ]
            
            for redis_url in redis_urls_to_try:
                try:
                    redis_client = redis.Redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=2)
                    redis_client.ping()
                    
                    # Use FLUSHDB to completely clear the database
                    # This clears: cache entries, embedding cache, AND llm_call_count, AND all stats
                    redis_client.flushdb()
                    
                    # Explicitly reset LLM call counter and stats (in case FLUSHDB didn't work)
                    redis_client.delete("llm_call_count")
                    redis_client.delete("stat:requests")
                    redis_client.delete("stat:cache_hits")
                    redis_client.delete("stat:cache_misses")
                    redis_client.delete("stat:llm_fallbacks")
                    
                    print(f"  ✓ Cleared Redis at {redis_url} (including LLM call counter and stats)")
                    cleared = True
                    break
                except Exception as e:
                    # This URL didn't work, try next one
                    continue
            
            if not cleared:
                print(f"  ⚠️  Warning: Could not connect to Redis at any URL")
                print(f"     Tried: {redis_urls_to_try}")
                print(f"     Make sure Redis is running and accessible.")
        except ImportError:
            print("  ⚠️  Redis module not available. Cache may not be fully cleared.")
            print("     Install with: pip install redis")
            print("     Test will use delta calculations (final - initial) which should still be accurate.")
    
    # Wait longer to ensure API sees the cleared state
    time.sleep(1.0)  # Increased delay
    
    # Verify by checking stats via API
    api_stats = get_stats_from_api()
    
    if api_stats.get("cache_hits", 0) > 0 or api_stats.get("llm_calls", 0) > 0:
        print(f"  ⚠️  Warning: API still shows stats (hits={api_stats.get('cache_hits', 0)}, "
              f"llm_calls={api_stats.get('llm_calls', 0)})")
        print(f"     This may indicate:")
        print(f"     1. API is using a different Redis instance/database")
        print(f"     2. API has cached stats (unlikely)")
        print(f"     3. Timing issue - stats were read before clearing")
        print(f"     Test will use delta calculations (final - initial) which should still be accurate.")
        print(f"     Consider manually resetting: docker compose exec redis redis-cli FLUSHDB")
    else:
        print(f"  ✓ Verified: API stats cleared (hits=0, llm_calls=0)")


def run_query(query: str, threshold: float, embedding_model: str, force_refresh: bool = False) -> dict:
    """Run a query with specific threshold and embedding model"""
    response = requests.post(
        f"{API_URL}/query",
        json={
            "query": query,
            "forceRefresh": force_refresh,
            "similarityThreshold": threshold,
            "embeddingModel": embedding_model,
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def test_threshold(threshold: float, embedding_model: str) -> tuple[ThresholdSummary, List[TestResult]]:
    """Test a specific similarity threshold with a specific embedding model"""
    print(f"\n{'='*60}")
    print(f"Testing threshold: {threshold} | Embedding model: {embedding_model}")
    print(f"{'='*60}")
    
    # CRITICAL: Clear cache before each threshold test for isolation
    print("\nClearing cache for test isolation...")
    clear_cache()
    
    # Wait a moment to ensure cache is cleared
    time.sleep(0.5)
    
    # Get initial stats after clearing (with a small delay to ensure API sees cleared state)
    time.sleep(0.3)
    initial_stats = get_stats_from_api()
    
    # Verify cache is actually cleared
    if initial_stats.get("cache_hits", 0) > 0 or initial_stats.get("llm_calls", 0) > 0:
        print(f"  ⚠️  Warning: Stats not fully cleared. Hits: {initial_stats.get('cache_hits', 0)}, "
              f"LLM calls: {initial_stats.get('llm_calls', 0)}")
        print(f"     API may be using different Redis URL than test script.")
        print(f"     Test script uses: {REDIS_URL}")
        print(f"     Consider manually clearing Redis or checking API's REDIS_URL.")
        print(f"     Test will continue but results may be affected by previous state.")
    
    results: List[TestResult] = []
    
    # Step 1: Populate cache with base queries
    print("\nStep 1: Populating cache...")
    base_queries_list = []
    for category, queries in BASE_QUERIES.items():
        for query in queries:
            base_queries_list.append((query, category))
    
    for query, category in base_queries_list:
        try:
            run_query(query, threshold, embedding_model, force_refresh=False)
            time.sleep(0.2)
        except Exception as e:
            print(f"    Error: {e}")
            continue
    
    print(f"  ✓ Cached {len(base_queries_list)} queries")
    
    # Step 2: Test queries
    print("\nStep 2: Testing queries...")
    test_queries_list = []
    for group_name, queries in TEST_QUERIES.items():
        group_label = group_name.split(" - ")[0].split()[-1]
        for query_tuple in queries:
            query, expected_category, expected_behavior = query_tuple
            test_queries_list.append((query, group_label, expected_category, expected_behavior))
    
    for query, group, expected_category, expected_behavior in test_queries_list:
        try:
            result = run_query(query, threshold, embedding_model, force_refresh=False)
            
            similarity = result["metadata"].get("similarity")
            cache_hit = result["metadata"]["source"] == "cache"
            source = result["metadata"]["source"]
            
            # Detect fallback responses (indicates LLM call limit reached)
            if source == "fallback":
                print(f"  ⚠️  [{group}] FALLBACK (LLM call limit likely reached)")
            
            test_result = TestResult(
                threshold=threshold,
                query=query,
                group=group,
                expected_behavior=expected_behavior,
                cache_hit=cache_hit,
                similarity_score=similarity,
                response=result["response"][:100] + "..." if len(result["response"]) > 100 else result["response"],
                source=source,
            )
            results.append(test_result)
            
            if cache_hit:
                sim_str = f"{similarity:.3f}" if similarity else "N/A"
                print(f"  [{group}] HIT (sim: {sim_str})")
            elif source == "fallback":
                # Already printed warning above
                pass
            else:
                print(f"  [{group}] MISS")
            
            time.sleep(0.2)
        except Exception as e:
            print(f"    Error: {e}")
            continue
    
    # Calculate statistics
    final_stats = get_stats_from_api()
    llm_calls_delta = final_stats["llm_calls"] - initial_stats["llm_calls"]
    cache_hits_delta = final_stats["cache_hits"] - initial_stats["cache_hits"]
    
    # Check for fallback responses (indicates LLM call limit issue)
    fallback_count = sum(1 for r in results if r.source == "fallback")
    if fallback_count > 0:
        print(f"\n  ⚠️  WARNING: {fallback_count}/{len(results)} queries returned fallback responses")
        print(f"     This indicates the LLM call limit ({final_stats.get('llm_calls', 'unknown')}) was reached.")
        print(f"     Results for this test may be inaccurate. Consider increasing MAX_LLM_CALLS.")
    
    test_cache_hits = sum(1 for r in results if r.cache_hit)
    test_total = len(results)
    hit_rate = test_cache_hits / test_total if test_total > 0 else 0.0
    
    similarities_on_hit = [r.similarity_score for r in results if r.cache_hit and r.similarity_score is not None]
    avg_similarity = sum(similarities_on_hit) / len(similarities_on_hit) if similarities_on_hit else 0.0
    min_similarity = min(similarities_on_hit) if similarities_on_hit else 0.0
    max_similarity = max(similarities_on_hit) if similarities_on_hit else 0.0
    
    # Acceptability evaluation
    acceptable_count = 0
    for result in results:
        if result.cache_hit:
            if result.group == "A":
                result.acceptable = True
                acceptable_count += 1
            elif result.group in ["B", "C"]:
                result.acceptable = False
        else:
            result.acceptable = True
            acceptable_count += 1
    
    acceptability_rate = acceptable_count / test_total if test_total > 0 else 0.0
    
    estimated_cost = llm_calls_delta * LLM_COST_PER_CALL
    estimated_savings = cache_hits_delta * LLM_COST_PER_CALL
    
    summary = ThresholdSummary(
        threshold=threshold,
        embedding_model=embedding_model,
        total_queries=test_total,
        cache_hits=test_cache_hits,
        cache_misses=test_total - test_cache_hits,
        hit_rate=hit_rate,
        acceptable_responses=acceptable_count,
        acceptability_rate=acceptability_rate,
        llm_calls=llm_calls_delta,
        estimated_cost=estimated_cost,
        estimated_savings=estimated_savings,
        avg_similarity_on_hit=avg_similarity,
        min_similarity_on_hit=min_similarity,
        max_similarity_on_hit=max_similarity,
    )
    
    return summary, results


def print_summary_table(summaries: List[ThresholdSummary]):
    """Print summary table grouped by model"""
    print("\n" + "="*120)
    print("SUMMARY TABLE - Grouped by Model")
    print("="*120)
    
    # Group summaries by model
    models = sorted(set(s.embedding_model for s in summaries))
    
    for model in models:
        model_summaries = [s for s in summaries if s.embedding_model == model]
        model_short = model.replace("text-embedding-", "").replace("-", "_")
        print(f"\n{model_short.upper()}:")
        print(f"{'Threshold':<12} {'Hit Rate':<12} {'Acceptability':<15} {'LLM Calls':<12} {'Cost':<12} {'Savings':<12} {'Avg Sim':<10}")
        print("-" * 100)
        
        for summary in sorted(model_summaries, key=lambda x: x.threshold):
            avg_sim_str = f"{summary.avg_similarity_on_hit:.3f}" if summary.avg_similarity_on_hit > 0 else "N/A"
            print(f"{summary.threshold:<12.2f} {summary.hit_rate*100:<11.1f}% "
                  f"{summary.acceptability_rate*100:<14.1f}% {summary.llm_calls:<12} "
                  f"${summary.estimated_cost:<11.6f} ${summary.estimated_savings:<11.6f} {avg_sim_str:<10}")
    
    print("\n" + "="*120)
    
    # Print similarity score ranges for debugging
    print("\nSimilarity Score Ranges (for cache hits):")
    for model in models:
        model_summaries = [s for s in summaries if s.embedding_model == model]
        print(f"\n  {model}:")
        for summary in sorted(model_summaries, key=lambda x: x.threshold):
            if summary.min_similarity_on_hit > 0:
                print(f"    Threshold {summary.threshold:.2f}: "
                      f"Min={summary.min_similarity_on_hit:.3f}, "
                      f"Max={summary.max_similarity_on_hit:.3f}, "
                      f"Avg={summary.avg_similarity_on_hit:.3f}")


def visualize_results(summaries: List[ThresholdSummary]) -> None:
    """Create visualization comparing all models"""
    if not HAS_VISUALIZATION:
        print("\n⚠️  Visualization libraries not available. Install with: pip install matplotlib seaborn pandas")
        return
    
    # Create output directory
    output_dir = "threshold_test_output"
    os.makedirs(output_dir, exist_ok=True)
    
    # Convert to DataFrame for easier plotting
    df = pd.DataFrame([asdict(s) for s in summaries])
    
    # Create figure with subplots
    fig = plt.figure(figsize=(20, 12))
    gs = fig.add_gridspec(3, 3, hspace=0.3, wspace=0.3)
    
    # Model name mapping for display
    model_names = {
        "text-embedding-3-small": "3-small",
        "text-embedding-3-large": "3-large",
        "text-embedding-ada-002": "ada-002",
    }
    df['model_short'] = df['embedding_model'].map(model_names)
    
    # 1. Hit Rate by Threshold (all models)
    ax1 = fig.add_subplot(gs[0, 0])
    for model in df['model_short'].unique():
        model_data = df[df['model_short'] == model].sort_values('threshold')
        ax1.plot(model_data['threshold'], model_data['hit_rate'] * 100, marker='o', label=model, linewidth=2)
    ax1.set_xlabel('Similarity Threshold')
    ax1.set_ylabel('Hit Rate (%)')
    ax1.set_title('Cache Hit Rate by Threshold', fontweight='bold')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    ax1.set_xticks(THRESHOLDS)
    
    # 2. Acceptability Rate by Threshold (all models)
    ax2 = fig.add_subplot(gs[0, 1])
    for model in df['model_short'].unique():
        model_data = df[df['model_short'] == model].sort_values('threshold')
        ax2.plot(model_data['threshold'], model_data['acceptability_rate'] * 100, marker='s', label=model, linewidth=2)
    ax2.set_xlabel('Similarity Threshold')
    ax2.set_ylabel('Acceptability Rate (%)')
    ax2.set_title('Response Acceptability by Threshold', fontweight='bold')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    ax2.set_xticks(THRESHOLDS)
    
    # 3. LLM Calls by Threshold (all models)
    ax3 = fig.add_subplot(gs[0, 2])
    for model in df['model_short'].unique():
        model_data = df[df['model_short'] == model].sort_values('threshold')
        ax3.plot(model_data['threshold'], model_data['llm_calls'], marker='^', label=model, linewidth=2)
    ax3.set_xlabel('Similarity Threshold')
    ax3.set_ylabel('LLM Calls')
    ax3.set_title('LLM Calls by Threshold', fontweight='bold')
    ax3.legend()
    ax3.grid(True, alpha=0.3)
    ax3.set_xticks(THRESHOLDS)
    
    # 4. Total Cost Comparison (bar chart)
    ax4 = fig.add_subplot(gs[1, 0])
    total_costs = df.groupby('model_short')['estimated_cost'].sum().sort_values(ascending=False)
    bars = ax4.bar(total_costs.index, total_costs.values, color=['#3498db', '#2ecc71', '#e74c3c'])
    ax4.set_xlabel('Model')
    ax4.set_ylabel('Total Cost ($)')
    ax4.set_title('Total LLM Cost Across All Thresholds', fontweight='bold')
    ax4.grid(True, alpha=0.3, axis='y')
    for bar in bars:
        height = bar.get_height()
        ax4.text(bar.get_x() + bar.get_width()/2., height,
                f'${height:.4f}', ha='center', va='bottom')
    
    # 5. Total Savings Comparison (bar chart)
    ax5 = fig.add_subplot(gs[1, 1])
    total_savings = df.groupby('model_short')['estimated_savings'].sum().sort_values(ascending=False)
    bars = ax5.bar(total_savings.index, total_savings.values, color=['#3498db', '#2ecc71', '#e74c3c'])
    ax5.set_xlabel('Model')
    ax5.set_ylabel('Total Savings ($)')
    ax5.set_title('Total Cache Savings Across All Thresholds', fontweight='bold')
    ax5.grid(True, alpha=0.3, axis='y')
    for bar in bars:
        height = bar.get_height()
        ax5.text(bar.get_x() + bar.get_width()/2., height,
                f'${height:.4f}', ha='center', va='bottom')
    
    # 6. Average Similarity Score (on cache hits)
    ax6 = fig.add_subplot(gs[1, 2])
    for model in df['model_short'].unique():
        model_data = df[df['model_short'] == model].sort_values('threshold')
        model_data_filtered = model_data[model_data['avg_similarity_on_hit'] > 0]
        if len(model_data_filtered) > 0:
            ax6.plot(model_data_filtered['threshold'], model_data_filtered['avg_similarity_on_hit'], 
                    marker='o', label=model, linewidth=2)
    ax6.set_xlabel('Similarity Threshold')
    ax6.set_ylabel('Avg Similarity Score')
    ax6.set_title('Average Similarity Score (Cache Hits)', fontweight='bold')
    ax6.legend()
    ax6.grid(True, alpha=0.3)
    ax6.set_xticks(THRESHOLDS)
    ax6.set_ylim([0.7, 1.0])
    
    # 7. Hit Rate Heatmap (threshold x model)
    ax7 = fig.add_subplot(gs[2, 0])
    pivot_hit = df.pivot_table(values='hit_rate', index='threshold', columns='model_short', aggfunc='mean')
    sns.heatmap(pivot_hit * 100, annot=True, fmt='.1f', cmap='YlOrRd', ax=ax7, cbar_kws={'label': 'Hit Rate (%)'})
    ax7.set_title('Hit Rate Heatmap', fontweight='bold')
    ax7.set_xlabel('Model')
    ax7.set_ylabel('Threshold')
    
    # 8. Acceptability Heatmap (threshold x model)
    ax8 = fig.add_subplot(gs[2, 1])
    pivot_acc = df.pivot_table(values='acceptability_rate', index='threshold', columns='model_short', aggfunc='mean')
    sns.heatmap(pivot_acc * 100, annot=True, fmt='.1f', cmap='YlGnBu', ax=ax8, cbar_kws={'label': 'Acceptability (%)'})
    ax8.set_title('Acceptability Rate Heatmap', fontweight='bold')
    ax8.set_xlabel('Model')
    ax8.set_ylabel('Threshold')
    
    # 9. Model Comparison Summary (text summary)
    ax9 = fig.add_subplot(gs[2, 2])
    ax9.axis('off')
    
    # Calculate summary stats
    summary_text = "MODEL COMPARISON SUMMARY\n" + "="*40 + "\n\n"
    
    for model in df['model_short'].unique():
        model_data = df[df['model_short'] == model]
        avg_hit_rate = model_data['hit_rate'].mean() * 100
        avg_acceptability = model_data['acceptability_rate'].mean() * 100
        total_llm_calls = model_data['llm_calls'].sum()
        total_cost = model_data['estimated_cost'].sum()
        total_savings = model_data['estimated_savings'].sum()
        
        summary_text += f"{model}:\n"
        summary_text += f"  Avg Hit Rate: {avg_hit_rate:.1f}%\n"
        summary_text += f"  Avg Acceptability: {avg_acceptability:.1f}%\n"
        summary_text += f"  Total LLM Calls: {total_llm_calls}\n"
        summary_text += f"  Total Cost: ${total_cost:.4f}\n"
        summary_text += f"  Total Savings: ${total_savings:.4f}\n\n"
    
    ax9.text(0.1, 0.5, summary_text, fontsize=10, family='monospace', verticalalignment='center',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
    
    plt.suptitle('Embedding Model Comparison: Similarity Threshold Analysis', fontsize=16, fontweight='bold', y=0.995)
    
    # Save figure
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(output_dir, f"model_comparison_{timestamp}.png")
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    print(f"\n✅ Visualization saved to: {output_file}")
    
    plt.close()


def main():
    """Main test execution"""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description="Test similarity thresholds with configurable embedding model",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Examples:
  # Test all models (default behavior)
  python test_similarity_thresholds.py
  python test_similarity_thresholds.py --all-models

  # Test specific model
  python test_similarity_thresholds.py --model text-embedding-3-large

  # Use model via environment variable
  EMBEDDING_MODEL=text-embedding-ada-002 python test_similarity_thresholds.py

Available models: {', '.join(AVAILABLE_MODELS)}
        """
    )
    parser.add_argument(
        "--model",
        "--embedding-model",
        dest="embedding_model",
        type=str,
        default=None,
        choices=AVAILABLE_MODELS + [None],
        help=f"Embedding model to use. If not specified, tests all models. Can also be set via EMBEDDING_MODEL env var."
    )
    parser.add_argument(
        "--all-models",
        action="store_true",
        help="Test all available embedding models (overrides --model)"
    )
    
    args = parser.parse_args()
    
    # Determine which models to test
    if args.all_models or args.embedding_model is None:
        models_to_test = AVAILABLE_MODELS
    else:
        models_to_test = [args.embedding_model]
    
    print("="*80)
    print("SIMILARITY THRESHOLD EVALUATION TEST")
    print("="*80)
    print(f"\nTesting models: {', '.join(models_to_test)}")
    print(f"Testing thresholds: {', '.join(map(str, THRESHOLDS))}")
    print(f"API URL: {API_URL}")
    print("="*80)
    
    # Check if API is accessible
    try:
        api_stats = requests.get(f"{API_URL}/stats", timeout=5)
        api_stats.raise_for_status()
        stats_data = api_stats.json()
        
        # Check if LLM call limit might be an issue
        current_llm_calls = stats_data.get("llm_calls", 0)
        total_tests = len(models_to_test) * len(THRESHOLDS)
        estimated_calls = total_tests * (sum(len(queries) for queries in BASE_QUERIES.values()) + 16)
        if current_llm_calls > 50 or estimated_calls > 200:  # Warning threshold
            print(f"\n⚠️  Warning: API shows {current_llm_calls} LLM calls already used.")
            print(f"   The test will make approximately {estimated_calls} API calls across {total_tests} test runs.")
            print(f"   If MAX_LLM_CALLS is 100, you may hit the limit.")
            print(f"   Consider increasing MAX_LLM_CALLS: export MAX_LLM_CALLS=500")
            print()
    except Exception as e:
        print(f"\n❌ Error: Cannot connect to API at {API_URL}")
        print("   Please ensure the API is running: docker compose up")
        return
    
    all_results: List[TestResult] = []
    all_summaries: List[ThresholdSummary] = []
    
    # Test each model
    for model_idx, embedding_model in enumerate(models_to_test):
        print(f"\n{'#'*100}")
        print(f"# Testing Model: {embedding_model} ({model_idx + 1}/{len(models_to_test)})")
        print(f"{'#'*100}")
        
        # Clear cache before starting a new model (except for the first one)
        if model_idx > 0:
            print("\nClearing cache before starting new model...")
            clear_cache()
            time.sleep(1.0)
        
        # Test each threshold for this model
        for threshold in THRESHOLDS:
            summary, results = test_threshold(threshold, embedding_model)
            all_summaries.append(summary)
            all_results.extend(results)
            
            print(f"\n📊 Threshold {threshold} ({embedding_model}):")
            print(f"  Hit rate: {summary.hit_rate*100:.1f}%")
            print(f"  Acceptability: {summary.acceptability_rate*100:.1f}%")
            print(f"  LLM calls: {summary.llm_calls}")
            print(f"  Estimated cost: ${summary.estimated_cost:.6f}")
            print(f"  Estimated savings: ${summary.estimated_savings:.6f}")
            if summary.avg_similarity_on_hit > 0:
                print(f"  Similarity range: {summary.min_similarity_on_hit:.3f} - {summary.max_similarity_on_hit:.3f} (avg: {summary.avg_similarity_on_hit:.3f})")
    
    # Print summary table
    print_summary_table(all_summaries)
    
    # Generate visualizations if multiple models were tested
    if len(models_to_test) > 1:
        print("\n" + "="*80)
        print("Generating visualizations...")
        print("="*80)
        visualize_results(all_summaries)
    
    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if len(models_to_test) > 1:
        results_file = f"threshold_test_results_all_models_{timestamp}.json"
    else:
        model_suffix = models_to_test[0].replace("text-embedding-", "").replace("-", "_")
        results_file = f"threshold_test_results_{model_suffix}_{timestamp}.json"
    
    with open(results_file, "w") as f:
        json.dump({
            "models_tested": models_to_test,
            "results": [asdict(r) for r in all_results],
            "summaries": [asdict(s) for s in all_summaries],
            "thresholds": THRESHOLDS,
        }, f, indent=2)
    
    print(f"\n✅ Results saved to: {results_file}")
    print("\n" + "="*80)
    print("✅ Test complete!")
    print("="*80)


if __name__ == "__main__":
    main()
