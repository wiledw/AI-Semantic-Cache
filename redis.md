# Redis Data Structure Documentation

This document describes how data is stored in Redis for the semantic cache system.

## Overview

Redis is used to store:
1. **Cached query responses** (with embeddings)
2. **Cached embeddings** (to avoid regenerating them)
3. **Cache key index** (set of all cache entry keys)
4. **Statistics counters** (request counts, cache hits/misses, etc.)

---

## Data Structures

### 1. Cache Entries (String Keys)

**Key Pattern:** `cache:{sha256_hash_of_query}`

**Example:** `cache:a1b2c3d4e5f6...` (64-char hex hash)

**Value:** JSON string containing:
```json
{
  "query_text": "What's the weather in New York?",
  "embedding": [0.123, -0.456, 0.789, ...],  // Array of floats
  "response": "The weather in New York is...",
  "created_at": "2024-01-17T12:34:56.789Z",
  "ttl_seconds": 3600
}
```

**TTL:** Set based on query type:
- Time-sensitive queries: `short_ttl_seconds` (default: 600 = 10 minutes)
- Evergreen queries: `long_ttl_seconds` (default: 86400 = 24 hours)

**Storage Method:** `SET key value EX ttl_seconds`

**Location:** `semantic_cache.py:84`

---

### 2. Embedding Cache (String Keys)

**Key Pattern:** `embed:{model_name}:{sha256_hash_of_normalized_query}`

**Example:** `embed:text-embedding-3-small:a1b2c3d4e5f6...`

**Value:** JSON string containing array of floats:
```json
[0.123, -0.456, 0.789, ...]
```

**TTL:** `embedding_cache_ttl_seconds` (configurable, typically longer than response cache)

**Storage Method:** `SET key value EX ttl_seconds`

**Purpose:** Avoids regenerating embeddings for the same normalized query

**Location:** `semantic_cache.py:41-44`

**Note:** Query is normalized (lowercased, trimmed) before hashing to maximize cache hits.

---

### 3. Cache Keys Index (Set)

**Key:** `cache_keys`

**Type:** Redis Set

**Value:** Set of all cache entry keys (e.g., `{"cache:abc123...", "cache:def456...", ...}`)

**Purpose:** 
- Maintains a list of all cached responses for similarity search
- Used in `find_similar()` to iterate through all cached entries
- Automatically cleaned up when entries expire (see cleanup logic below)

**Operations:**
- **Add:** `SADD cache_keys cache:{hash}` when storing a new response
- **Remove:** `SREM cache_keys cache:{hash}` when entry expires (cleanup)
- **Read:** `SMEMBERS cache_keys` to get all keys for similarity search

**Location:** `semantic_cache.py:53, 85, 57`

**Cleanup:** When `find_similar()` encounters an expired key (returns `None`), it removes it from the set.

---

### 4. Statistics Counters (String Keys)

All statistics are stored as integer values using Redis string operations.

#### Request Statistics

**Key:** `stat:requests`
- **Type:** Integer (stored as string)
- **Operation:** `INCR stat:requests`
- **Purpose:** Total number of API requests
- **Location:** `routes.py:102`

**Key:** `stat:cache_hits`
- **Type:** Integer
- **Operation:** `INCR stat:cache_hits`
- **Purpose:** Number of cache hits
- **Location:** `routes.py:116`

**Key:** `stat:cache_misses`
- **Type:** Integer
- **Operation:** `INCR stat:cache_misses`
- **Purpose:** Number of cache misses
- **Location:** `routes.py:122, 124`

**Key:** `stat:llm_fallbacks`
- **Type:** Integer
- **Operation:** `INCR stat:llm_fallbacks`
- **Purpose:** Number of fallback responses (when LLM call limit reached)
- **Location:** `routes.py:135`

#### LLM Call Counter

**Key:** `llm_call_count`
- **Type:** Integer
- **Operation:** `INCR llm_call_count` (only when actually making LLM call)
- **Purpose:** Tracks total LLM API calls made (used for rate limiting)
- **Location:** `openai_client.py:66, 72`
- **Note:** Checked before incrementing to enforce `max_llm_calls` limit

---

## Data Flow

### Storing a New Response

1. Query comes in → normalized → hashed
2. Check embedding cache: `embed:{model}:{hash}`
   - If exists: use cached embedding
   - If not: generate embedding → store with TTL
3. Search for similar cached responses (iterate `cache_keys` set)
4. If no match above threshold:
   - Call LLM → get response
   - Store response: `SET cache:{hash} {json} EX ttl`
   - Add to index: `SADD cache_keys cache:{hash}`
5. Update stats: `INCR stat:requests`, `INCR stat:cache_misses`

### Retrieving a Cached Response

1. Query comes in → generate/get embedding
2. Iterate `cache_keys` set
3. For each key:
   - `GET cache:{key}` → parse JSON
   - Compute cosine similarity with query embedding
   - Track best match
4. If best similarity ≥ threshold:
   - Return cached response
   - Update stats: `INCR stat:cache_hits`
5. If entry expired (GET returns None):
   - Clean up: `SREM cache_keys {key}`

---

## Key Characteristics

### Expiration Behavior

- **Cache entries:** Expire automatically via Redis TTL
- **Embedding cache:** Expires automatically via Redis TTL
- **Cache keys set:** Entries removed manually when expired entries are detected
- **Statistics:** Never expire (persist indefinitely)

### Hash Function

- **Algorithm:** SHA-256
- **Input:** Query text (or normalized query for embeddings)
- **Output:** 64-character hexadecimal string
- **Location:** `semantic_cache.py:89-90`

### JSON Serialization

- All complex data (cache entries, embeddings) stored as JSON strings
- Redis client configured with `decode_responses=True` for automatic string decoding
- Manual `json.loads()` / `json.dumps()` for serialization

---

## Example Redis State

After processing a few queries, Redis might contain:

```
KEYS *
  cache:a1b2c3d4e5f6...  (string, TTL: 3600)
  cache:def456789abc...  (string, TTL: 600)
  embed:text-embedding-3-small:abc123...  (string, TTL: 86400)
  cache_keys  (set: {"cache:a1b2c3d4e5f6...", "cache:def456789abc..."})
  stat:requests  (string: "5")
  stat:cache_hits  (string: "2")
  stat:cache_misses  (string: "3")
  llm_call_count  (string: "3")
```

---

## Potential Issues & Improvements

### Current Limitations

1. **Linear Scan:** `find_similar()` scans all cache keys linearly - O(n) complexity
   - **Impact:** Slow for large cache sizes
   - **Solution:** Use Redis vector search or external vector DB

2. **Set Cleanup:** Expired keys only removed when encountered during search
   - **Impact:** `cache_keys` set may contain stale references
   - **Solution:** Periodic cleanup job or use Redis SCAN with TTL checks

3. **Statistics Persistence:** Stats never expire, could grow indefinitely
   - **Impact:** Memory usage (minimal for counters)
   - **Solution:** Optional TTL or periodic reset

### Data Consistency

- Cache entries and `cache_keys` set can become inconsistent if Redis crashes between operations
- Mitigated by cleanup logic in `find_similar()` that removes stale keys

---

## Commands for Inspection

### View all keys
```bash
docker exec <redis-container> redis-cli KEYS "*"
```

### View cache entry
```bash
docker exec <redis-container> redis-cli GET "cache:a1b2c3d4e5f6..."
```

### View cache keys set
```bash
docker exec <redis-container> redis-cli SMEMBERS "cache_keys"
```

### View statistics
```bash
docker exec <redis-container> redis-cli GET "stat:requests"
docker exec <redis-container> redis-cli GET "stat:cache_hits"
docker exec <redis-container> redis-cli GET "llm_call_count"
```

### Count total keys
```bash
docker exec <redis-container> redis-cli DBSIZE
```

### Clear all data
```bash
./clear_redis.sh
# or
docker exec <redis-container> redis-cli FLUSHALL
```
