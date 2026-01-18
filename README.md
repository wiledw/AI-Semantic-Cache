# Boardy Semantic Cache Service

## System Overview

This service provides a semantic caching layer for an AI-powered query API. It
uses OpenAI embeddings to identify semantically similar queries and serves cached
responses from Redis when similarity is above a configurable threshold. If no
cache hit exists (or `forceRefresh=true`), it calls the LLM, caches the result,
and returns the response.

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
Redis (responses + embeddings + TTL)
```

## Semantic Similarity Approach

- Embeddings: OpenAI `text-embedding-3-small`
- Similarity: cosine similarity across embedding vectors
- Threshold: configurable via `SIMILARITY_THRESHOLD` (default `0.85`)

If the best cached entry is above the threshold and not expired, the cached
response is returned.

## Caching Strategy & TTL Logic

- Cache entries include `query_text`, `embedding`, `response`, `created_at`,
  `ttl_seconds`.
- Time-sensitive queries are detected via keywords:
  `today`, `now`, `current`, `weather`, `news`, `price`, `score`.
- Time-sensitive TTL defaults to 10 minutes.
- Evergreen TTL defaults to 24 hours.

## Cost Control Strategy

- Embeddings are cached by normalized query to minimize repeat calls.
- LLM calls are capped via `MAX_LLM_CALLS`. Once the limit is reached, the API
  returns a graceful fallback response without crashing.
- Estimated cost tracking uses `LLM_COST_PER_CALL` (default `$0.01`).

## Tradeoffs (Accuracy vs Cost vs Latency)

- Lower thresholds improve hit rate but increase risk of mismatched responses.
- Higher thresholds reduce false positives but incur more LLM calls and cost.
- Linear scan of cached keys is simple and correct for small scale, but slower
  at large scale.

## Scaling Discussion

- For higher throughput, replace the linear scan with a vector index (e.g. Redis
  vector search or an external vector DB).
- Move LLM call counter to a centralized metrics store for visibility.
- Add request-level caching and batching if traffic grows.

## How to Run Locally

1. Copy `.env.example` to `.env` and set `OPENAI_API_KEY`.
2. Run:
   ```
   docker compose up --build
   ```
3. API is available at `http://localhost:3000`.
4. UI is available at `http://localhost:5173`.

### Example Request

```
POST http://localhost:3000/api/query
{
  "query": "What's the weather like in New York today?",
  "forceRefresh": false
}
```

## UI Usage

Open `http://localhost:5173` and submit a query. The UI displays:
- The response body
- `source` (cache or model name)
- `similarity` when applicable

## Stats Endpoint

`GET /api/stats` returns live counters and cost estimates:
- request count, cache hits/misses, hit rate
- LLM call count + fallback count
- estimated LLM spend and savings

### Example Response

```
{
  "response": "The weather in New York today is sunny...",
  "metadata": {
    "source": "cache",
    "similarity": 0.87
  }
}
```
