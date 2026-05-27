"""Prometheus metrics for the pin service.

We expose four families of metrics:

  pin_requests_total{status}       — request volume, broken down by status
  pin_latency_seconds              — server-side latency histogram
  pin_candidates_considered        — raw candidate count per request
  pin_candidates_feasible          — count surviving hard-constraint filter

These are scraped on port 9090 (configurable via env var). Grafana
dashboards in `docker/grafana/dashboards/` provide a default p50/p95/p99
view per status code.
"""

from __future__ import annotations

import os

from prometheus_client import Counter, Histogram, start_http_server


_METRICS_PORT = int(os.environ.get("PIN_METRICS_PORT", "9090"))


REQUESTS = Counter(
    "pin_requests_total",
    "Total pin selection requests, partitioned by terminal status.",
    labelnames=("status",),
)

LATENCY = Histogram(
    "pin_latency_seconds",
    "End-to-end pin selection latency, server side.",
    # Buckets tuned to a ~200ms p99 budget.
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.2, 0.5, 1.0),
)

CANDIDATES_CONSIDERED = Histogram(
    "pin_candidates_considered",
    "Number of candidates generated per request.",
    buckets=(5, 10, 20, 50, 100, 200),
)

CANDIDATES_FEASIBLE = Histogram(
    "pin_candidates_feasible",
    "Number of candidates surviving the hard-constraint filter.",
    buckets=(0, 1, 5, 10, 20, 50, 100),
)


def start_metrics_server() -> None:
    """Start the Prometheus scrape endpoint on a side port."""
    start_http_server(_METRICS_PORT)
