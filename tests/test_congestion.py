"""Tests for the congestion tracker."""

from pin_service.congestion import CongestionTracker


def test_no_penalty_under_threshold():
    t = CongestionTracker(threshold=3, penalty=0.25)
    for _ in range(3):
        t.record_assignment("cell-a", now=1000.0)
    p = t.penalties_for(["cell-a"], now=1000.0)
    assert p[0] == 0.0


def test_penalty_applied_over_threshold():
    t = CongestionTracker(threshold=3, penalty=0.25)
    for _ in range(4):
        t.record_assignment("cell-a", now=1000.0)
    p = t.penalties_for(["cell-a"], now=1000.0)
    assert p[0] == 0.25


def test_window_expiry_clears_penalty():
    t = CongestionTracker(window_seconds=60.0, threshold=3, penalty=0.25)
    for _ in range(10):
        t.record_assignment("cell-a", now=1000.0)
    # Fast-forward past the window.
    p = t.penalties_for(["cell-a"], now=1500.0)
    assert p[0] == 0.0


def test_independent_cells_dont_affect_each_other():
    t = CongestionTracker(threshold=3, penalty=0.25)
    for _ in range(10):
        t.record_assignment("hot", now=1000.0)
    p = t.penalties_for(["hot", "cold"], now=1000.0)
    assert p[0] == 0.25
    assert p[1] == 0.0


def test_load_shed_triggers_at_global_cap():
    t = CongestionTracker(threshold=3, penalty=0.25, load_shed_ratio=2.0)
    # Cap = 3 * 2.0 = 6. Push 10 assignments across 3 cells.
    for cell in ("a", "b", "c"):
        for _ in range(4):
            t.record_assignment(cell, now=1000.0)
    assert t.should_load_shed(now=1000.0) is True


def test_load_shed_clears_after_window():
    t = CongestionTracker(window_seconds=60.0, threshold=3, load_shed_ratio=2.0)
    for cell in ("a", "b", "c"):
        for _ in range(4):
            t.record_assignment(cell, now=1000.0)
    assert t.should_load_shed(now=2000.0) is False
