import threading
from typing import Dict, Any, Optional
from collections import defaultdict

class MetricsRegistry:
    def __init__(self):
        self._lock = threading.Lock()
        self._counters: Dict[str, int] = defaultdict(int)
        self._gauges: Dict[str, float] = {}
        self._latency_sums: Dict[str, float] = defaultdict(float)
        self._latency_counts: Dict[str, int] = defaultdict(int)

    def increment(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self._counters[name] += amount

    def set_gauge(self, name: str, value: float) -> None:
        with self._lock:
            self._gauges[name] = value

    def record_latency(self, name: str, duration_ms: float) -> None:
        with self._lock:
            self._latency_sums[name] += duration_ms
            self._latency_counts[name] += 1

    def get_counter(self, name: str) -> int:
        with self._lock:
            return self._counters.get(name, 0)

    def get_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            avg_latencies = {}
            for name, total in self._latency_sums.items():
                count = self._latency_counts[name]
                avg_latencies[name] = round(total / count, 2) if count > 0 else 0.0

            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "average_latencies_ms": avg_latencies
            }

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._latency_sums.clear()
            self._latency_counts.clear()

# Global default metrics registry
default_metrics = MetricsRegistry()
