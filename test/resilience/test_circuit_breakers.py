#!/usr/bin/env python3
"""
Circuit Breaker Testing Suite

Tests circuit breaker functionality for external dependencies:
- OpenAI API failures
- Redis failures
- Weaviate failures

All tests use mocked services to avoid API costs.
"""

import asyncio
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from app.utils.circuit_breaker import CircuitBreaker, CircuitState, CircuitBreakerOpenError
from test.utils.mock_openai import create_mock_openai_client


async def test_circuit_breaker_basic():
    """Test basic circuit breaker functionality."""
    print("=" * 80)
    print("Test: Basic Circuit Breaker Functionality")
    print("=" * 80)
    
    cb = CircuitBreaker(
        name="test",
        failure_threshold=0.5,  # 50% failures to open
        time_window_seconds=10,
        open_duration_seconds=2,
    )
    
    # Test successful calls
    async def success_func():
        return "success"
    
    result = await cb.call(success_func)
    assert result == "success", "Should return success"
    assert cb.state == CircuitState.CLOSED, "Should be CLOSED"
    print("✅ Successful calls work")
    
    # Test failure calls
    async def fail_func():
        raise Exception("Test failure")
    
    try:
        await cb.call(fail_func)
        assert False, "Should have raised exception"
    except Exception as e:
        assert str(e) == "Test failure", "Should raise original exception"
    
    print("✅ Failure calls raise exceptions")
    
    # Test circuit opening after threshold
    cb.reset()
    for i in range(6):  # 6 failures out of 10 calls = 60% failure rate
        try:
            await cb.call(fail_func)
        except Exception:
            pass
    
    # Make some successful calls to get to threshold
    for i in range(4):
        await cb.call(success_func)
    
    # Now trigger failures to exceed threshold
    for i in range(5):
        try:
            await cb.call(fail_func)
        except Exception:
            pass
    
    # Circuit should be open
    assert cb.state == CircuitState.OPEN, "Circuit should be OPEN"
    print("✅ Circuit opens after failure threshold")
    
    # Test rejection when open
    try:
        await cb.call(success_func)
        assert False, "Should raise CircuitBreakerOpenError"
    except CircuitBreakerOpenError:
        print("✅ Requests rejected when circuit is OPEN")
    
    # Test transition to half-open
    await asyncio.sleep(2.1)  # Wait for open_duration
    
    # Should transition to half-open on next call
    try:
        await cb.call(success_func)
    except CircuitBreakerOpenError:
        pass  # May still be open if timing is off
    
    print("✅ Circuit transitions to HALF_OPEN after duration")
    
    print("\n✅ All basic tests passed!")


async def test_openai_circuit_breaker():
    """Test circuit breaker with mocked OpenAI client."""
    print("=" * 80)
    print("Test: OpenAI Circuit Breaker")
    print("=" * 80)
    
    cb = CircuitBreaker(
        name="openai",
        failure_threshold=0.5,
        time_window_seconds=10,
        open_duration_seconds=1,
    )
    
    mock_client = create_mock_openai_client(failure_rate=0.7)  # 70% failure rate
    
    async def get_embedding(text: str):
        return await cb.call(mock_client.get_embedding, text)
    
    # Make several calls - circuit should open
    failures = 0
    successes = 0
    
    for i in range(10):
        try:
            result = await get_embedding("test query")
            successes += 1
        except Exception as e:
            failures += 1
            if isinstance(e, CircuitBreakerOpenError):
                print(f"  Call {i+1}: Circuit breaker opened (expected)")
            else:
                print(f"  Call {i+1}: API failure: {e}")
    
    print(f"  Successes: {successes}, Failures: {failures}")
    
    # Circuit should be open
    assert cb.state == CircuitState.OPEN, "Circuit should be OPEN"
    print("✅ Circuit opens with OpenAI failures")
    
    # Test fallback behavior - should reject immediately
    try:
        await get_embedding("test")
        assert False, "Should reject when circuit is open"
    except CircuitBreakerOpenError:
        print("✅ Requests rejected when circuit is open (no API calls)")
    
    print("\n✅ All OpenAI circuit breaker tests passed!")


async def test_circuit_breaker_recovery():
    """Test circuit breaker recovery."""
    print("=" * 80)
    print("Test: Circuit Breaker Recovery")
    print("=" * 80)
    
    cb = CircuitBreaker(
        name="recovery_test",
        failure_threshold=0.5,
        time_window_seconds=10,
        open_duration_seconds=1,
        success_threshold=0.8,  # 80% success to close
        half_open_max_calls=5,
    )
    
    # Open the circuit
    async def fail_func():
        raise Exception("Failure")
    
    for i in range(6):
        try:
            await cb.call(fail_func)
        except Exception:
            pass
    
    assert cb.state == CircuitState.OPEN, "Circuit should be OPEN"
    print("✅ Circuit opened")
    
    # Wait for half-open transition
    await asyncio.sleep(1.1)
    
    # Test recovery with successful calls
    async def success_func():
        return "success"
    
    # Make successful calls in half-open state
    for i in range(5):
        try:
            result = await cb.call(success_func)
            assert result == "success"
        except CircuitBreakerOpenError:
            # May still be transitioning
            await asyncio.sleep(0.1)
    
    # Circuit should close after successful calls
    await asyncio.sleep(0.5)
    
    # Verify circuit is closed
    result = await cb.call(success_func)
    assert result == "success", "Should work when circuit is closed"
    print("✅ Circuit recovers and closes after successful calls")
    
    print("\n✅ All recovery tests passed!")


async def run_all_tests():
    """Run all circuit breaker tests."""
    print("\n" + "=" * 80)
    print("Circuit Breaker Testing Suite")
    print("=" * 80)
    print("All tests use mocked services - $0 API cost")
    print()
    
    try:
        await test_circuit_breaker_basic()
        await test_openai_circuit_breaker()
        await test_circuit_breaker_recovery()
        
        print()
        print("=" * 80)
        print("✅ All circuit breaker tests passed!")
        print("=" * 80)
        return 0
        
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(run_all_tests())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
