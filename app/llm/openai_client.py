from __future__ import annotations

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
    ) -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._max_llm_calls = max_llm_calls
        self._redis = redis_client
        self._system_prompt = system_prompt
        self._fallback_response = fallback_response
        self._embedding_model = embedding_model
        self._chat_model = chat_model

    async def get_embedding(self, text: str) -> list[float]:
        response = await self._client.embeddings.create(
            model=self._embedding_model,
            input=text,
        )
        return list(response.data[0].embedding)

    async def get_completion(self, query: str) -> tuple[str, bool]:
        if not await self._can_make_llm_call():
            logger.warning("LLM call limit reached. Returning fallback response.")
            return self._fallback_response, False

        response = await self._client.chat.completions.create(
            model=self._chat_model,
            temperature=0,
            messages=[
                {"role": "system", "content": self._system_prompt},
                {"role": "user", "content": query},
            ],
        )
        message = response.choices[0].message.content or ""
        return message.strip(), True

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
