#!/bin/bash

# Script to inspect Redis data structure
# Shows what keys exist and their types/values

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Find Redis container
REDIS_CONTAINER=""
if command -v docker &> /dev/null; then
    REDIS_CONTAINER=$(docker ps --format '{{.Names}}' | grep -i redis | head -n 1)
fi

if [ -z "$REDIS_CONTAINER" ]; then
    echo -e "${RED}✗ Redis container not found. Is it running?${NC}"
    echo "Try: docker compose up -d redis"
    exit 1
fi

echo -e "${GREEN}✓ Found Redis container: ${REDIS_CONTAINER}${NC}\n"

# Redis CLI command helper
redis_cmd() {
    docker exec "${REDIS_CONTAINER}" redis-cli "$@"
}

# Get total key count
TOTAL_KEYS=$(redis_cmd DBSIZE)
echo -e "${CYAN}═══════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  Redis Data Inspection${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}Total Keys:${NC} ${TOTAL_KEYS}\n"

# Get all keys grouped by type
echo -e "${YELLOW}📊 Key Breakdown:${NC}\n"

# Cache entries
CACHE_ENTRIES=$(redis_cmd KEYS "cache:*" | wc -l | tr -d ' ')
echo -e "  ${GREEN}Cache Entries:${NC} ${CACHE_ENTRIES} (cache:*)"

# Embedding cache
EMBED_KEYS=$(redis_cmd KEYS "embed:*" | wc -l | tr -d ' ')
echo -e "  ${GREEN}Embedding Cache:${NC} ${EMBED_KEYS} (embed:*)"

# Statistics
STAT_KEYS=$(redis_cmd KEYS "stat:*" | wc -l | tr -d ' ')
echo -e "  ${GREEN}Statistics:${NC} ${STAT_KEYS} (stat:*)"

# Cache keys set
CACHE_KEYS_SET=$(redis_cmd EXISTS "cache_keys")
if [ "$CACHE_KEYS_SET" -eq 1 ]; then
    SET_SIZE=$(redis_cmd SCARD "cache_keys")
    echo -e "  ${GREEN}Cache Keys Set:${NC} ${SET_SIZE} entries (cache_keys)"
else
    echo -e "  ${GREEN}Cache Keys Set:${NC} 0 entries (not found)"
fi

# LLM call count
LLM_COUNT=$(redis_cmd GET "llm_call_count" 2>/dev/null || echo "0")
echo -e "  ${GREEN}LLM Call Count:${NC} ${LLM_COUNT}"

echo ""

# Show statistics
echo -e "${YELLOW}📈 Statistics:${NC}\n"
STATS=("stat:requests" "stat:cache_hits" "stat:cache_misses" "stat:llm_fallbacks")
for stat in "${STATS[@]}"; do
    VALUE=$(redis_cmd GET "$stat" 2>/dev/null || echo "0")
    echo -e "  ${BLUE}${stat}:${NC} ${VALUE}"
done

# Calculate hit rate
REQUESTS=$(redis_cmd GET "stat:requests" 2>/dev/null || echo "0")
HITS=$(redis_cmd GET "stat:cache_hits" 2>/dev/null || echo "0")
if [ "$REQUESTS" -gt 0 ]; then
    HIT_RATE=$(echo "scale=2; $HITS * 100 / $REQUESTS" | bc 2>/dev/null || echo "0")
    echo -e "  ${BLUE}Cache Hit Rate:${NC} ${HIT_RATE}%"
fi

echo ""

# Show sample cache entries
echo -e "${YELLOW}📝 Sample Cache Entries (first 3):${NC}\n"
CACHE_KEYS=$(redis_cmd KEYS "cache:*" | head -n 3)
if [ -z "$CACHE_KEYS" ]; then
    echo -e "  ${RED}No cache entries found${NC}\n"
else
    for key in $CACHE_KEYS; do
        echo -e "  ${CYAN}Key:${NC} ${key}"
        TTL=$(redis_cmd TTL "$key")
        if [ "$TTL" -gt 0 ]; then
            echo -e "    ${BLUE}TTL:${NC} ${TTL} seconds"
        else
            echo -e "    ${BLUE}TTL:${NC} expired"
        fi
        VALUE=$(redis_cmd GET "$key" | head -c 200)
        echo -e "    ${BLUE}Value (preview):${NC} ${VALUE}..."
        echo ""
    done
fi

# Show cache_keys set contents
if [ "$CACHE_KEYS_SET" -eq 1 ]; then
    SET_SIZE=$(redis_cmd SCARD "cache_keys")
    if [ "$SET_SIZE" -gt 0 ]; then
        echo -e "${YELLOW}🔑 Cache Keys Set Contents (first 5):${NC}\n"
        redis_cmd SMEMBERS "cache_keys" | head -n 5 | while read -r key; do
            echo -e "  ${CYAN}${key}${NC}"
        done
        if [ "$SET_SIZE" -gt 5 ]; then
            echo -e "  ${BLUE}... and $((SET_SIZE - 5)) more${NC}"
        fi
        echo ""
    fi
fi

# Show all keys (if requested)
if [ "$1" == "--all-keys" ]; then
    echo -e "${YELLOW}🔍 All Keys:${NC}\n"
    redis_cmd KEYS "*" | while read -r key; do
        TYPE=$(redis_cmd TYPE "$key")
        echo -e "  ${CYAN}${key}${NC} (${TYPE})"
    done
fi

echo -e "${CYAN}═══════════════════════════════════════════════════════${NC}"
