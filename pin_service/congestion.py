"""Congestion-aware re-ranking.

Pin selection on its own is myopic: it answers "what's the best curb for
*this* rider, right now?" without considering that 19 other riders just
asked the same question 10 seconds ago. Without congestion control the
service produces hotspots — every car in a metro converges on the same
3 curbs near a stadium exit, and the entire fleet enters a doom loop.

This module maintains a sliding-window assignment counter per H3 cell.
When a cell's assignments-in-window exceed a threshold, we subtract a
penalty from its score so that the re-ranker prefers nearby alternatives.
This is the simplest credible form of demand-control / load-shaping.

Thread-safety: the gRPC server runs a thread-pool executor. The
assignment counter is guarded by a single `threading.Lock`. For Waymo-
scale traffic, replace with a sharded, lock-free LRU keyed by cell id.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

import numpy as np


class CongestionTracker:
    """Sliding-window assignment counter per H3 cell.

    All times are in seconds (float, monotonic-clock).

    Args:
        window_seconds: Width of the sliding window.
        threshold: Soft cap on assignments per cell per window before a
            penalty is applied.
        penalty: Subtracted from the candidate score when a cell is over
            threshold. Tuned so that a single "hot" cell falls below a
            cool neighbor in expected score.
        load_shed_ratio: If the global assignment rate exceeds this
            multiple of the threshold (summed across cells), the service
            sheds load by failing requests fast. This is the demand-
            control fail-safe.
    """

    def __init__(
        self,
        window_seconds: float = 60.0,
        threshold: int = 3,
        penalty: float = 0.25,
        load_shed_ratio: float = 50.0,
    ) -> None:
        self.window_seconds = window_seconds
        self.threshold = threshold
        self.penalty = penalty
        self.load_shed_ratio = load_shed_ratio
        self._lock = threading.Lock()
        self._assignments: dict[str, deque] = defaultdict(deque)

    def _evict(self, cell: str, now: float) -> None:
        """Drop timestamps that have aged out of the window."""
        q = self._assignments[cell]
        cutoff = now - self.window_seconds
        while q and q[0] < cutoff:
            q.popleft()

    def record_assignment(self, cell: str, now: float | None = None) -> None:
        """Mark that we just assigned a pin in this H3 cell."""
        now = now if now is not None else time.monotonic()
        with self._lock:
            self._evict(cell, now)
            self._assignments[cell].append(now)

    def penalties_for(
        self, cells: list[str], now: float | None = None
    ) -> np.ndarray:
        """Return a penalty vector aligned with `cells`."""
        now = now if now is not None else time.monotonic()
        out = np.zeros(len(cells), dtype=np.float32)
        with self._lock:
            for i, cell in enumerate(cells):
                self._evict(cell, now)
                if len(self._assignments[cell]) > self.threshold:
                    out[i] = self.penalty
        return out

    def should_load_shed(self, now: float | None = None) -> bool:
        """Return True if global load exceeds the shed ratio.

        A simple but effective backpressure signal: if the total
        in-window assignments across all cells exceeds
        `threshold * load_shed_ratio`, we refuse new requests rather
        than degrade latency for everyone.
        """
        now = now if now is not None else time.monotonic()
        global_cap = self.threshold * self.load_shed_ratio
        with self._lock:
            total = 0
            for cell, q in list(self._assignments.items()):
                self._evict(cell, now)
                total += len(q)
            return total > global_cap
