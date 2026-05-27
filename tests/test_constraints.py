"""Tests for the hard-constraint filter."""

from pin_service.candidate_gen import PinCandidate, generate_candidates
from pin_service.constraints import HD_MAP, filter_feasible, is_feasible


def test_point_inside_drivable_passes():
    c = PinCandidate(lat=37.780, lon=-122.405, h3_cell="x")
    assert is_feasible(c)


def test_point_outside_drivable_fails():
    c = PinCandidate(lat=39.000, lon=-122.405, h3_cell="x")
    assert not is_feasible(c)


def test_point_in_no_stop_zone_fails():
    # No-stop zone center per fixture
    c = PinCandidate(lat=37.779, lon=-122.409, h3_cell="x")
    assert not is_feasible(c)


def test_filter_drops_only_infeasible():
    cands = [
        PinCandidate(lat=37.780, lon=-122.405, h3_cell="ok"),
        PinCandidate(lat=39.000, lon=-122.405, h3_cell="bad"),
    ]
    out = filter_feasible(cands)
    assert {c.h3_cell for c in out} == {"ok"}


def test_realistic_request_yields_some_feasible():
    """A request inside the drivable area should yield >0 feasible pins."""
    cands = generate_candidates(37.780, -122.408)
    feasible = filter_feasible(cands)
    assert len(feasible) > 0
    assert len(feasible) <= len(cands)
