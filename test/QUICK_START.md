# Quick Start - Final Testing

## ⚠️ IMPORTANT: Always Run from Project Root

**All test scripts must be run from the project root directory**, not from subdirectories.

```bash
# ✅ Correct - Run from project root
cd /Users/wiledw/boardy
python3 test/utils/populate_cache.py

# ❌ Wrong - Don't run from subdirectories
cd test/utils
python3 populate_cache.py  # This will fail with import errors
```

## Step-by-Step Testing

### 1. Start the System

```bash
cd /Users/wiledw/boardy
docker compose up
```

Wait for all services to be ready (check logs for "Application startup complete").

### 2. Populate Cache (One-Time, ~$1.50)

```bash
cd /Users/wiledw/boardy
python3 test/utils/populate_cache.py
```

**Expected**: Script connects to API and populates cache with ~50 queries.

### 3. Run All Tests

```bash
cd /Users/wiledw/boardy
./test/run_all_tests.sh
```

This will:
- Prompt to populate cache (say 'n' if already done)
- Run query pattern tests
- Run load tests  
- Run resilience tests
- Generate reports

### 4. Check Results

```bash
# View results
ls -la test/results/

# View cost reports
cat test/results/*/cost_report_*.json | jq '.summary'
```

## Individual Test Commands

All commands should be run from `/Users/wiledw/boardy`:

```bash
# Query pattern tests
python3 test/queryPatterns/test_query_patterns.py

# Load tests
python3 test/loadTesting/test_load_performance.py

# Circuit breaker tests (mocked, $0 cost)
python3 test/resilience/test_circuit_breakers.py

# Graceful degradation tests
python3 test/resilience/test_graceful_degradation.py
```

## Troubleshooting

### Import Error: `ModuleNotFoundError: No module named 'test.utils'`

**Solution**: Make sure you're in the project root:
```bash
cd /Users/wiledw/boardy  # Go to project root
python3 test/utils/populate_cache.py  # Now it will work
```

### API Not Accessible

**Solution**: 
```bash
# Check if API is running
docker compose ps

# Check API health
curl http://localhost:3000/api/stats
```

## Expected Costs

- Cache population: ~$1.50 (one-time)
- Query pattern tests: ~$0.20
- Load tests: ~$0.60
- Resilience tests: $0.00 (all mocked)
- **Total: ~$2.30** (within $5 budget)
