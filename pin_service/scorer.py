"""ML scoring for pin candidates.

We score each surviving candidate with a gradient-boosted regressor. The
model is trained offline (see `scripts/train_model.py`) and serialized to
`data/scorer.joblib`. The serving path loads it once at module import.

Features (4-d vector, ordered):
    walk_distance_m    — great-circle distance from rider to candidate
    hour_of_day        — 0..23, from the request timestamp
    historical_success — exponential-moving-average "good pin" rate at
                         this H3 cell, in [0, 1]
    local_supply       — count of idle AVs within 2 km

The label during training is a synthetic "rider satisfaction" score in
roughly [-2, 2]; in production this is bootstrapped from rider ratings,
actual wait time vs. promised, and the rate of rider pin edits.

Production note: at Waymo scale the inference path is wrapped in a C++
Triton or ONNX-Runtime serving layer. The Python sklearn version here is
the *logical* baseline; a follow-up commit ports it to ONNX and serves
from C++. We have parity tests in `tests/test_scorer.py` to make that
port a one-day task rather than a one-week task.
"""

from __future__ import annotations

import pathlib
import time
from dataclasses import dataclass

import h3
import joblib
import numpy as np

from pin_service.candidate_gen import PinCandidate


_DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / "data"
_MODEL_PATH = _DATA_DIR / "scorer.joblib"


@dataclass
class ScoringContext:
    """Per-request context passed into feature extraction."""

    rider_lat: float
    rider_lon: float
    timestamp_ms: int


# Lazy-loaded singleton. The first call to `score_candidates` loads the
# model from disk; subsequent calls reuse it. We keep this module-level
# (rather than a class field) so that the gRPC server's worker threads
# share the same model object.
_MODEL = None


def _load_model():
    global _MODEL
    if _MODEL is None:
        if not _MODEL_PATH.exists():
            raise FileNotFoundError(
                f"Scoring model not found at {_MODEL_PATH}. "
                f"Run `python scripts/train_model.py` first."
            )
        _MODEL = joblib.load(_MODEL_PATH)
    return _MODEL


def _historical_success_stub(h3_cell: str) -> float:
    """Stub for the historical-success feature lookup.

    Production: this is a feature-store call (e.g. Feast, Tecton) keyed
    on h3_cell with a few-ms p99 latency budget. Here we compute a
    deterministic pseudo-success rate from the cell id so tests are
    reproducible.
    """
    # Deterministic hash -> [0.4, 1.0]
    h = sum(ord(c) for c in h3_cell) % 600
    return 0.4 + (h / 1000.0)


def _local_supply_stub(rider_lat: float, rider_lon: float) -> int:
    """Stub for the local-supply feature.

    Production: read from the dispatch service's supply index. Here a
    deterministic value seeded by the rider's coarse H3 cell.
    """
    coarse_cell = h3.latlng_to_cell(rider_lat, rider_lon, 7)
    return (sum(ord(c) for c in coarse_cell) % 10) + 1


def _featurize_one(c: PinCandidate, ctx: ScoringContext) -> np.ndarray:
    """Build the 4-d feature vector for a single candidate."""
    walk_m = h3.great_circle_distance(
        (ctx.rider_lat, ctx.rider_lon),
        (c.lat, c.lon),
        unit="m",
    )
    hour = time.gmtime(ctx.timestamp_ms / 1000.0).tm_hour
    hist = _historical_success_stub(c.h3_cell)
    supply = _local_supply_stub(ctx.rider_lat, ctx.rider_lon)
    return np.array([walk_m, hour, hist, supply], dtype=np.float32)


def score_candidates(
    candidates: list[PinCandidate], ctx: ScoringContext
) -> np.ndarray:
    """Return a score per candidate (higher is better)."""
    if not candidates:
        return np.empty(0, dtype=np.float32)
    model = _load_model()
    feats = np.stack([_featurize_one(c, ctx) for c in candidates])
    return model.predict(feats).astype(np.float32)
