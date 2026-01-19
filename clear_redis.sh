#!/bin/bash

# Script to clear all Redis data
# This will flush all keys from the Redis cache

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Clearing Redis cache...${NC}"

# Try to use docker exec first (most common case)
if command -v docker &> /dev/null; then
    # Check if redis container is running
    if docker ps --format '{{.Names}}' | grep -q "^boardy-redis-1$\|^.*redis.*$"; then
        REDIS_CONTAINER=$(docker ps --format '{{.Names}}' | grep -i redis | head -n 1)
        echo -e "${YELLOW}Using Docker container: ${REDIS_CONTAINER}${NC}"
        docker exec "${REDIS_CONTAINER}" redis-cli FLUSHALL
        echo -e "${GREEN}✓ Successfully cleared all Redis data via Docker${NC}"
        exit 0
    fi
    
    # Try docker compose naming convention
    if docker ps --format '{{.Names}}' | grep -q ".*_redis_"; then
        REDIS_CONTAINER=$(docker ps --format '{{.Names}}' | grep -i redis | head -n 1)
        echo -e "${YELLOW}Using Docker container: ${REDIS_CONTAINER}${NC}"
        docker exec "${REDIS_CONTAINER}" redis-cli FLUSHALL
        echo -e "${GREEN}✓ Successfully cleared all Redis data via Docker${NC}"
        exit 0
    fi
fi

# Fallback: try direct redis-cli connection
if command -v redis-cli &> /dev/null; then
    echo -e "${YELLOW}Attempting direct connection to Redis on localhost:6379...${NC}"
    if redis-cli -h localhost -p 6379 ping &> /dev/null; then
        redis-cli -h localhost -p 6379 FLUSHALL
        echo -e "${GREEN}✓ Successfully cleared all Redis data via direct connection${NC}"
        exit 0
    fi
fi

# If docker compose is available, try to start redis and clear it
if command -v docker-compose &> /dev/null || command -v docker &> /dev/null; then
    echo -e "${YELLOW}Redis container not running. Attempting to start it...${NC}"
    if command -v docker-compose &> /dev/null; then
        docker-compose up -d redis 2>/dev/null || true
    else
        docker compose up -d redis 2>/dev/null || true
    fi
    
    sleep 2
    
    # Try again
    if docker ps --format '{{.Names}}' | grep -i redis | head -n 1 | xargs -I {} docker exec {} redis-cli FLUSHALL 2>/dev/null; then
        echo -e "${GREEN}✓ Successfully cleared all Redis data${NC}"
        exit 0
    fi
fi

echo -e "${RED}✗ Failed to clear Redis. Please ensure:${NC}"
echo -e "  1. Docker is installed and running"
echo -e "  2. Redis container is running (try: docker compose up -d redis)"
echo -e "  3. Or install redis-cli and ensure Redis is accessible on localhost:6379"
exit 1
