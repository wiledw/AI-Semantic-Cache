# Final Testing Suite

Comprehensive testing suite for the Boardy Semantic Cache system, covering load testing, resilience (circuit breakers and graceful degradation), and diverse query pattern testing.

## Budget-Aware Testing

**Total API Budget: $5.00**

All tests are designed to minimize API costs:
- **Pre-populated cache**: One-time cache population (~$1.50) before running tests
- **Mocked services**: All failure scenarios use mocked OpenAI/Redis/Weaviate ($0 cost)
- **High cache hit rates**: Load and pattern tests achieve 95%+ cache hits
- **Cost tracking**: Built-in cost tracking warns when approaching budget limits

**Estimated Total Cost: ~$2.30** (leaves $2.70 buffer)

## Test Structure

```
test/
├── utils/                    # Shared utilities
│   ├── cost_tracker.py      # API cost tracking
│   ├── mock_openai.py       # Mock OpenAI client
│   └── populate_cache.py   # Cache pre-population script
├── queryPatterns/           # Query pattern testing
│   ├── query_datasets.py   # Query datasets
│   ├── test_query_patterns.py
│   └── run_query_tests.sh
├── loadTesting/             # Load testing
│   ├── load_test_scenarios.py
│   ├── test_load_performance.py
│   └── run_load_tests.sh
├── resilience/              # Resilience testing
│   ├── test_circuit_breakers.py
│   └── test_graceful_degradation.py
└── run_all_tests.sh        # Master test runner
```

## Quick Start

### 1. Start the API

```bash
docker compose up
```

### 2. Populate Cache (One-Time)

```bash
python3 test/utils/populate_cache.py
```

This populates the cache with diverse queries (~$1.50 cost, one-time).

### 3. Run All Tests

```bash
./test/run_all_tests.sh
```

Or run individual test suites:

```bash
# Query pattern tests
./test/queryPatterns/run_query_tests.sh

# Load testing
./test/loadTesting/run_load_tests.sh

# Resilience tests (no API cost)
python3 test/resilience/test_circuit_breakers.py
python3 test/resilience/test_graceful_degradation.py
```

## Test Suites

### 1. Query Pattern Testing

Tests semantic cache against diverse query patterns:

- **Exact duplicates**: Same query repeated (100% cache hit expected)
- **Semantically similar**: Different wording, same intent (>85% similarity expected)
- **Unrelated queries**: Different topics (<50% similarity expected)
- **Time-sensitive vs evergreen**: TTL and age-based invalidation
- **Varying complexity**: Short, medium, long queries
- **Different languages**: English, Spanish, French, Chinese, Japanese
- **Special characters**: Unicode, emojis, SQL injection attempts, XSS

**Cost**: ~$0.20 (uses pre-populated cache)

**Run**: `./test/queryPatterns/run_query_tests.sh`

### 2. Load Testing

Tests system performance under various load scenarios:

- **Baseline**: 10 concurrent users, 1 req/sec
- **Moderate**: 50 concurrent users, 2 req/sec
- **High**: 200 concurrent users, 5 req/sec
- **Spike**: 500 concurrent users for 30 seconds
- **Sustained**: 100 concurrent users for 5 minutes

**Metrics tracked**:
- Latency (p50, p95, p99)
- Throughput (requests/second)
- Cache hit rate
- Error rate

**Cost**: ~$0.60 (uses pre-populated cache, 95%+ cache hits)

**Run**: `./test/loadTesting/run_load_tests.sh`

### 3. Resilience Testing

Tests system behavior under failures and high load:

#### Circuit Breakers

Tests circuit breaker functionality for:
- OpenAI API failures
- Redis failures
- Weaviate failures

**Cost**: $0 (all mocked)

**Run**: `python3 test/resilience/test_circuit_breakers.py`

#### Graceful Degradation

Tests system behavior under:
- Overload scenarios (1000+ concurrent requests)
- Resource exhaustion
- Error response handling

**Cost**: ~$0.10 (uses cached data)

**Run**: `python3 test/resilience/test_graceful_degradation.py`

## Cost Tracking

All tests use the cost tracker to monitor API usage:

```python
from test.utils.cost_tracker import get_tracker

tracker = get_tracker(budget=5.0)
tracker.record_llm_call("gpt-4o-mini", test_suite="load_testing")
tracker.print_summary()
```

The tracker:
- Warns at 80%, 90%, 95% budget usage
- Stops tests if budget exceeded
- Generates cost reports

## Results

Test results are saved in `test/results/`:

- `query_patterns/results_*.json`: Query pattern test results
- `query_patterns/cost_report_*.json`: Cost reports
- `load_testing/results_*.json`: Load test results
- `load_testing/cost_report_*.json`: Cost reports
- `cost_log.jsonl`: Detailed cost log

## Environment Variables

- `API_URL`: API endpoint (default: `http://localhost:3000/api/query`)
- `STATS_URL`: Stats endpoint (default: `http://localhost:3000/api/stats`)
- `API_BUDGET`: Total budget in dollars (default: `5.0`)
- `COST_LOG_FILE`: Path to cost log file (default: `test/results/cost_log.jsonl`)

## Success Criteria

### Load Testing
- System handles 500 req/sec peak load
- P95 latency < 2000ms for cache misses
- P95 latency < 50ms for cache hits
- Error rate < 1% under normal load
- Error rate < 5% under peak load

### Resilience
- Circuit breakers prevent cascade failures
- System degrades gracefully under load
- No crashes or data loss during failures
- Automatic recovery when services restore

### Query Patterns
- 100% accuracy on exact duplicates
- >90% accuracy on semantically similar queries
- 0% false positives on unrelated queries
- Correct TTL handling for time-sensitive vs evergreen
- All languages and special characters handled safely

## Troubleshooting

### API Not Accessible

Make sure the API is running:
```bash
docker compose up
```

Check API health:
```bash
curl http://localhost:3000/api/stats
```

### Budget Exceeded

If you exceed the budget:
1. Check cost reports in `test/results/`
2. Re-run cache population to ensure cache is populated
3. Most tests should use cached data (95%+ hit rate)

### Tests Failing

1. Check API logs: `docker compose logs api`
2. Verify cache is populated: Run `populate_cache.py`
3. Check Redis: `docker compose exec redis redis-cli KEYS "*"`

## Notes

- All tests are designed to be runnable in CI/CD pipelines
- Tests are deterministic and repeatable
- Load tests should be run against staging environment, not production
- Circuit breakers are configurable and monitorable
- Query pattern tests validate both correctness and performance
