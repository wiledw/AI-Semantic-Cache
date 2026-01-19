# Boardy Semantic Cache Service

## System Overview

<img width="1526" height="1700" alt="image" src="https://github.com/user-attachments/assets/25de4bff-6ec8-4dc1-8c0c-0405ba985bd5" />

This service provides a semantic caching layer for an AI-powered query API. It uses OpenAI embeddings to identify semantically similar queries and serves cached responses from Redis when similarity is above a configurable threshold. If no cache hit exists (or `forceRefresh=true`), it calls the LLM, caches the result, and returns the response.

## Features

- **Semantic Caching**: Uses cosine similarity on embeddings to match semantically similar queries
- **Structured Logging**: JSON-formatted logs with severity levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- **Metrics Collection**: Time-series metrics tracking cache performance (hit rate, latency, request volume)
- **Real-time Visualization**: Interactive charts showing cache performance over time
- **Cost Tracking**: Estimates LLM costs and cache savings
- **Dual Storage**: Supports Redis (default) and optional Weaviate vector database
- **Request-level Caching**: Fast exact-match cache before semantic search
- **TTL Management**: Automatic expiration based on query type (time-sensitive vs evergreen)

## Architecture Diagram

```
Client
  |
  v
FastAPI (/api/query)
  | \
  |  \-> OpenAI LLM (gpt-4o-mini)
  v
Semantic Cache
  | \
  |  \-> OpenAI Embeddings (text-embedding-3-small)
  v
Redis (responses + embeddings + metrics + TTL)
  |
  +-> Optional: Weaviate (vector search)
```

## Semantic Similarity Approach

- **Embeddings**: OpenAI `text-embedding-3-small` (configurable)
- **Similarity**: Cosine similarity across embedding vectors
- **Threshold**: Configurable via `SIMILARITY_THRESHOLD` (default `0.85`)
- **Preprocessing**: Enhanced query normalization for better cache matching

If the best cached entry is above the threshold and not expired, the cached response is returned.

## Caching Strategy & TTL Logic

- Cache entries include `query_text`, `embedding`, `response`, `created_at`, `ttl_seconds`.
- **Time-sensitive queries** are detected via keywords: `today`, `now`, `current`, `weather`, `news`, `price`, `score`.
- **Time-sensitive TTL**: Default 10 minutes (`SHORT_TTL_SECONDS`)
- **Evergreen TTL**: Default 24 hours (`LONG_TTL_SECONDS`)
- **Embedding cache TTL**: Default 7 days (`EMBEDDING_CACHE_TTL_SECONDS`)

## Cost Control Strategy

- Embeddings are cached by normalized query to minimize repeat calls.
- LLM calls are capped via `MAX_LLM_CALLS`. Once the limit is reached, the API returns a graceful fallback response without crashing.
- Estimated cost tracking uses `LLM_COST_PER_CALL` (default `$0.01`).
- Real-time cost and savings metrics displayed in UI.

## How to Run Locally

### Prerequisites

- Docker and Docker Compose installed
- OpenAI API key

### Setup

1. Copy `.env.example` to `.env` and set `OPENAI_API_KEY`:
   ```bash
   cp .env.example .env
   # Edit .env and add your OPENAI_API_KEY
   ```

2. Start all services:
   ```bash
   docker compose up --build
   ```

3. Access the services:
   - **API**: `http://localhost:3000`
   - **UI**: `http://localhost:5173`
   - **Redis**: `localhost:6379`
   - **Weaviate** (if enabled): `localhost:8080`

### Environment Variables

Key configuration options in `.env`:

- `OPENAI_API_KEY`: Your OpenAI API key (required)
- `SIMILARITY_THRESHOLD`: Similarity threshold for cache matching (default: `0.85`)
- `MAX_LLM_CALLS`: Maximum LLM calls allowed (default: `100`)
- `USE_WEAVIATE`: Enable Weaviate vector database (default: `false`)
- `LOG_LEVEL`: Logging level - DEBUG, INFO, WARNING, ERROR, CRITICAL (default: `INFO`)
- `USE_JSON_LOGGING`: Use JSON format for logs (default: `true`)
- `LLM_COST_PER_CALL`: Cost per LLM call for estimates (default: `0.01`)

## API Endpoints

### Query Endpoint

```bash
POST http://localhost:3000/api/query
Content-Type: application/json

{
  "query": "What's the weather like in New York today?",
  "forceRefresh": false,
  "similarityThreshold": 0.85,  # Optional: override default threshold
  "embeddingModel": "text-embedding-3-small"  # Optional: override embedding model
}
```

**Response:**
```json
{
  "response": "The weather in New York today is sunny...",
  "metadata": {
    "source": "cache",
    "similarity": 0.87
  }
}
```

### Stats Endpoint

```bash
GET http://localhost:3000/api/stats
```

Returns live counters and cost estimates:
- `requests`: Total number of requests
- `cache_hits`: Number of cache hits
- `cache_misses`: Number of cache misses
- `cache_hit_rate`: Hit rate percentage
- `llm_calls`: Total LLM API calls made
- `llm_fallbacks`: Number of fallback responses
- `estimated_llm_cost`: Estimated cost of LLM calls
- `estimated_cache_savings`: Estimated savings from cache hits

### Metrics Endpoint

```bash
GET http://localhost:3000/api/metrics?hours=1&interval_seconds=10
```

Returns time-series metrics data:
- `data`: Array of aggregated metrics per time interval
  - `timestamp`: ISO timestamp
  - `requests`: Requests in this interval
  - `hits`: Cache hits in this interval
  - `misses`: Cache misses in this interval
  - `hit_rate`: Hit rate for this interval
  - `avg_latency_ms`: Average latency in milliseconds
  - `cumulative_requests`: Total requests up to this point
  - `cumulative_hits`: Total hits up to this point
  - `cumulative_hit_rate`: Overall hit rate up to this point
- `current_stats`: Current aggregate statistics

**Query Parameters:**
- `hours`: Number of hours of data to retrieve (default: `1`)
- `interval_seconds`: Aggregation interval in seconds (default: `10`)

## UI Features

The web interface at `http://localhost:5173` provides:

1. **Query Interface**: Submit queries and see responses
2. **Live Stats Dashboard**: Real-time statistics including:
   - Request counts
   - Cache hits/misses
   - Hit rate percentage
   - LLM calls and fallbacks
   - Estimated costs and savings
3. **Performance Visualization**: Interactive chart showing:
   - Cumulative hit rate over time
   - Total requests over time
   - Summary statistics (average latency, overall hit rate)
4. **Response Metadata**: Shows source (cache vs LLM) and similarity scores

## Shell Scripts

The project includes several shell scripts for common tasks. To run them:

### Making Scripts Executable

First, ensure scripts have execute permissions:

```bash
chmod +x clear_redis.sh
chmod +x inspect_redis.sh
chmod +x test/metrics/test_metrics.sh
chmod +x test/similarityThresholds/run_threshold_tests.sh
```

### Available Scripts

#### `clear_redis.sh`

Clears all Redis data including persistence files and optionally clears Weaviate data.

```bash
./clear_redis.sh
```

**What it does:**
- Flushes all Redis keys from memory
- Deletes Redis persistence files (`dump.rdb`, `appendonly.aof`)
- Clears Weaviate data (if enabled)
- Provides instructions for complete cleanup

**Note**: This script handles Redis persistence properly. After running it, restart containers to ensure a clean state:
```bash
docker compose restart redis
```

#### `inspect_redis.sh`

Inspects Redis data structure and shows statistics.

```bash
./inspect_redis.sh
./inspect_redis.sh --all-keys  # Show all keys
```

**What it shows:**
- Total key count
- Breakdown by type (cache entries, embeddings, statistics)
- Current statistics (requests, hits, misses, hit rate)
- Sample cache entries with TTL information

#### `test/metrics/test_metrics.sh`

Generates test data for metrics visualization.

```bash
./test/metrics/test_metrics.sh
```

**What it does:**
- Sends multiple queries to generate cache hits and misses
- Helps populate the performance visualization chart
- Useful for testing cache behavior

**Customization:**
```bash
API_URL=http://localhost:3000/api/query ./test/metrics/test_metrics.sh
```

#### `test/similarityThresholds/run_threshold_tests.sh`

Runs similarity threshold testing suite.

```bash
cd test/similarityThresholds
./run_threshold_tests.sh
./run_threshold_tests.sh --model text-embedding-3-large
```

**What it does:**
- Tests different similarity thresholds
- Compares embedding models
- Generates comparison reports and visualizations

See `test/similarityThresholds/README.md` for detailed usage.

## Logging

### Structured Logging

The application uses structured JSON logging by default. Logs include:

- **Timestamp**: ISO 8601 format
- **Level**: DEBUG, INFO, WARNING, ERROR, CRITICAL
- **Severity**: Severity code
- **Logger**: Module name
- **Message**: Log message
- **Context Fields**: Additional context like `request_id`, `operation`, `latency_ms`, `similarity`, etc.

### Log Format Example

```json
{
  "timestamp": "2024-01-17T12:34:56.789Z",
  "level": "INFO",
  "severity": "INFO",
  "logger": "app.api.routes",
  "message": "Cache hit with similarity",
  "request_id": "req_1705496096789",
  "operation": "semantic_search",
  "hit": true,
  "similarity": 0.87,
  "latency_ms": 45.2
}
```

### Viewing Logs

```bash
# View API logs
docker compose logs -f api

# View logs in JSON format (default)
# Or set USE_JSON_LOGGING=false for standard format
```

### Configuring Logging

Set in `.env`:
- `LOG_LEVEL`: Set log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `USE_JSON_LOGGING`: Use JSON format (`true`) or standard format (`false`)

## Metrics & Monitoring

### Metrics Collection

The system automatically collects metrics for:
- Request counts (total, hits, misses)
- Latency measurements
- Hit rates (per interval and cumulative)
- Operation types (exact_match, semantic_search, etc.)

### Metrics Storage

- **Time-series data**: Stored in Redis sorted sets
- **Aggregate counters**: Stored as Redis keys
- **Retention**: Configurable (default: 24 hours)

### Accessing Metrics

1. **Via API**: `GET /api/metrics`
2. **Via UI**: Performance visualization chart
3. **Via Redis**: Direct inspection of metrics keys

## Testing

### Quick Test

```bash
# Generate test metrics data
./test/metrics/test_metrics.sh

# Or use Python test script
python3 test/metrics/test_metrics.py
```

### Threshold Testing

```bash
cd test/similarityThresholds
./run_threshold_tests.sh
```

See `test/similarityThresholds/README.md` for details.

### Manual Testing

1. Start the application: `docker compose up`
2. Open UI: `http://localhost:5173`
3. Send queries and observe:
   - Cache hits/misses
   - Hit rate trends in the chart
   - Cost and savings metrics

## Tradeoffs (Accuracy vs Cost vs Latency)

- **Lower thresholds**: Improve hit rate but increase risk of mismatched responses
- **Higher thresholds**: Reduce false positives but incur more LLM calls and cost
- **Linear scan**: Simple and correct for small scale, but slower at large scale
- **Weaviate**: Faster vector search but adds complexity and infrastructure

## Scaling Discussion

- For higher throughput, use Weaviate vector search (set `USE_WEAVIATE=true`)
- Move metrics to a dedicated time-series database (e.g., InfluxDB, TimescaleDB)
- Add request-level caching and batching if traffic grows
- Consider distributed caching for multi-instance deployments

## Troubleshooting

### Cache Not Clearing

If cache persists after running `clear_redis.sh`:

1. Check Redis persistence files:
   ```bash
   docker exec <redis-container> ls -la /data/
   ```

2. Restart Redis container:
   ```bash
   docker compose restart redis
   ```

3. For complete cleanup:
   ```bash
   docker compose down -v
   docker compose up -d
   ```

### Metrics Not Showing

1. Ensure metrics endpoint is accessible:
   ```bash
   curl http://localhost:3000/api/metrics
   ```

2. Check browser console for errors (F12 → Console)

3. Verify data exists in Redis:
   ```bash
   docker exec <redis-container> redis-cli ZRANGE metrics:timeseries 0 -1
   ```

### Logs Not Appearing

1. Check log level configuration in `.env`
2. Verify `USE_JSON_LOGGING` setting
3. Check Docker logs: `docker compose logs api`

## Documentation

- **Redis Data Structure**: See `REDIS_DATA_STRUCTURE.md`
- **Threshold Testing**: See `test/similarityThresholds/README.md`
- **Preprocessing**: See `test/preProcessing/PREPROCESSING_IMPROVEMENTS.md`
- **Testing Guide**: See `TESTING_GUIDE.md` (if exists)

## License

[Add your license here]
