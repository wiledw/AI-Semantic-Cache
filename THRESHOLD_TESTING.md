# Similarity Threshold Testing Guide

This guide explains how to test different similarity thresholds and analyze the results.

## Overview

The testing suite evaluates similarity thresholds (0.75, 0.80, 0.85, 0.90) against a curated dataset to measure:
- Cache hit/miss rates
- Response acceptability
- Cost savings
- Similarity score distributions

## Prerequisites

1. Ensure the API service is running:
   ```bash
   docker compose up --build
   ```

2. Install additional Python dependencies:
   ```bash
   pip install requests matplotlib seaborn pandas
   ```

## Running the Tests

1. **Start the API service** (if not already running):
   ```bash
   docker compose up
   ```

2. **Run the test script**:
   ```bash
   python test_similarity_thresholds.py
   ```

   The script will:
   - Test each threshold (0.75, 0.80, 0.85, 0.90) sequentially
   - Clear the cache between threshold tests for clean results
   - Run queries from the evaluation dataset
   - Save results to a JSON file: `threshold_test_results_YYYYMMDD_HHMMSS.json`

3. **Generate visualizations**:
   ```bash
   python visualize_results.py threshold_test_results_YYYYMMDD_HHMMSS.json
   ```

   This creates:
   - `threshold_test_output/threshold_comparison.png` - Comprehensive comparison charts
   - `threshold_test_output/cost_analysis.png` - Detailed cost analysis
   - `threshold_test_output/summary_table.png` - Summary table visualization
   - `threshold_test_output/summary_table.csv` - CSV data export

## Evaluation Dataset

The test uses three groups of queries:

### Group A - Semantically Equivalent
- "How do I change my password?"
- "I need to reset my login credentials."
- "Where is the option to update my secret word?"

**Expected**: Cache hits should be acceptable (semantically equivalent queries)

### Group B - Related but Not Equivalent
- "How do I change my password?"
- "How do I change my billing address?"

**Expected**: Cache hits are tricky - only acceptable if similarity > 0.90

### Group C - Unrelated
- "How do I change my password?"
- "What are the new features in the v2.0 update?"

**Expected**: Should rarely hit cache, and if they do, it's likely incorrect

## Understanding the Results

### Metrics Explained

1. **Cache Hit Rate**: Percentage of queries that found a cached response
   - Higher threshold → Lower hit rate → More LLM calls
   - Lower threshold → Higher hit rate → Fewer LLM calls (but riskier)

2. **Acceptability Rate**: Percentage of responses that are considered acceptable
   - Group A cache hits: Always acceptable (semantically equivalent)
   - Group B cache hits: Acceptable only if similarity > 0.90
   - Group C cache hits: Not acceptable (unrelated queries)
   - Cache misses: Always acceptable (fresh LLM response)

3. **Cost Savings**: 
   - **LLM Cost**: Cost of actual LLM calls made
   - **Cache Savings**: Cost saved by serving cached responses
   - **Net Savings**: Cache Savings - LLM Cost

### Interpreting Thresholds

- **0.75 (Aggressive)**: 
  - Highest cache hit rate
  - Most cost savings potential
  - Higher risk of incorrect matches
  
- **0.80**: 
  - Balanced approach
  - Moderate hit rate and risk

- **0.85 (Default)**:
  - Current system default
  - Baseline for comparison

- **0.90 (Conservative)**:
  - Lowest cache hit rate
  - Highest accuracy
  - More LLM calls required

## Cost Calculation

The cost model assumes:
- `LLM_COST_PER_CALL`: $0.01 per LLM call (configurable via environment variable)

**Cost Savings Formula**:
```
Total Cost Without Cache = Total Queries × LLM_COST_PER_CALL
Actual Cost = LLM Calls × LLM_COST_PER_CALL
Cache Savings = Cache Hits × LLM_COST_PER_CALL
Net Savings = Cache Savings - Actual Cost
Savings Percentage = (Cache Savings / (Actual Cost + Cache Savings)) × 100
```

## Example Output

After running the tests, you'll see:

```
Threshold Comparison:
Threshold     Hit Rate     LLM Calls   Cost         Savings    
------------------------------------------------------------
0.75          85.7%        2           0.0200       0.0600     
0.80          71.4%        4           0.0400       0.0400     
0.85          57.1%        6           0.0600       0.0200     
0.90          42.9%        8           0.0800       0.0000     
```

## Troubleshooting

1. **API Connection Error**:
   - Ensure the API is running: `docker compose up`
   - Check `API_URL` environment variable (default: `http://localhost:3000/api`)

2. **Redis Connection Error**:
   - Ensure Redis is running in Docker
   - Check `REDIS_URL` environment variable (default: `redis://localhost:6379/0`)

3. **No Cache Hits**:
   - This is normal for the first run of each threshold
   - The test runs queries twice: first to populate cache, second to test cache behavior

4. **Visualization Errors**:
   - Ensure matplotlib, seaborn, and pandas are installed
   - Check that the results JSON file exists and is valid

## Next Steps

After analyzing the results:

1. **Choose optimal threshold** based on your accuracy vs cost requirements
2. **Update `.env`** with the chosen `SIMILARITY_THRESHOLD` value
3. **Monitor production** metrics to validate the choice
4. **Iterate** if needed based on real-world performance
