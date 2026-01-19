#!/usr/bin/env python3
"""
API Cost Tracker for Testing

Tracks API costs during test execution to stay within budget constraints.
Estimates costs based on OpenAI pricing and warns when approaching limits.
"""

import json
import os
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional


# OpenAI pricing (per 1K tokens, approximate)
EMBEDDING_PRICING = {
    "text-embedding-3-small": 0.00002,  # $0.02 per 1M tokens
    "text-embedding-3-large": 0.00013,  # $0.13 per 1M tokens
    "text-embedding-ada-002": 0.0001,   # $0.10 per 1M tokens
}

# LLM pricing (approximate per call, varies by model and tokens)
LLM_PRICING = {
    "gpt-4o-mini": 0.01,  # ~$0.01 per call (estimated)
    "gpt-4o": 0.05,       # ~$0.05 per call (estimated)
    "gpt-4o-search-preview": 0.05,
    "gpt-4o-mini-search-preview": 0.01,
}

# Default budget
DEFAULT_BUDGET = 5.0


@dataclass
class CostEntry:
    """Single cost entry."""
    timestamp: str
    test_suite: str
    operation: str  # 'embedding', 'llm_call', etc.
    model: str
    cost: float
    tokens: Optional[int] = None
    details: Optional[str] = None


@dataclass
class CostSummary:
    """Summary of costs."""
    total_cost: float
    budget: float
    remaining: float
    entries: list[CostEntry]
    by_suite: dict[str, float]
    by_operation: dict[str, float]


class CostTracker:
    """Tracks API costs during test execution."""
    
    def __init__(self, budget: float = DEFAULT_BUDGET, log_file: Optional[str] = None):
        """
        Initialize cost tracker.
        
        Args:
            budget: Total budget in dollars
            log_file: Optional path to log file for cost entries
        """
        self.budget = budget
        self.total_cost = 0.0
        self.entries: list[CostEntry] = []
        self.log_file = log_file
        self._warned_at = set()  # Track which thresholds we've warned at
        
        # Create log directory if needed
        if self.log_file:
            log_path = Path(self.log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
    
    def estimate_embedding_cost(self, model: str, num_tokens: int) -> float:
        """
        Estimate cost for embedding generation.
        
        Args:
            model: Embedding model name
            num_tokens: Number of tokens (approximate)
            
        Returns:
            Estimated cost in dollars
        """
        price_per_1k = EMBEDDING_PRICING.get(model, EMBEDDING_PRICING["text-embedding-3-small"])
        return (num_tokens / 1000.0) * price_per_1k
    
    def estimate_llm_cost(self, model: str, num_tokens: Optional[int] = None) -> float:
        """
        Estimate cost for LLM call.
        
        Args:
            model: LLM model name
            num_tokens: Optional number of tokens (if None, uses default estimate)
            
        Returns:
            Estimated cost in dollars
        """
        # Use per-call estimate if available
        if model in LLM_PRICING:
            return LLM_PRICING[model]
        
        # Fallback: estimate based on tokens (rough approximation)
        if num_tokens:
            # Rough estimate: $0.01 per 1K tokens for most models
            return (num_tokens / 1000.0) * 0.01
        
        # Default estimate
        return 0.01
    
    def record_embedding(self, model: str, num_tokens: int, test_suite: str = "unknown") -> float:
        """
        Record an embedding API call.
        
        Args:
            model: Embedding model name
            num_tokens: Number of tokens (approximate)
            test_suite: Name of test suite
            
        Returns:
            Cost in dollars
        """
        cost = self.estimate_embedding_cost(model, num_tokens)
        self._record_cost(
            operation="embedding",
            model=model,
            cost=cost,
            test_suite=test_suite,
            tokens=num_tokens,
        )
        return cost
    
    def record_llm_call(self, model: str, test_suite: str = "unknown", num_tokens: Optional[int] = None) -> float:
        """
        Record an LLM API call.
        
        Args:
            model: LLM model name
            test_suite: Name of test suite
            num_tokens: Optional number of tokens
            
        Returns:
            Cost in dollars
        """
        cost = self.estimate_llm_cost(model, num_tokens)
        self._record_cost(
            operation="llm_call",
            model=model,
            cost=cost,
            test_suite=test_suite,
            tokens=num_tokens,
        )
        return cost
    
    def _record_cost(self, operation: str, model: str, cost: float, test_suite: str, 
                     tokens: Optional[int] = None, details: Optional[str] = None):
        """Internal method to record a cost entry."""
        entry = CostEntry(
            timestamp=datetime.now().isoformat(),
            test_suite=test_suite,
            operation=operation,
            model=model,
            cost=cost,
            tokens=tokens,
            details=details,
        )
        
        self.entries.append(entry)
        self.total_cost += cost
        
        # Log to file if specified
        if self.log_file:
            self._write_log_entry(entry)
        
        # Check budget and warn if needed
        self._check_budget()
    
    def _write_log_entry(self, entry: CostEntry):
        """Write entry to log file."""
        try:
            with open(self.log_file, "a") as f:
                f.write(json.dumps(asdict(entry)) + "\n")
        except Exception as e:
            print(f"Warning: Failed to write cost log entry: {e}")
    
    def _check_budget(self):
        """Check if we're approaching budget limits and warn."""
        if self.budget <= 0:
            return
        
        percentage = (self.total_cost / self.budget) * 100
        remaining = self.budget - self.total_cost
        
        # Warn at thresholds
        thresholds = [80, 90, 95, 100]
        for threshold in thresholds:
            if percentage >= threshold and threshold not in self._warned_at:
                self._warned_at.add(threshold)
                if threshold == 100:
                    print(f"\n⚠️  CRITICAL: Budget exceeded! Total cost: ${self.total_cost:.4f}")
                    raise BudgetExceededError(f"Budget of ${self.budget:.2f} exceeded. Total cost: ${self.total_cost:.4f}")
                else:
                    print(f"\n⚠️  Budget Warning: {threshold}% used (${self.total_cost:.4f} / ${self.budget:.2f}). Remaining: ${remaining:.4f}")
    
    def get_summary(self) -> CostSummary:
        """
        Get cost summary.
        
        Returns:
            CostSummary object
        """
        by_suite: dict[str, float] = {}
        by_operation: dict[str, float] = {}
        
        for entry in self.entries:
            by_suite[entry.test_suite] = by_suite.get(entry.test_suite, 0.0) + entry.cost
            by_operation[entry.operation] = by_operation.get(entry.operation, 0.0) + entry.cost
        
        return CostSummary(
            total_cost=self.total_cost,
            budget=self.budget,
            remaining=self.budget - self.total_cost,
            entries=self.entries.copy(),
            by_suite=by_suite,
            by_operation=by_operation,
        )
    
    def print_summary(self):
        """Print cost summary to console."""
        summary = self.get_summary()
        
        print("\n" + "=" * 80)
        print("API Cost Summary")
        print("=" * 80)
        print(f"Total Cost: ${summary.total_cost:.4f}")
        print(f"Budget: ${summary.budget:.2f}")
        print(f"Remaining: ${summary.remaining:.4f}")
        print(f"Usage: {(summary.total_cost / summary.budget * 100):.1f}%")
        print()
        
        if summary.by_suite:
            print("Cost by Test Suite:")
            for suite, cost in sorted(summary.by_suite.items(), key=lambda x: x[1], reverse=True):
                print(f"  {suite}: ${cost:.4f}")
            print()
        
        if summary.by_operation:
            print("Cost by Operation:")
            for op, cost in sorted(summary.by_operation.items(), key=lambda x: x[1], reverse=True):
                print(f"  {op}: ${cost:.4f}")
            print()
        
        print("=" * 80)
    
    def save_report(self, filepath: str):
        """
        Save cost report to JSON file.
        
        Args:
            filepath: Path to save report
        """
        summary = self.get_summary()
        report = {
            "timestamp": datetime.now().isoformat(),
            "summary": asdict(summary),
        }
        
        report_path = Path(filepath)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)
        
        print(f"Cost report saved to: {report_path}")


class BudgetExceededError(Exception):
    """Raised when budget is exceeded."""
    pass


# Global tracker instance (can be imported and used across tests)
_global_tracker: Optional[CostTracker] = None


def get_tracker(budget: Optional[float] = None) -> CostTracker:
    """
    Get or create global cost tracker.
    
    Args:
        budget: Optional budget override (uses DEFAULT_BUDGET if None)
        
    Returns:
        CostTracker instance
    """
    global _global_tracker
    
    if _global_tracker is None:
        budget_value = budget if budget is not None else float(os.getenv("API_BUDGET", DEFAULT_BUDGET))
        log_file = os.getenv("COST_LOG_FILE", "test/results/cost_log.jsonl")
        _global_tracker = CostTracker(budget=budget_value, log_file=log_file)
    
    return _global_tracker


def reset_tracker():
    """Reset global tracker (useful for test isolation)."""
    global _global_tracker
    _global_tracker = None
