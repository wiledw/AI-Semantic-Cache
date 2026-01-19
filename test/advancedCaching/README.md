# Advanced Caching Strategies Test Suite

This test suite demonstrates and validates the implementation of:

1. **Time-Based Cache Invalidation**: TTL + age-based limits per query type
2. **Topic-Based Cache Partitioning**: Keyword + embedding fallback for efficient search

## Features Tested

### Time-Based Cache Invalidation
- Verifies that cache entries respect both TTL and age-based limits
- Tests that stale entries are rejected even if TTL hasn't expired
- Demonstrates different invalidation rules for different query types (weather, news, price, score)

### Topic-Based Cache Partitioning
- Tests topic extraction (keyword-based and embedding fallback)
- Verifies that cache searches are partitioned by topic
- Measures cache hit rates by topic
- Demonstrates improved search efficiency through partitioning

### Combined Features
- Tests both features working together
- Measures overall cache performance improvements
- Validates that features complement each other

## Running the Tests

### Prerequisites
1. API server must be running:
   ```bash
   docker compose up
   ```

2. Python dependencies:
   ```bash
   pip install aiohttp
   ```

### Run Tests

```bash
# From project root
cd test/advancedCaching
./run_tests.sh

# Or directly
python3 test/advanced_caching.py
```

### Environment Variables

You can configure the test behavior:

```bash
export API_URL="http://localhost:3000/api/query"
export STATS_URL="http://localhost:3000/api/stats"
```

## Test Output

The test suite provides:

1. **Test 1: Time-Based Cache Invalidation**
   - Initial cache population
   - Immediate cache hit verification
   - Notes on testing age-based invalidation

2. **Test 2: Topic-Based Cache Partitioning**
   - Cache population with queries from different topics
   - Topic distribution analysis
   - Cache hit rates by topic

3. **Test 3: Combined Features**
   - Both features working together
   - Overall performance metrics

4. **Final Summary**
   - Overall cache statistics
   - Key improvements demonstrated

## Expected Results

### Time-Based Invalidation
- Cache entries should be served immediately after caching
- Entries should be rejected if they exceed age limits (requires configuration)
- Different query types should have different age limits

### Topic Partitioning
- Queries should be correctly classified into topics
- Cache searches should find matches within topic partitions
- Hit rates should improve due to more focused searches

### Combined
- Both features should work together seamlessly
- Overall cache hit rate should be high (>80% for repeated queries)
- Average latency should be low for cache hits (<50ms)

## Advanced Testing

### Testing Age-Based Invalidation

To fully test age-based invalidation, set very short max ages:

```bash
export MAX_AGE_BY_QUERY_TYPE='{"weather": 60, "news": 30, "price": 30, "score": 10}'
```

Then:
1. Run queries to populate cache
2. Wait for the max_age period (e.g., 60 seconds for weather)
3. Run the same queries again
4. Verify entries are rejected even if TTL hasn't expired

### Testing Topic Centroids

To test embedding-based topic classification:

1. Initialize topic centroids in Redis (future enhancement)
2. Run queries that don't match keyword patterns
3. Verify they're classified correctly via embeddings

## Troubleshooting

### API Not Running
```
❌ Error: API is not running at http://localhost:3000/api/stats
```
**Solution**: Start the API server with `docker compose up`

### Dependencies Missing
```
❌ Error: aiohttp not installed
```
**Solution**: Install with `pip install aiohttp`

### Low Cache Hit Rates
- Ensure queries are semantically similar
- Check that similarity threshold is appropriate (default 0.85)
- Verify cache entries are not being invalidated too aggressively

### Topic Classification Issues
- Verify topic keywords are matching correctly
- Check logs for topic extraction results
- Ensure embedding-based fallback is working (if centroids are configured)

## Integration with CI/CD

The test suite can be integrated into CI/CD pipelines:

```yaml
# Example GitHub Actions
- name: Run Advanced Caching Tests
  run: |
    docker compose up -d
    sleep 10  # Wait for services to start
    cd test/advancedCaching
    python3 test_advanced_caching.py
```

## Future Enhancements

- [ ] Automated age-based invalidation testing with time manipulation
- [ ] Topic centroid initialization and testing
- [ ] Performance benchmarking (latency improvements)
- [ ] Cache hit rate comparison (before/after features)
- [ ] Memory usage analysis by topic partition
