"""Candidate generation for pin selection.

Given a rider location, we enumerate a small set of plausible PUDO pin
locations. The geospatial primitive is Uber's H3 hexagonal hierarchical
index; we choose a resolution whose cell size matches the urban-curb
granularity at which the AV stack reasons.

Resolution choice (H3 docs):
    Res 11: ~25 m edge length, ~5400 m^2 area. Roughly one cell per
    short curb segment. Appropriate for dense urban PUDO.
    Res 10: ~65 m edge. Appropriate for suburban areas where curb
    density is lower.

We expose a single function `generate_candidates` whose density-aware
k-ring radius is selected from the rider density model at request time
(stubbed here as a constant).
"""

from __future__ import annotations

from dataclasses import dataclass

import h3


# H3 resolution for PUDO candidate cells. See module docstring.
DEFAULT_RESOLUTION = 11

# How many "rings" out from the rider's hex to consider. k=2 yields
# 1 + 6 + 12 = 19 cells around the rider's hex.
DEFAULT_K_RING = 2


@dataclass(frozen=True)
class PinCandidate:
    """A candidate PUDO pin location.

    `h3_cell` is the H3 cell id at `DEFAULT_RESOLUTION` that contains
    (`lat`, `lon`). We keep both representations because (a) downstream
    constraint checks operate on lat/lon polygons, and (b) congestion
    bookkeeping is keyed on the hex cell.
    """

    lat: float
    lon: float
    h3_cell: str


def generate_candidates(
    rider_lat: float,
    rider_lon: float,
    resolution: int = DEFAULT_RESOLUTION,
    k_ring: int = DEFAULT_K_RING,
) -> list[PinCandidate]:
    """Return H3-grid PUDO candidates centered on the rider.

    Args:
        rider_lat: Rider latitude in WGS84 degrees.
        rider_lon: Rider longitude in WGS84 degrees.
        resolution: H3 resolution. See module docstring for guidance.
        k_ring: Number of hex rings to expand around the rider's cell.

    Returns:
        A list of `PinCandidate`s. Order is stable for a given
        (rider_lat, rider_lon, resolution, k_ring) tuple, which makes
        downstream behavior reproducible under load testing.
    """
    home_cell = h3.latlng_to_cell(rider_lat, rider_lon, resolution)
    cells = sorted(h3.grid_disk(home_cell, k_ring))
    out: list[PinCandidate] = []
    for cell in cells:
        lat, lon = h3.cell_to_latlng(cell)
        out.append(PinCandidate(lat=lat, lon=lon, h3_cell=cell))
    return out
