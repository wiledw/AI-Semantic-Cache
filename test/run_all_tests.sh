#!/bin/bash
# Master Test Runner

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

echo "=========================================="
echo "Final Testing Suite - Master Runner"
echo "=========================================="
echo ""
echo "This script runs all test suites in order:"
echo "  1. Cache population (one-time, ~\$1.50)"
echo "  2. Query pattern tests (~\$0.20)"
echo "  3. Load testing (~\$0.60)"
echo "  4. Resilience tests (\$0 - all mocked)"
echo ""
echo "Total estimated cost: ~\$2.30 (within \$5 budget)"
echo ""

# Check if API is running
if ! curl -s -f http://localhost:3000/api/stats > /dev/null 2>&1; then
    echo "❌ API is not running at http://localhost:3000"
    echo "Please start the API first: docker compose up"
    exit 1
fi

echo "✅ API is accessible"
echo ""

# Create results directory
mkdir -p test/results

# Step 1: Cache population (optional - skip if already populated)
echo "=========================================="
echo "Step 1: Cache Population (Optional)"
echo "=========================================="
echo ""
read -p "Populate cache now? (y/n) " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Running cache population..."
    python3 test/utils/populate_cache.py
    echo ""
else
    echo "Skipping cache population (assuming cache is already populated)"
    echo ""
fi

# Step 2: Query pattern tests
echo "=========================================="
echo "Step 2: Query Pattern Tests"
echo "=========================================="
echo ""
python3 test/queryPatterns/test_query_patterns.py
QUERY_EXIT=$?

if [ $QUERY_EXIT -ne 0 ]; then
    echo "❌ Query pattern tests failed"
    exit $QUERY_EXIT
fi

# Step 3: Load testing
echo ""
echo "=========================================="
echo "Step 3: Load Testing"
echo "=========================================="
echo ""
python3 test/loadTesting/test_load_performance.py
LOAD_EXIT=$?

if [ $LOAD_EXIT -ne 0 ]; then
    echo "❌ Load tests failed"
    exit $LOAD_EXIT
fi

# Step 4: Resilience tests (no API costs)
echo ""
echo "=========================================="
echo "Step 4: Resilience Tests (Mocked)"
echo "=========================================="
echo ""
python3 test/resilience/test_circuit_breakers.py
CIRCUIT_EXIT=$?

if [ $CIRCUIT_EXIT -ne 0 ]; then
    echo "❌ Circuit breaker tests failed"
    exit $CIRCUIT_EXIT
fi

python3 test/resilience/test_graceful_degradation.py
DEGRADATION_EXIT=$?

if [ $DEGRADATION_EXIT -ne 0 ]; then
    echo "❌ Graceful degradation tests failed"
    exit $DEGRADATION_EXIT
fi

# Final summary
echo ""
echo "=========================================="
echo "All Tests Completed"
echo "=========================================="
echo ""
echo "✅ All test suites passed!"
echo ""
echo "Results saved in: test/results/"
echo ""

exit 0
