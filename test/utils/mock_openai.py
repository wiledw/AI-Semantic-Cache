#!/usr/bin/env python3
"""
Mock OpenAI Client for Testing

Provides a mock OpenAI client that returns realistic responses without making
actual API calls. Useful for testing failure scenarios and avoiding API costs.
"""

import asyncio
import random
from typing import Optional
from unittest.mock import AsyncMock, MagicMock


class MockOpenAIClient:
    """Mock OpenAI client for testing."""
    
    def __init__(self, failure_rate: float = 0.0, delay_ms: int = 0):
        """
        Initialize mock OpenAI client.
        
        Args:
            failure_rate: Probability of failure (0.0 to 1.0)
            delay_ms: Artificial delay in milliseconds
        """
        self.failure_rate = failure_rate
        self.delay_ms = delay_ms
        self.call_count = 0
        self.failure_count = 0
        
        # Pre-computed embeddings for common queries (1536 dimensions for text-embedding-3-small)
        self._embedding_cache: dict[str, list[float]] = {}
        
        # Pre-computed responses for common queries
        self._response_cache: dict[str, str] = {}
    
    async def _delay(self):
        """Apply artificial delay if configured."""
        if self.delay_ms > 0:
            await asyncio.sleep(self.delay_ms / 1000.0)
    
    async def _should_fail(self) -> bool:
        """Determine if this call should fail."""
        if self.failure_rate <= 0:
            return False
        
        self.call_count += 1
        if random.random() < self.failure_rate:
            self.failure_count += 1
            return True
        return False
    
    def _generate_embedding(self, text: str) -> list[float]:
        """
        Generate a mock embedding vector.
        
        Args:
            text: Input text
            
        Returns:
            Mock embedding vector (1536 dimensions)
        """
        # Check cache first
        if text in self._embedding_cache:
            return self._embedding_cache[text]
        
        # Generate deterministic embedding based on text hash
        # This ensures same text produces same embedding
        import hashlib
        hash_obj = hashlib.md5(text.encode())
        seed = int(hash_obj.hexdigest()[:8], 16)
        random.seed(seed)
        
        # Generate 1536-dimensional vector (text-embedding-3-small)
        embedding = [random.random() * 2 - 1 for _ in range(1536)]
        
        # Normalize to unit vector (for cosine similarity)
        norm = sum(x * x for x in embedding) ** 0.5
        embedding = [x / norm for x in embedding]
        
        self._embedding_cache[text] = embedding
        return embedding
    
    def _generate_response(self, query: str) -> str:
        """
        Generate a mock LLM response.
        
        Args:
            query: User query
            
        Returns:
            Mock response
        """
        # Check cache first
        if query in self._response_cache:
            return self._response_cache[query]
        
        # Generate deterministic response based on query
        # Simple template-based responses for common patterns
        query_lower = query.lower()
        
        if "weather" in query_lower:
            response = "The weather today is sunny with a temperature of 72°F."
        elif "password" in query_lower or "reset" in query_lower:
            response = "To reset your password, go to Settings > Security > Password Reset."
        elif "news" in query_lower:
            response = "Here are the latest news headlines: [Mock news content]"
        elif "price" in query_lower:
            response = "The current price is $100.00 (mock data)."
        elif "python" in query_lower or "code" in query_lower:
            response = "Python is a high-level programming language. Here's how to get started: [Mock tutorial]"
        else:
            response = f"This is a mock response to: {query}"
        
        self._response_cache[query] = response
        return response
    
    async def get_embedding(self, text: str) -> list[float]:
        """
        Get embedding for text (mocked).
        
        Args:
            text: Input text
            
        Returns:
            Mock embedding vector
            
        Raises:
            Exception: If failure_rate triggers a failure
        """
        await self._delay()
        
        if await self._should_fail():
            raise Exception("Mock OpenAI API failure: Rate limit exceeded")
        
        return self._generate_embedding(text)
    
    async def get_embeddings_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Get embeddings for multiple texts (mocked).
        
        Args:
            texts: List of input texts
            
        Returns:
            List of mock embedding vectors
            
        Raises:
            Exception: If failure_rate triggers a failure
        """
        await self._delay()
        
        if await self._should_fail():
            raise Exception("Mock OpenAI API failure: Rate limit exceeded")
        
        return [self._generate_embedding(text) for text in texts]
    
    async def get_completion(self, query: str) -> tuple[str, bool]:
        """
        Get LLM completion (mocked).
        
        Args:
            query: User query
            
        Returns:
            Tuple of (response, used_llm)
            
        Raises:
            Exception: If failure_rate triggers a failure
        """
        await self._delay()
        
        if await self._should_fail():
            raise Exception("Mock OpenAI API failure: Service unavailable")
        
        response = self._generate_response(query)
        return response, True
    
    async def get_completions_batch(self, queries: list[str]) -> list[tuple[str, bool]]:
        """
        Get completions for multiple queries (mocked).
        
        Args:
            queries: List of user queries
            
        Returns:
            List of tuples (response, used_llm)
            
        Raises:
            Exception: If failure_rate triggers a failure
        """
        await self._delay()
        
        if await self._should_fail():
            raise Exception("Mock OpenAI API failure: Service unavailable")
        
        return [await self.get_completion(query) for query in queries]
    
    def get_stats(self) -> dict:
        """
        Get mock client statistics.
        
        Returns:
            Dictionary with call counts and failure counts
        """
        return {
            "call_count": self.call_count,
            "failure_count": self.failure_count,
            "failure_rate": self.failure_rate,
            "cached_embeddings": len(self._embedding_cache),
            "cached_responses": len(self._response_cache),
        }


def create_mock_openai_client(failure_rate: float = 0.0, delay_ms: int = 0) -> MockOpenAIClient:
    """
    Create a mock OpenAI client.
    
    Args:
        failure_rate: Probability of failure (0.0 to 1.0)
        delay_ms: Artificial delay in milliseconds
        
    Returns:
        MockOpenAIClient instance
    """
    return MockOpenAIClient(failure_rate=failure_rate, delay_ms=delay_ms)
