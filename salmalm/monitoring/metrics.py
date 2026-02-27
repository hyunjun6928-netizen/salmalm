"""Prometheus-compatible metrics exporter (stdlib only — no prometheus_client dep).

Implements Prometheus text format 0.0.4.
"""
from __future__ import annotations

import math
import threading
from collections import defaultdict
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Metric types
# ---------------------------------------------------------------------------

class Counter:
    """Monotonically increasing counter."""

    _type = "counter"

    def __init__(self, name: str, help: str, labels: Tuple[str, ...] = ()):
        self.name = name
        self.help = help
        self.labels = labels
        self._values: Dict[tuple, float] = defaultdict(float)
        self._lock = threading.Lock()

    def inc(self, value: float = 1, **label_vals) -> None:
        key = tuple(label_vals.get(l, "") for l in self.labels)
        with self._lock:
            self._values[key] += value

    def collect(self) -> List[Tuple[dict, float]]:
        with self._lock:
            return [(dict(zip(self.labels, k)), v) for k, v in self._values.items()]


class Gauge:
    """Arbitrary value gauge (can go up or down)."""

    _type = "gauge"

    def __init__(self, name: str, help: str, labels: Tuple[str, ...] = ()):
        self.name = name
        self.help = help
        self.labels = labels
        self._values: Dict[tuple, float] = defaultdict(float)
        self._lock = threading.Lock()

    def set(self, value: float, **label_vals) -> None:
        key = tuple(label_vals.get(l, "") for l in self.labels)
        with self._lock:
            self._values[key] = value

    def inc(self, value: float = 1, **label_vals) -> None:
        key = tuple(label_vals.get(l, "") for l in self.labels)
        with self._lock:
            self._values[key] += value

    def dec(self, value: float = 1, **label_vals) -> None:
        self.inc(-value, **label_vals)

    def collect(self) -> List[Tuple[dict, float]]:
        with self._lock:
            return [(dict(zip(self.labels, k)), v) for k, v in self._values.items()]


_DEFAULT_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)


class Histogram:
    """Histogram with configurable buckets, per-label-set."""

    _type = "histogram"

    def __init__(
        self,
        name: str,
        help: str,
        labels: Tuple[str, ...] = (),
        buckets: Tuple[float, ...] = _DEFAULT_BUCKETS,
    ):
        self.name = name
        self.help = help
        self.labels = labels
        self.buckets = tuple(sorted(buckets))
        self._lock = threading.Lock()
        # key → (bucket_counts list, sum, count)
        self._data: Dict[tuple, list] = {}

    def _key(self, label_vals: dict) -> tuple:
        return tuple(label_vals.get(l, "") for l in self.labels)

    def _init_key(self, key: tuple):
        if key not in self._data:
            # bucket_counts[i] = cumulative count for bucket i (le = buckets[i])
            self._data[key] = [[0] * len(self.buckets), 0.0, 0]

    def observe(self, value: float, **label_vals) -> None:
        key = self._key(label_vals)
        with self._lock:
            self._init_key(key)
            bucket_counts, total_sum, count = self._data[key]
            for i, bound in enumerate(self.buckets):
                if value <= bound:
                    bucket_counts[i] += 1
            self._data[key][1] = total_sum + value
            self._data[key][2] = count + 1

    def collect(self) -> List[Tuple[dict, list, float, int]]:
        """Returns list of (labels_dict, cumulative_bucket_counts, sum, count)."""
        with self._lock:
            result = []
            for key, (bucket_counts, total_sum, count) in self._data.items():
                result.append((
                    dict(zip(self.labels, key)),
                    list(bucket_counts),
                    total_sum,
                    count,
                ))
            return result


# ---------------------------------------------------------------------------
# Registry & rendering
# ---------------------------------------------------------------------------

def _label_str(labels: dict) -> str:
    if not labels:
        return ""
    parts = [f'{k}="{v}"' for k, v in labels.items()]
    return "{" + ",".join(parts) + "}"


class MetricsRegistry:
    def __init__(self):
        self._metrics: list = []

    def register(self, m):
        self._metrics.append(m)
        return m

    def render_text(self) -> str:
        """Render all metrics in Prometheus text format 0.0.4."""
        lines: List[str] = []
        for m in self._metrics:
            lines.append(f"# HELP {m.name} {m.help}")
            lines.append(f"# TYPE {m.name} {m._type}")

            if isinstance(m, Histogram):
                for labels_dict, bucket_counts, total_sum, count in m.collect():
                    # bucket_counts[i] is already cumulative (observe increments all le>=value)
                    for i, bound in enumerate(m.buckets):
                        label_str = _label_str({**labels_dict, "le": str(bound)})
                        lines.append(f"{m.name}_bucket{label_str} {bucket_counts[i]}")
                    # +Inf bucket = total count
                    inf_labels = _label_str({**labels_dict, "le": "+Inf"})
                    lines.append(f"{m.name}_bucket{inf_labels} {count}")
                    base_labels = _label_str(labels_dict)
                    lines.append(f"{m.name}_sum{base_labels} {total_sum}")
                    lines.append(f"{m.name}_count{base_labels} {count}")
            else:
                for labels_dict, value in m.collect():
                    label_str = _label_str(labels_dict)
                    lines.append(f"{m.name}{label_str} {value}")

        return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Global registry & metric definitions
# ---------------------------------------------------------------------------

metrics = MetricsRegistry()

requests_total = metrics.register(
    Counter("salmalm_requests_total", "Total HTTP requests", ("method", "path", "status"))
)
request_duration = metrics.register(
    Histogram("salmalm_request_duration_seconds", "HTTP request latency seconds", ("method",))
)
llm_calls_total = metrics.register(
    Counter("salmalm_llm_calls_total", "Total LLM API calls", ("provider", "model", "status"))
)
llm_call_duration = metrics.register(
    Histogram("salmalm_llm_call_duration_seconds", "LLM call latency seconds")
)
active_sessions = metrics.register(
    Gauge("salmalm_active_sessions", "Active in-memory session count")
)
token_usage_total = metrics.register(
    Counter("salmalm_token_usage_total", "Token usage total", ("provider", "type"))
)
