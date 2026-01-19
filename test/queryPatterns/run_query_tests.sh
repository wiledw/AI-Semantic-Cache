#!/bin/bash
# Query Pattern Test Runner

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$PROJECT_ROOT"

echo "=========================================="
echo "Query Pattern Testing Suite"
echo "=========================================="
echo ""

# Check if API is running
if ! curl -s -f http://localhost:3000/api/stats > /dev/null 2>&1; then
    echo "❌ API is not running at http://localhost:3000"
    echo "Please start the API first: docker compose up"
    exit 1
fi

echo "✅ API is accessible"
echo ""

# Run tests
python3 test/queryPatterns/test_query_patterns.py

exit_code=$?

if [ $exit_code -eq 0 ]; then
    echo ""
    echo "✅ All query pattern tests passed!"
else
    echo ""
    echo "❌ Some tests failed"
fi

exit $exit_code
