#!/bin/bash

# Test script to generate metrics data for visualization
# Usage: ./test_metrics.sh

API_URL="${API_URL:-http://localhost:3000/api/query}"

echo "🚀 Starting metrics test..."
echo "API URL: $API_URL"
echo ""

# Array of queries - first set (will be cache misses)
queries=(
  "How to reset password?"
  "How do I reset my password?"
  "Password reset instructions"
  "What is the weather today?"
  "Current weather conditions"
  "How to update profile?"
  "Update my profile information"
  "Profile update guide"
  "How to change email?"
  "Email change process"
)

echo "📤 Phase 1: Sending initial queries (cache misses)..."
for i in "${!queries[@]}"; do
  query="${queries[$i]}"
  echo "  [$((i+1))/${#queries[@]}] Sending: $query"
  curl -X POST "$API_URL" \
    -H "Content-Type: application/json" \
    -d "{\"query\": \"$query\"}" \
    -s -o /dev/null -w "  Status: %{http_code}\n"
  sleep 1
done

echo ""
echo "⏳ Waiting 3 seconds..."
sleep 3

echo ""
echo "📤 Phase 2: Sending similar queries (should hit cache)..."
for i in "${!queries[@]}"; do
  query="${queries[$i]}"
  echo "  [$((i+1))/${#queries[@]}] Sending: $query"
  curl -X POST "$API_URL" \
    -H "Content-Type: application/json" \
    -d "{\"query\": \"$query\"}" \
    -s -o /dev/null -w "  Status: %{http_code}\n"
  sleep 1
done

echo ""
echo "📊 Checking metrics..."
curl -s "$API_URL/../metrics?hours=1&interval_seconds=60" | python3 -m json.tool 2>/dev/null || echo "Metrics endpoint response received"

echo ""
echo "✅ Test complete!"
echo ""
echo "📈 Next steps:"
echo "   1. Open http://localhost:5173 in your browser"
echo "   2. Check the 'Cache Performance Over Time' chart"
echo "   3. Hit rate should increase as more queries are cached"
echo ""
echo "💡 Tip: Run this script multiple times to see the hit rate improve!"
