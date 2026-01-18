Use the attached PDF strictly as the authoritative source of requirements.
Do not restate the PDF verbatim.
Follow the scoped instructions below even if the PDF suggests optional extensions.

# Cursor One-Shot Prompt  
## Semantic Caching Take-Home Assessment (Boardy AI)

You are a **senior backend engineer** building a **production-ready but intentionally scoped** semantic caching system for an AI service.

This is a **take-home assessment**, not a research project.
Favor clarity, correctness, and explainability over completeness or novelty.

---

## Objective

Implement a **semantic caching API** that reduces redundant LLM calls by detecting **semantically similar queries** and returning cached responses when appropriate.

The final product must be:
- Working
- Demoable
- Explainable
- Containerized with Docker Compose
- Exposed at `http://localhost:3000`

Do **NOT** over-engineer.

---

## Locked Tech Stack (do not change)

### Language & Framework
- **Python 3.10+**
- **FastAPI**

### Cache
- **Redis** (via Docker Compose)
- TTL-based eviction only

### Embeddings (REQUIRED – real model)
- **OpenAI `text-embedding-3-small`**
- Cache embeddings to avoid re-computation
- Embedding calls must be minimal and efficient

### LLM (REQUIRED – real model, low cost)
- **OpenAI `gpt-4o-mini`**
- Use short, deterministic prompts
- Add a hard safety cap on total LLM calls

### Similarity
- **Cosine similarity**
- Default threshold: `0.85`
- Threshold must be configurable via environment variable

---

## Cost & Safety Constraints (IMPORTANT)

- Total expected cost must stay under **$2**
- Add a configurable max LLM call limit (e.g. `MAX_LLM_CALLS`)
- If the limit is reached:
  - Fail gracefully
  - Return a clear fallback response
  - Do NOT crash the server

---

## Functional Requirements

### API

Implement:

POST /api/query

### Request body

```json
{
  "query": "What's the weather like in New York today?",
  "forceRefresh": false
}
```

### Response body

```json
{
  "response": "The weather in New York today is sunny...",
  "metadata": {
    "source": "cache",
    "similarity": 0.87
  }
}
```

---

## Semantic Caching Behavior

### Query Flow

1. Receive query  
2. Generate or retrieve cached embedding  
3. Search Redis for semantically similar entries  
4. Compute cosine similarity  
5. If similarity ≥ threshold AND entry not expired AND forceRefresh=false:  
   - Return cached response  
6. Otherwise:  
   - Call LLM  
   - Cache response + embedding + TTL  
   - Return LLM response  

---

## Time-Sensitive Queries

Implement **simple heuristic-based detection**.

Time-sensitive keywords:
- today
- now
- current
- weather
- news
- price
- score

Behavior:
- If query contains any keyword → **time-sensitive**
  - Assign **short TTL** (5–15 minutes)
- Otherwise → **evergreen**
  - Assign **long TTL** (hours or days)

Do **NOT** implement ML classification.

---

## Cache Design

Each cached entry must store:
- query_text
- embedding
- response
- created_at
- ttl_seconds

Use Redis TTL for expiration.

---

## Logging & Metadata

Log:
- Cache hits vs misses
- Similarity scores
- LLM call count
- Query type (time-sensitive vs evergreen)

Expose in API response metadata:
- `source: cache | llm`
- `similarity` (if from cache)

---

## Project Structure

```
/app
  /api
    routes.py
  /cache
    semantic_cache.py
  /llm
    openai_client.py
  /utils
    similarity.py
    query_classification.py
  main.py
Dockerfile
docker-compose.yml
.env.example
README.md
```

---

## Docker Requirements

- `docker compose up --build` must work
- API exposed at **localhost:3000**
- Redis included as a service
- No credentials committed
- `.env.example` included with:
  - OPENAI_API_KEY
  - SIMILARITY_THRESHOLD
  - MAX_LLM_CALLS

---

## README Requirements

Generate a **clear, concise README** explaining:
1. System overview
2. Architecture diagram (ASCII acceptable)
3. Semantic similarity approach
4. Caching strategy & TTL logic
5. Cost control strategy
6. Tradeoffs (accuracy vs cost vs latency)
7. Scaling discussion
8. How to run locally

Write as if reviewed by a **senior staff engineer**.

---

## Constraints & Guidance

- Favor readability over abstraction
- Avoid unnecessary layers
- Keep file count reasonable
- Optimize for a 5–10 minute demo
- Do NOT implement optional extensions unless trivial

---

## Deliverable

Generate:
- Complete, runnable codebase
- Docker configuration
- README
- Graceful failure behavior

Proceed step-by-step and ensure correctness before adding polish.

---

## Final Reminder

This project is evaluated on:
- Engineering judgment
- Cost-awareness
- Explainability
- Practical system design

**Do NOT over-engineer.**
