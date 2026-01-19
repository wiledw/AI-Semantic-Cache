from __future__ import annotations

import asyncio
import logging
from typing import Optional

from openai import AsyncOpenAI
from redis.asyncio import Redis as AsyncRedis


logger = logging.getLogger(__name__)


class OpenAIClient:
    def __init__(
        self,
        api_key: str,
        max_llm_calls: int,
        redis_client: Optional[AsyncRedis],
        system_prompt: str,
        fallback_response: str,
        embedding_model: str = "text-embedding-3-small",
        chat_model: str = "gpt-4o-mini",
        max_batch_size: int = 2048,
        max_parallel_llm_calls: int = 10,
        enable_web_search: bool = False,
    ) -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._max_llm_calls = max_llm_calls
        self._redis = redis_client
        self._system_prompt = system_prompt
        self._fallback_response = fallback_response
        self._embedding_model = embedding_model
        self._chat_model = chat_model
        self._max_batch_size = max_batch_size
        self._max_parallel_llm_calls = max_parallel_llm_calls
        self._enable_web_search = enable_web_search
        self._llm_semaphore = asyncio.Semaphore(max_parallel_llm_calls)
        
        # If web search is enabled, use search-preview model variant
        # Note: These models may require API access approval
        if enable_web_search:
            if chat_model == "gpt-4o":
                self._effective_chat_model = "gpt-4o-search-preview"
            elif chat_model == "gpt-4o-mini":
                self._effective_chat_model = "gpt-4o-mini-search-preview"
            else:
                # For other models, keep original model name
                # Search-preview variants may not exist for all models
                self._effective_chat_model = chat_model
                logger.warning(
                    "Web search enabled but model %s may not have a search-preview variant. "
                    "Using original model. Web search may not be available.",
                    chat_model,
                )
        else:
            self._effective_chat_model = chat_model

    async def get_embedding(self, text: str) -> list[float]:
        response = await self._client.embeddings.create(
            model=self._embedding_model,
            input=text,
        )
        return list(response.data[0].embedding)

    async def get_embeddings_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts in a single batch API call.
        
        This is more efficient than parallel calls since OpenAI optimizes batch processing.
        Uses OpenAI's native batch support which accepts multiple inputs in one request.
        
        Args:
            texts: List of texts to generate embeddings for
            
        Returns:
            List of embedding vectors, one per input text
            
        Raises:
            Exception: If the batch API call fails
        """
        if not texts:
            return []
        
        # OpenAI allows up to 2048 inputs per batch, but we'll respect max_batch_size
        batch_size = min(len(texts), self._max_batch_size)
        texts_to_process = texts[:batch_size]
        
        if len(texts) > batch_size:
            logger.warning(
                "Batch size (%d) exceeds max_batch_size (%d). Processing first %d texts.",
                len(texts),
                self._max_batch_size,
                batch_size,
            )
        
        max_retries = 3
        base_delay = 1.0
        
        for attempt in range(max_retries):
            try:
                response = await self._client.embeddings.create(
                    model=self._embedding_model,
                    input=texts_to_process,
                )
                # Extract embeddings in order
                embeddings = [list(item.embedding) for item in response.data]
                logger.info("Generated %d embeddings in batch", len(embeddings))
                return embeddings
            except Exception as exc:
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(
                        "Batch embedding attempt %d/%d failed: %s. Retrying in %.1fs...",
                        attempt + 1,
                        max_retries,
                        exc,
                        delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error("Batch embedding failed after %d attempts: %s", max_retries, exc)
                    raise

    async def get_embeddings_parallel(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts using parallel async calls.
        
        Useful when you need results immediately and can't wait for batch processing.
        Each text is processed in a separate API call, but calls are made concurrently.
        
        Args:
            texts: List of texts to generate embeddings for
            
        Returns:
            List of embedding vectors, one per input text
        """
        if not texts:
            return []
        
        async def get_single_embedding(text: str) -> list[float]:
            max_retries = 3
            base_delay = 0.5
            
            for attempt in range(max_retries):
                try:
                    return await self.get_embedding(text)
                except Exception as exc:
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(
                            "Embedding attempt %d/%d failed for text (length: %d): %s. Retrying in %.1fs...",
                            attempt + 1,
                            max_retries,
                            len(text),
                            exc,
                            delay,
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error("Embedding failed after %d attempts: %s", max_retries, exc)
                        raise
        
        embeddings = await asyncio.gather(*[get_single_embedding(text) for text in texts])
        logger.info("Generated %d embeddings in parallel", len(embeddings))
        return embeddings

    async def get_completion(self, query: str) -> tuple[str, bool]:
        if not await self._can_make_llm_call():
            logger.warning("LLM call limit reached. Returning fallback response.")
            return self._fallback_response, False

        # Use search-preview model if web search is enabled
        # These models automatically use web search when needed for time-sensitive queries
        model_to_use = self._effective_chat_model if self._enable_web_search else self._chat_model
        
        if self._enable_web_search:
            logger.info("Web search enabled (using %s) for query: %s", model_to_use, query[:50])

        try:
            # Build request parameters
            # Search-preview models may not support all parameters (e.g., temperature)
            request_params = {
                "model": model_to_use,
                "messages": [
                    {"role": "system", "content": self._system_prompt},
                    {"role": "user", "content": query},
                ],
            }
            
            # Only include temperature for non-search-preview models
            # Search-preview models don't support temperature parameter
            if "search-preview" not in model_to_use:
                request_params["temperature"] = 0
            
            response = await self._client.chat.completions.create(**request_params)
        except Exception as exc:
            # If search-preview model fails (e.g., not available or parameter error), fall back to regular model
            if self._enable_web_search and "gpt-4o" in model_to_use and "search-preview" in model_to_use:
                logger.warning(
                    "Search-preview model %s failed (may not be available or parameter incompatibility). Falling back to %s. Error: %s",
                    model_to_use,
                    self._chat_model,
                    exc,
                )
                # Retry with regular model (which supports temperature)
                response = await self._client.chat.completions.create(
                    model=self._chat_model,
                    temperature=0,
                    messages=[
                        {"role": "system", "content": self._system_prompt},
                        {"role": "user", "content": query},
                    ],
                )
            else:
                raise
        message = response.choices[0].message.content or ""
        return message.strip(), True

    async def get_completions_batch(self, queries: list[str]) -> list[tuple[str, bool]]:
        """Generate completions for multiple queries using parallel async calls.
        
        Uses asyncio.gather() to make multiple LLM calls concurrently, respecting
        rate limits via semaphore and max_llm_calls limit.
        
        Args:
            queries: List of query strings to generate completions for
            
        Returns:
            List of (response, used_llm) tuples, one per query
        """
        if not queries:
            return []
        
        async def get_single_completion(query: str) -> tuple[str, bool]:
            """Get completion for a single query with semaphore-based rate limiting."""
            async with self._llm_semaphore:
                max_retries = 3
                base_delay = 1.0
                
                for attempt in range(max_retries):
                    try:
                        return await self.get_completion(query)
                    except Exception as exc:
                        if attempt < max_retries - 1:
                            delay = base_delay * (2 ** attempt)
                            logger.warning(
                                "LLM completion attempt %d/%d failed for query (length: %d): %s. Retrying in %.1fs...",
                                attempt + 1,
                                max_retries,
                                len(query),
                                exc,
                                delay,
                            )
                            await asyncio.sleep(delay)
                        else:
                            logger.error("LLM completion failed after %d attempts: %s", max_retries, exc)
                            # Return fallback response on final failure
                            return self._fallback_response, False
        
        results = await asyncio.gather(*[get_single_completion(query) for query in queries])
        logger.info("Generated %d completions in parallel", len(results))
        return results

    @property
    def chat_model(self) -> str:
        return self._chat_model
    
    @property
    def embedding_model(self) -> str:
        return self._embedding_model

    async def _can_make_llm_call(self) -> bool:
        if self._max_llm_calls <= 0:
            return False
        if self._redis is None:
            return True
        try:
            # Check current count BEFORE incrementing to avoid race conditions
            current_count_str = await self._redis.get("llm_call_count")
            current_count = int(current_count_str) if current_count_str else 0
            if current_count >= self._max_llm_calls:
                logger.warning("LLM call limit reached: %s/%s", current_count, self._max_llm_calls)
                return False
            
            # Only increment if we're going to make the call
            count = await self._redis.incr("llm_call_count")
            logger.info("LLM call count incremented to %s", count)
            return True
        except Exception as exc:  # pragma: no cover - redis failure fallback
            logger.warning("Failed to read LLM call count: %s", exc)
            return True
