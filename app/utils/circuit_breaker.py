#!/usr/bin/env python3
"""
Circuit Breaker Implementation

Provides circuit breaker pattern for external service calls to prevent
cascade failures and enable graceful degradation.
"""

import asyncio
import logging
import time
from enum import Enum
from typing import Callable, Optional, TypeVar, Any

logger = logging.getLogger(__name__)

T = TypeVar('T')


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"  # Normal operation, requests pass through
    OPEN = "open"  # Circuit is open, requests fail fast
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreaker:
    """
    Circuit breaker for external service calls.
    
    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Circuit is open, requests fail fast (no API calls)
    - HALF_OPEN: Testing if service recovered (limited requests allowed)
    
    Transitions:
    - CLOSED -> OPEN: When failure threshold exceeded
    - OPEN -> HALF_OPEN: After open_duration expires
    - HALF_OPEN -> CLOSED: When success threshold met
    - HALF_OPEN -> OPEN: When failures continue
    """
    
    def __init__(
        self,
        name: str,
        failure_threshold: float = 0.5,  # 50% failures to open
        time_window_seconds: int = 60,  # Rolling window for failure calculation
        open_duration_seconds: int = 30,  # How long circuit stays open
        success_threshold: float = 0.8,  # 80% success to close from half-open
        half_open_max_calls: int = 5,  # Max calls in half-open state
    ):
        """
        Initialize circuit breaker.
        
        Args:
            name: Name of the circuit breaker (for logging)
            failure_threshold: Percentage of failures to open circuit (0.0 to 1.0)
            time_window_seconds: Rolling window for failure calculation
            open_duration_seconds: How long circuit stays open before half-open
            success_threshold: Percentage of successes needed to close (0.0 to 1.0)
            half_open_max_calls: Maximum calls allowed in half-open state
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.time_window_seconds = time_window_seconds
        self.open_duration_seconds = open_duration_seconds
        self.success_threshold = success_threshold
        self.half_open_max_calls = half_open_max_calls
        
        self.state = CircuitState.CLOSED
        self.failure_history: list[tuple[float, bool]] = []  # (timestamp, is_failure)
        self.half_open_calls: list[bool] = []  # Track successes/failures in half-open
        self.opened_at: Optional[float] = None
        self._lock = asyncio.Lock()
        
        # Statistics
        self.total_calls = 0
        self.total_failures = 0
        self.total_rejected = 0
    
    async def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """
        Execute a function call through the circuit breaker.
        
        Args:
            func: Async function to call
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func
            
        Returns:
            Result from func
            
        Raises:
            CircuitBreakerOpenError: If circuit is open
            Exception: If func raises an exception
        """
        async with self._lock:
            self.total_calls += 1
            
            # Check circuit state
            if self.state == CircuitState.OPEN:
                # Check if we should transition to half-open
                if self.opened_at and (time.time() - self.opened_at) >= self.open_duration_seconds:
                    logger.info(f"Circuit breaker '{self.name}' transitioning to HALF_OPEN")
                    self.state = CircuitState.HALF_OPEN
                    self.half_open_calls = []
                else:
                    self.total_rejected += 1
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker '{self.name}' is OPEN. "
                        f"Opened {time.time() - (self.opened_at or 0):.1f}s ago. "
                        f"Will retry in {self.open_duration_seconds - (time.time() - (self.opened_at or 0)):.1f}s"
                    )
            
            elif self.state == CircuitState.HALF_OPEN:
                # Limit calls in half-open state
                if len(self.half_open_calls) >= self.half_open_max_calls:
                    self.total_rejected += 1
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker '{self.name}' is HALF_OPEN. "
                        f"Max calls ({self.half_open_max_calls}) reached. "
                        f"Transitioning back to OPEN."
                    )
            
            # Clean old history
            self._clean_history()
        
        # Execute the call
        is_failure = False
        try:
            result = await func(*args, **kwargs)
            
            # Record success
            async with self._lock:
                self._record_result(False)
            
            return result
            
        except Exception as e:
            is_failure = True
            async with self._lock:
                self.total_failures += 1
                self._record_result(True)
            
            # Re-raise the exception
            raise
    
    def _record_result(self, is_failure: bool):
        """Record a call result and update circuit state."""
        now = time.time()
        self.failure_history.append((now, is_failure))
        
        if self.state == CircuitState.HALF_OPEN:
            self.half_open_calls.append(not is_failure)  # True = success
            
            # Check if we should close or reopen
            if len(self.half_open_calls) >= self.half_open_max_calls:
                success_rate = sum(self.half_open_calls) / len(self.half_open_calls)
                
                if success_rate >= self.success_threshold:
                    logger.info(f"Circuit breaker '{self.name}' closing (success rate: {success_rate:.1%})")
                    self.state = CircuitState.CLOSED
                    self.opened_at = None
                    self.half_open_calls = []
                else:
                    logger.warning(f"Circuit breaker '{self.name}' reopening (success rate: {success_rate:.1%})")
                    self.state = CircuitState.OPEN
                    self.opened_at = now
                    self.half_open_calls = []
        
        elif self.state == CircuitState.CLOSED:
            # Check if we should open
            failure_rate = self._calculate_failure_rate()
            
            if failure_rate >= self.failure_threshold:
                logger.warning(
                    f"Circuit breaker '{self.name}' opening "
                    f"(failure rate: {failure_rate:.1%} >= {self.failure_threshold:.1%})"
                )
                self.state = CircuitState.OPEN
                self.opened_at = now
    
    def _calculate_failure_rate(self) -> float:
        """Calculate failure rate in the time window."""
        if not self.failure_history:
            return 0.0
        
        now = time.time()
        window_start = now - self.time_window_seconds
        
        # Filter to time window
        recent_history = [
            (ts, is_failure)
            for ts, is_failure in self.failure_history
            if ts >= window_start
        ]
        
        if not recent_history:
            return 0.0
        
        failures = sum(1 for _, is_failure in recent_history if is_failure)
        return failures / len(recent_history)
    
    def _clean_history(self):
        """Remove old history entries outside the time window."""
        now = time.time()
        window_start = now - self.time_window_seconds
        
        self.failure_history = [
            (ts, is_failure)
            for ts, is_failure in self.failure_history
            if ts >= window_start
        ]
    
    def get_stats(self) -> dict:
        """Get circuit breaker statistics."""
        return {
            "name": self.name,
            "state": self.state.value,
            "total_calls": self.total_calls,
            "total_failures": self.total_failures,
            "total_rejected": self.total_rejected,
            "failure_rate": self._calculate_failure_rate(),
            "opened_at": self.opened_at,
            "time_since_opened": time.time() - (self.opened_at or 0) if self.opened_at else None,
        }
    
    def reset(self):
        """Reset circuit breaker to CLOSED state (for testing)."""
        self.state = CircuitState.CLOSED
        self.failure_history = []
        self.half_open_calls = []
        self.opened_at = None
        self.total_calls = 0
        self.total_failures = 0
        self.total_rejected = 0


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open and request is rejected."""
    pass
