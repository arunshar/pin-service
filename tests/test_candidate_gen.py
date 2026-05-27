"""Tests for candidate_gen module."""

from pin_service.candidate_gen import (
    DEFAULT_K_RING,
    DEFAULT_RESOLUTION,
    generate_candidates,
)


def test_default_k_ring_returns_19_cells():
    """k=2 hex ring => 1 + 6 + 12 = 19 cells."""
    candidates = generate_candidates(37.7799, -122.4080)
    assert len(candidates) == 19


def test_candidates_are_deterministic():
    """Same input -> same output, same order (load-test reproducibility)."""
    a = generate_candidates(37.7799, -122.4080)
    b = generate_candidates(37.7799, -122.4080)
    assert [c.h3_cell for c in a] == [c.h3_cell for c in b]


def test_rider_cell_is_among_candidates():
    """The rider's own H3 cell must always be a candidate."""
    import h3

    rider_cell = h3.latlng_to_cell(37.7799, -122.4080, DEFAULT_RESOLUTION)
    candidates = generate_candidates(37.7799, -122.4080)
    assert rider_cell in {c.h3_cell for c in candidates}


def test_larger_k_ring_returns_more_candidates():
    small = generate_candidates(37.7799, -122.4080, k_ring=1)
    large = generate_candidates(37.7799, -122.4080, k_ring=3)
    assert len(large) > len(small)


def test_resolution_affects_cell_size():
    """Higher H3 res -> smaller cells -> denser candidate spacing."""
    import h3

    coarse = generate_candidates(37.7799, -122.4080, resolution=9, k_ring=2)
    fine = generate_candidates(37.7799, -122.4080, resolution=11, k_ring=2)
    # Same cell count (same k_ring) but finer cells have smaller area.
    assert len(coarse) == len(fine)
    coarse_area = h3.cell_area(coarse[0].h3_cell, unit="m^2")
    fine_area = h3.cell_area(fine[0].h3_cell, unit="m^2")
    assert fine_area < coarse_area
