"""Execution latency logger for performance monitoring and validation."""

import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class LatencyMeasurement:
    """Single latency measurement."""
    
    operation: str
    latency_ms: float
    timestamp: datetime = field(default_factory=datetime.now)
    success: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LatencyStats:
    """Aggregated latency statistics."""
    
    operation: str
    count: int
    min_ms: float
    max_ms: float
    avg_ms: float
    median_ms: float
    p95_ms: float
    p99_ms: float
    std_dev_ms: float
    success_rate: float


class LatencyLogger:
    """
    Logs and analyzes execution latency for trading operations.
    
    Critical for validating bot performance before production:
    - Order placement latency
    - Market data fetch latency
    - WebSocket message latency
    - Full round-trip execution latency
    """
    
    def __init__(self, max_measurements: int = 10000) -> None:
        """
        Initialize latency logger.
        
        Args:
            max_measurements: Maximum measurements to keep in memory
        """
        self._measurements: list[LatencyMeasurement] = []
        self._max_measurements = max_measurements
        self._operation_counts: dict[str, int] = {}
        
        # Latency thresholds for warnings (ms)
        self.warning_thresholds = {
            "order_placement": 500,
            "market_fetch": 1000,
            "ws_message": 100,
            "full_execution": 2000,
            "api_call": 500,
        }
    
    def start_timer(self) -> float:
        """Start a timer and return the start time."""
        return time.perf_counter()
    
    def record(
        self,
        operation: str,
        start_time: float,
        success: bool = True,
        **metadata: Any,
    ) -> LatencyMeasurement:
        """
        Record a latency measurement.
        
        Args:
            operation: Name of the operation (e.g., 'order_placement')
            start_time: Start time from start_timer()
            success: Whether operation succeeded
            **metadata: Additional context
            
        Returns:
            The recorded measurement
        """
        latency_ms = (time.perf_counter() - start_time) * 1000
        
        measurement = LatencyMeasurement(
            operation=operation,
            latency_ms=latency_ms,
            success=success,
            metadata=metadata,
        )
        
        self._measurements.append(measurement)
        self._operation_counts[operation] = self._operation_counts.get(operation, 0) + 1
        
        # Trim if over limit
        if len(self._measurements) > self._max_measurements:
            self._measurements = self._measurements[-self._max_measurements:]
        
        # Check threshold warnings
        threshold = self.warning_thresholds.get(operation)
        if threshold and latency_ms > threshold:
            logger.warning(
                "High latency detected",
                operation=operation,
                latency_ms=round(latency_ms, 2),
                threshold_ms=threshold,
                **metadata,
            )
        else:
            logger.debug(
                "Latency recorded",
                operation=operation,
                latency_ms=round(latency_ms, 2),
                **metadata,
            )
        
        return measurement
    
    def record_direct(
        self,
        operation: str,
        latency_ms: float,
        success: bool = True,
        **metadata: Any,
    ) -> LatencyMeasurement:
        """Record a latency measurement with known latency value."""
        measurement = LatencyMeasurement(
            operation=operation,
            latency_ms=latency_ms,
            success=success,
            metadata=metadata,
        )
        
        self._measurements.append(measurement)
        self._operation_counts[operation] = self._operation_counts.get(operation, 0) + 1
        
        if len(self._measurements) > self._max_measurements:
            self._measurements = self._measurements[-self._max_measurements:]
        
        return measurement
    
    def get_stats(
        self,
        operation: str | None = None,
        since: datetime | None = None,
    ) -> LatencyStats | dict[str, LatencyStats]:
        """
        Get latency statistics.
        
        Args:
            operation: Specific operation or None for all
            since: Only include measurements after this time
            
        Returns:
            LatencyStats for specific operation or dict of all
        """
        if operation:
            return self._calculate_stats(operation, since)
        
        # Get stats for all operations
        operations = set(m.operation for m in self._measurements)
        return {op: self._calculate_stats(op, since) for op in operations}
    
    def _calculate_stats(
        self,
        operation: str,
        since: datetime | None = None,
    ) -> LatencyStats:
        """Calculate statistics for a specific operation."""
        measurements = [
            m for m in self._measurements
            if m.operation == operation
            and (since is None or m.timestamp >= since)
        ]
        
        if not measurements:
            return LatencyStats(
                operation=operation,
                count=0,
                min_ms=0,
                max_ms=0,
                avg_ms=0,
                median_ms=0,
                p95_ms=0,
                p99_ms=0,
                std_dev_ms=0,
                success_rate=0,
            )
        
        latencies = [m.latency_ms for m in measurements]
        successful = sum(1 for m in measurements if m.success)
        
        sorted_latencies = sorted(latencies)
        n = len(sorted_latencies)
        
        return LatencyStats(
            operation=operation,
            count=n,
            min_ms=round(min(latencies), 2),
            max_ms=round(max(latencies), 2),
            avg_ms=round(statistics.mean(latencies), 2),
            median_ms=round(statistics.median(latencies), 2),
            p95_ms=round(sorted_latencies[int(n * 0.95)] if n > 0 else 0, 2),
            p99_ms=round(sorted_latencies[int(n * 0.99)] if n > 0 else 0, 2),
            std_dev_ms=round(statistics.stdev(latencies), 2) if n > 1 else 0,
            success_rate=round(successful / n * 100, 2) if n > 0 else 0,
        )
    
    def get_recent_measurements(
        self,
        operation: str | None = None,
        limit: int = 100,
    ) -> list[LatencyMeasurement]:
        """Get recent measurements."""
        measurements = self._measurements
        
        if operation:
            measurements = [m for m in measurements if m.operation == operation]
        
        return measurements[-limit:]
    
    def get_hourly_breakdown(
        self,
        operation: str,
        hours: int = 24,
    ) -> list[dict[str, Any]]:
        """Get hourly latency breakdown for analysis."""
        now = datetime.now()
        breakdown = []
        
        for h in range(hours):
            start = now - timedelta(hours=h + 1)
            end = now - timedelta(hours=h)
            
            measurements = [
                m for m in self._measurements
                if m.operation == operation
                and start <= m.timestamp < end
            ]
            
            if measurements:
                latencies = [m.latency_ms for m in measurements]
                breakdown.append({
                    "hour": end.strftime("%H:00"),
                    "count": len(measurements),
                    "avg_ms": round(statistics.mean(latencies), 2),
                    "max_ms": round(max(latencies), 2),
                })
            else:
                breakdown.append({
                    "hour": end.strftime("%H:00"),
                    "count": 0,
                    "avg_ms": 0,
                    "max_ms": 0,
                })
        
        return list(reversed(breakdown))
    
    def generate_report(self) -> dict[str, Any]:
        """Generate comprehensive latency report."""
        all_stats = self.get_stats()
        
        report = {
            "generated_at": datetime.now().isoformat(),
            "total_measurements": len(self._measurements),
            "operations": {},
            "alerts": [],
        }
        
        for op, stats in all_stats.items():
            report["operations"][op] = {
                "count": stats.count,
                "avg_ms": stats.avg_ms,
                "p95_ms": stats.p95_ms,
                "p99_ms": stats.p99_ms,
                "success_rate": stats.success_rate,
            }
            
            # Add alerts for poor performance
            threshold = self.warning_thresholds.get(op)
            if threshold and stats.p95_ms > threshold:
                report["alerts"].append({
                    "operation": op,
                    "issue": "p95_latency_high",
                    "value_ms": stats.p95_ms,
                    "threshold_ms": threshold,
                })
            
            if stats.success_rate < 95:
                report["alerts"].append({
                    "operation": op,
                    "issue": "low_success_rate",
                    "value": stats.success_rate,
                    "threshold": 95,
                })
        
        return report
    
    def clear(self, before: datetime | None = None) -> int:
        """
        Clear measurements.
        
        Args:
            before: Only clear measurements before this time
            
        Returns:
            Number of measurements cleared
        """
        if before is None:
            count = len(self._measurements)
            self._measurements.clear()
            self._operation_counts.clear()
            return count
        
        original_count = len(self._measurements)
        self._measurements = [m for m in self._measurements if m.timestamp >= before]
        return original_count - len(self._measurements)


# Global latency logger instance
_latency_logger: LatencyLogger | None = None


def get_latency_logger() -> LatencyLogger:
    """Get global latency logger instance."""
    global _latency_logger
    if _latency_logger is None:
        _latency_logger = LatencyLogger()
    return _latency_logger
