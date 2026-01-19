#!/bin/bash

# Script to clear all Redis and Weaviate data
# This will flush all keys from Redis AND delete persistence files
# Also clears Weaviate data if enabled

# Don't exit on error - we want to try all cleanup methods
set +e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Clearing Redis cache and persistence files...${NC}"

REDIS_CONTAINER=""
WEAVIATE_CONTAINER=""

# Find Redis container
if command -v docker &> /dev/null; then
    REDIS_CONTAINER=$(docker ps --format '{{.Names}}' | grep -i redis | head -n 1 || true)
    WEAVIATE_CONTAINER=$(docker ps --format '{{.Names}}' | grep -i weaviate | head -n 1 || true)
fi

# Clear Redis
if [ -n "$REDIS_CONTAINER" ]; then
    echo -e "${YELLOW}Found Redis container: ${REDIS_CONTAINER}${NC}"
    
    # Flush all data from memory
    echo -e "${YELLOW}  → Flushing all Redis keys...${NC}"
    docker exec "${REDIS_CONTAINER}" redis-cli FLUSHALL > /dev/null 2>&1 || true
    
    # Delete persistence files to prevent data from being restored on restart
    echo -e "${YELLOW}  → Removing Redis persistence files...${NC}"
    docker exec "${REDIS_CONTAINER}" sh -c "rm -f /data/dump.rdb /data/appendonly.aof" 2>/dev/null || true
    
    # Also try to save empty state (creates new empty persistence files)
    docker exec "${REDIS_CONTAINER}" redis-cli BGSAVE > /dev/null 2>&1 || true
    
    echo -e "${GREEN}✓ Successfully cleared Redis data and persistence files${NC}"
else
    # Fallback: try direct redis-cli connection
    if command -v redis-cli &> /dev/null; then
        echo -e "${YELLOW}Attempting direct connection to Redis on localhost:6379...${NC}"
        if redis-cli -h localhost -p 6379 ping &> /dev/null; then
            redis-cli -h localhost -p 6379 FLUSHALL
            echo -e "${GREEN}✓ Successfully cleared all Redis data via direct connection${NC}"
            echo -e "${YELLOW}⚠ Note: Persistence files may still exist. Manually delete them if needed.${NC}"
        fi
    fi
fi

# Clear Weaviate if container exists
if [ -n "$WEAVIATE_CONTAINER" ]; then
    echo -e "${YELLOW}Found Weaviate container: ${WEAVIATE_CONTAINER}${NC}"
    echo -e "${YELLOW}  → Clearing Weaviate data...${NC}"
    
    # Delete the SemanticCache collection if it exists
    docker exec "${WEAVIATE_CONTAINER}" sh -c \
        'curl -s -X DELETE http://localhost:8080/v1/schema/SemanticCache 2>/dev/null || true' || true
    
    echo -e "${GREEN}✓ Cleared Weaviate data${NC}"
    echo -e "${YELLOW}  → Note: Weaviate persistence volume may still contain data.${NC}"
    echo -e "${YELLOW}  → To fully clear, remove volume: docker volume rm boardy_weaviate_data${NC}"
fi

# Option to clear Docker volumes completely
if [ -n "$REDIS_CONTAINER" ] || [ -n "$WEAVIATE_CONTAINER" ]; then
    echo ""
    echo -e "${YELLOW}To completely remove all persisted data (including volumes), run:${NC}"
    echo -e "  docker compose down -v"
    echo -e "  # This will remove redis_data and weaviate_data volumes"
fi

echo ""
echo -e "${GREEN}✓ Cache clearing complete!${NC}"
echo -e "${YELLOW}⚠ If cache still appears after queries, check:${NC}"
echo -e "  1. Redis persistence files were deleted (check container: /data/)"
echo -e "  2. Weaviate data was cleared (if USE_WEAVIATE=true)"
echo -e "  3. Restart containers to ensure clean state: docker compose restart"
