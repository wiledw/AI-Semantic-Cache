#!/bin/bash

# Quick start script for similarity threshold testing
# Usage: ./run_threshold_tests.sh [--model MODEL_NAME]
#   or: EMBEDDING_MODEL=model_name ./run_threshold_tests.sh

set -e

# Parse command-line arguments
EMBEDDING_MODEL_ARG=""
if [ "$1" == "--model" ] || [ "$1" == "--embedding-model" ]; then
    if [ -z "$2" ]; then
        echo "❌ Error: --model requires a model name"
        echo "   Available models: text-embedding-3-small, text-embedding-3-large, text-embedding-ada-002"
        exit 1
    fi
    EMBEDDING_MODEL_ARG="--model $2"
    shift 2
fi

# Use environment variable if set, otherwise use command-line arg
if [ -n "$EMBEDDING_MODEL" ]; then
    EMBEDDING_MODEL_ARG="--model $EMBEDDING_MODEL"
fi

echo "=========================================="
echo "Similarity Threshold Testing Suite"
echo "=========================================="
echo ""

# Check if API is running
echo "Checking if API is running..."
if ! curl -s http://localhost:3000/api/stats > /dev/null 2>&1; then
    echo "⚠️  Warning: API doesn't seem to be running at http://localhost:3000"
    echo "   Please start it with: docker compose up"
    echo ""
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Check Python dependencies
echo "Checking Python dependencies..."
python3 -c "import requests" 2>/dev/null || {
    echo "⚠️  Missing 'requests'. Installing..."
    pip install requests
}

# Check Redis (optional but recommended)
python3 -c "import redis" 2>/dev/null || {
    echo "⚠️  Missing 'redis' module. Cache clearing may not work properly."
    echo "   Install with: pip install redis"
}

echo ""
echo "Starting similarity threshold test..."
echo "This will test thresholds: 0.75, 0.80, 0.85, 0.90"
if [ -n "$EMBEDDING_MODEL_ARG" ]; then
    echo "Using embedding model from argument/environment"
else
    echo "Using default embedding model: text-embedding-3-small"
fi
echo ""

# Run test with embedding model argument if provided
python3 test_similarity_thresholds.py $EMBEDDING_MODEL_ARG

# Find the most recent results file (may include model suffix)
RESULTS_FILE=$(ls -t threshold_test_results_*.json 2>/dev/null | head -1)

if [ -n "$RESULTS_FILE" ]; then
    echo ""
    echo "✅ Test complete!"
    echo "   Results: $RESULTS_FILE"
else
    echo "❌ No results file found!"
    exit 1
fi

echo ""
echo "=========================================="
echo "✅ All tests complete!"
echo "=========================================="
echo ""
