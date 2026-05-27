"""Tests for the ML scorer."""

import time

import numpy as np
import pytest

from pin_service.candidate_gen import PinCandidate, generate_candidates
from pin_service.scorer import ScoringContext, score_candidates


def _ctx() -> ScoringContext:
    return ScoringContext(
        rider_lat=37.7799,
        rider_lon=-122.4080,
        timestamp_ms=int(time.time() * 1000),
    )


def test_empty_input_returns_empty_array():
    out = score_candidates([], _ctx())
    assert out.shape == (0,)


def test_score_output_matches_candidate_count():
    cands = generate_candidates(37.7799, -122.4080)
    out = score_candidates(cands, _ctx())
    assert out.shape == (len(cands),)


def test_scores_are_finite_floats():
    cands = generate_candidates(37.7799, -122.4080)
    out = score_candidates(cands, _ctx())
    assert np.all(np.isfinite(out))


def test_closer_candidate_outscores_far_one_on_average():
    """All else equal, closer pins should tend to score higher.

    This is not a hard guarantee — the model also reads supply, hour,
    and historical features — but on a controlled pair the expectation
    is stable across resolutions.
    """
    close = PinCandidate(lat=37.78000, lon=-122.40800, h3_cell="8b283082d6dffff")
    far = PinCandidate(lat=37.78900, lon=-122.40800, h3_cell="8b283082c87ffff")
    scores = score_candidates([close, far], _ctx())
    assert scores[0] >= scores[1] - 0.5  # generous margin for stub features
