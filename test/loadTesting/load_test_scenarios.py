#!/usr/bin/env python3
"""
Load Test Scenarios

Predefined test scenarios for load testing.
All scenarios use pre-populated cache to minimize API costs.
"""

from dataclasses import dataclass
from typing import List


@dataclass
class LoadTestScenario:
    """Represents a load test scenario."""
    name: str
    description: str
    concurrent_users: int
    requests_per_user: int
    request_rate_per_user: float  # requests per second per user
    duration_seconds: int
    expected_cache_hit_rate: float  # Expected cache hit rate (0.0 to 1.0)
    estimated_cost: float  # Estimated API cost in dollars


# Pre-populated queries for load testing (should be cached)
LOAD_TEST_QUERIES = [
    "What's the weather today?",
    "How do I reset my password?",
    "What's the latest news?",
    "Bitcoin price",
    "Python tutorial",
    "Current weather conditions",
    "I need to change my password",
    "Breaking news headlines",
    "Stock prices",
    "How to write code?",
]


# Load test scenarios
SCENARIOS = [
    LoadTestScenario(
        name="baseline",
        description="Baseline load test",
        concurrent_users=10,
        requests_per_user=10,
        request_rate_per_user=1.0,  # 1 req/sec
        duration_seconds=10,
        expected_cache_hit_rate=0.95,
        estimated_cost=0.05,  # Minimal - mostly cache hits
    ),
    LoadTestScenario(
        name="moderate",
        description="Moderate load test",
        concurrent_users=50,
        requests_per_user=20,
        request_rate_per_user=2.0,  # 2 req/sec
        duration_seconds=10,
        expected_cache_hit_rate=0.95,
        estimated_cost=0.10,  # Minimal - mostly cache hits
    ),
    LoadTestScenario(
        name="high",
        description="High load test",
        concurrent_users=200,
        requests_per_user=25,
        request_rate_per_user=5.0,  # 5 req/sec
        duration_seconds=5,
        expected_cache_hit_rate=0.90,
        estimated_cost=0.20,  # Some cache misses
    ),
    LoadTestScenario(
        name="spike",
        description="Traffic spike test",
        concurrent_users=500,
        requests_per_user=6,
        request_rate_per_user=10.0,  # 10 req/sec (burst)
        duration_seconds=1,
        expected_cache_hit_rate=0.85,
        estimated_cost=0.15,  # More cache misses during spike
    ),
    LoadTestScenario(
        name="sustained",
        description="Sustained load test",
        concurrent_users=100,
        requests_per_user=50,
        request_rate_per_user=2.0,  # 2 req/sec
        duration_seconds=25,
        expected_cache_hit_rate=0.95,
        estimated_cost=0.10,  # Minimal - mostly cache hits
    ),
]


def get_scenario(name: str) -> LoadTestScenario:
    """Get a scenario by name."""
    for scenario in SCENARIOS:
        if scenario.name == name:
            return scenario
    raise ValueError(f"Unknown scenario: {name}")


def get_all_scenarios() -> List[LoadTestScenario]:
    """Get all scenarios."""
    return SCENARIOS.copy()
