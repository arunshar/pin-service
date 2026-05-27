"""Hard-constraint filtering ("is this pin even legal/reachable?").

In production this module queries an HD-map service (e.g. Lanelet2-backed
or a proprietary equivalent). The HD map encodes drivable lanes, curb
attributes, no-stop zones, school zones, construction geofences, etc.

For this scaffold we use a Shapely-polygon stand-in. The polygon shapes
are loaded from `data/hd_map_fixture.json` at module import time so that
tests and load tests share the same fixture.

The filter outputs are strict booleans. ML scoring NEVER overrides a
hard-constraint failure. This separation is a core safety invariant.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass

from shapely.geometry import Point, Polygon, shape

from pin_service.candidate_gen import PinCandidate


_DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / "data"
_FIXTURE_PATH = _DATA_DIR / "hd_map_fixture.json"


@dataclass
class HDMapView:
    """Snapshot of HD-map polygons used by the feasibility filter."""

    drivable_area: Polygon
    no_stop_zones: list[Polygon]

    @classmethod
    def from_fixture(cls, path: pathlib.Path = _FIXTURE_PATH) -> "HDMapView":
        with open(path, "r") as f:
            doc = json.load(f)
        drivable = shape(doc["drivable_area"])
        zones = [shape(z) for z in doc["no_stop_zones"]]
        return cls(drivable_area=drivable, no_stop_zones=zones)


# Loaded once at import time. In a real service we would hot-reload this
# on map updates via a versioned config-channel subscription.
HD_MAP = HDMapView.from_fixture()


def is_feasible(candidate: PinCandidate, hd_map: HDMapView = HD_MAP) -> bool:
    """Return True iff the candidate satisfies all hard constraints.

    Constraints applied:
      1. The candidate point lies inside the drivable area polygon.
      2. The candidate point does not lie inside any no-stop zone.

    Production would additionally check:
      - Lane-level reachability from current vehicle pose
      - Curb-side validity (do not stop on the divider median)
      - Active operational geofences (e.g. event closures)
      - Time-of-day restrictions (e.g. school-zone hours)
      - Accessibility constraints from the request
    """
    point = Point(candidate.lon, candidate.lat)
    if not hd_map.drivable_area.contains(point):
        return False
    for zone in hd_map.no_stop_zones:
        if zone.contains(point):
            return False
    return True


def filter_feasible(
    candidates: list[PinCandidate], hd_map: HDMapView = HD_MAP
) -> list[PinCandidate]:
    """Keep only candidates that pass `is_feasible`."""
    return [c for c in candidates if is_feasible(c, hd_map)]
