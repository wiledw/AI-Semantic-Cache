#!/bin/bash
# Run Advanced Caching Strategies Test Suite

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "🧪 Advanced Caching Strategies Test Suite"
echo "=========================================="
echo ""

# Check if API is running
API_URL="${API_URL:-http://localhost:3000/api/stats}"
if ! curl -s "$API_URL" > /dev/null 2>&1; then
    echo "❌ Error: API is not running at $API_URL"
    echo "   Please start the API server first:"
    echo "   docker compose up"
    exit 1
fi

echo "✅ API is running"
echo ""

# Check Python dependencies
echo "Checking Python dependencies..."
python3 -c "import aiohttp" 2>/dev/null || {
    echo "❌ Error: aiohttp not installed"
    echo "   Install with: pip install aiohttp"
    exit 1
}

echo "✅ Dependencies OK"
echo ""

# Run the test
cd "$PROJECT_ROOT"
python3 "$SCRIPT_DIR/test_advanced_caching.py"

echo ""
echo "✅ Test suite completed!"
