from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Optional

from redis.asyncio import Redis as AsyncRedis


class MetricsCollector:
    """Collects and stores cache performance metrics over time."""
    
    def __init__(self, redis_client: AsyncRedis, retention_hours: int = 24):
        """Initialize metrics collector.
        
        Args:
            redis_client: Redis client for storing metrics
            retention_hours: Number of hours to retain metrics data (default: 24)
        """
        self._redis = redis_client
        self._retention_seconds = retention_hours * 3600
        self._metrics_key_prefix = "metrics:"
        self._time_series_key = "metrics:timeseries"
    
    async def record_request(
        self,
        is_hit: bool,
        latency_ms: float,
        similarity: Optional[float] = None,
        operation: str = "query",
    ) -> None:
        """Record a cache request metric.
        
        Args:
            is_hit: Whether the request was a cache hit
            latency_ms: Request latency in milliseconds
            similarity: Similarity score (if applicable)
            operation: Operation type (e.g., "query", "exact_match", "semantic_search")
        """
        timestamp = datetime.now(timezone.utc)
        timestamp_iso = timestamp.isoformat()
        timestamp_sec = int(timestamp.timestamp())
        
        # Create metric entry
        metric = {
            "timestamp": timestamp_iso,
            "timestamp_sec": timestamp_sec,
            "hit": 1 if is_hit else 0,
            "miss": 0 if is_hit else 1,
            "latency_ms": latency_ms,
            "operation": operation,
        }
        
        if similarity is not None:
            metric["similarity"] = similarity
        
        # Store in time-series sorted set (score = timestamp, value = JSON)
        metric_json = json.dumps(metric)
        await self._redis.zadd(
            self._time_series_key,
            {metric_json: timestamp_sec},
        )
        
        # Set expiration on the sorted set
        await self._redis.expire(self._time_series_key, self._retention_seconds)
        
        # Update aggregate counters
        await self._redis.incr("metrics:total_requests")
        if is_hit:
            await self._redis.incr("metrics:total_hits")
        else:
            await self._redis.incr("metrics:total_misses")
        
        # Track latency statistics
        await self._redis.lpush("metrics:latencies", latency_ms)
        # Keep only last 1000 latency measurements
        await self._redis.ltrim("metrics:latencies", 0, 999)
    
    async def get_time_series_data(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        interval_seconds: int = 10,
    ) -> list[dict]:
        """Get time-series metrics data aggregated by time intervals.
        
        Args:
            start_time: Start time for data retrieval (default: 1 hour ago)
            end_time: End time for data retrieval (default: now)
            interval_seconds: Aggregation interval in seconds (default: 60)
        
        Returns:
            List of aggregated metric entries
        """
        if end_time is None:
            end_time = datetime.now(timezone.utc)
        if start_time is None:
            # Default to 1 hour ago
            from datetime import timedelta
            start_time = end_time - timedelta(hours=1)
        
        start_sec = int(start_time.timestamp())
        end_sec = int(end_time.timestamp())
        
        # Get all metrics in the time range
        metrics_json = await self._redis.zrangebyscore(
            self._time_series_key,
            min=start_sec,
            max=end_sec,
        )
        
        # Parse and aggregate by interval
        aggregated: dict[int, dict] = {}
        
        for metric_json in metrics_json:
            try:
                metric = json.loads(metric_json)
                timestamp_sec = metric["timestamp_sec"]
                
                # Round to interval
                interval_start = (timestamp_sec // interval_seconds) * interval_seconds
                
                if interval_start not in aggregated:
                    aggregated[interval_start] = {
                        "timestamp": datetime.fromtimestamp(interval_start, tz=timezone.utc).isoformat(),
                        "timestamp_sec": interval_start,
                        "requests": 0,
                        "hits": 0,
                        "misses": 0,
                        "total_latency_ms": 0.0,
                        "avg_latency_ms": 0.0,
                        "hit_rate": 0.0,
                    }
                
                agg = aggregated[interval_start]
                agg["requests"] += 1
                agg["hits"] += metric.get("hit", 0)
                agg["misses"] += metric.get("miss", 0)
                agg["total_latency_ms"] += metric.get("latency_ms", 0.0)
            except (json.JSONDecodeError, KeyError, ValueError):
                # Skip invalid metric entries
                continue
        
        # Calculate averages, hit rates, and cumulative totals
        result = []
        cumulative_requests = 0
        cumulative_hits = 0
        cumulative_misses = 0
        
        for interval_start in sorted(aggregated.keys()):
            agg = aggregated[interval_start]
            
            # Only process intervals with requests
            if agg["requests"] > 0:
                agg["avg_latency_ms"] = agg["total_latency_ms"] / agg["requests"]
                agg["hit_rate"] = agg["hits"] / agg["requests"]
                
                # Calculate cumulative totals
                cumulative_requests += agg["requests"]
                cumulative_hits += agg["hits"]
                cumulative_misses += agg["misses"]
                
                # Always set cumulative fields
                agg["cumulative_requests"] = cumulative_requests
                agg["cumulative_hits"] = cumulative_hits
                agg["cumulative_misses"] = cumulative_misses
                agg["cumulative_hit_rate"] = cumulative_hits / cumulative_requests if cumulative_requests > 0 else 0.0
                
                # Remove intermediate field
                del agg["total_latency_ms"]
                
                # Only add intervals with requests to result
                result.append(agg)
        
        return result
    
    async def get_current_stats(self) -> dict:
        """Get current aggregate statistics.
        
        Returns:
            Dictionary with current stats
        """
        total_requests = int(await self._redis.get("metrics:total_requests") or 0)
        total_hits = int(await self._redis.get("metrics:total_hits") or 0)
        total_misses = int(await self._redis.get("metrics:total_misses") or 0)
        
        # Calculate average latency from recent measurements
        latencies = await self._redis.lrange("metrics:latencies", 0, 99)
        avg_latency = 0.0
        if latencies:
            try:
                latency_values = [float(l) for l in latencies]
                avg_latency = sum(latency_values) / len(latency_values)
            except (ValueError, TypeError):
                pass
        
        hit_rate = (total_hits / total_requests) if total_requests > 0 else 0.0
        
        return {
            "total_requests": total_requests,
            "total_hits": total_hits,
            "total_misses": total_misses,
            "hit_rate": hit_rate,
            "avg_latency_ms": avg_latency,
        }
    
    async def cleanup_old_metrics(self) -> int:
        """Remove metrics older than retention period.
        
        Returns:
            Number of metrics removed
        """
        cutoff_time = int((datetime.now(timezone.utc).timestamp()) - self._retention_seconds)
        removed = await self._redis.zremrangebyscore(
            self._time_series_key,
            min=0,
            max=cutoff_time,
        )
        return removed
