"""Locate stations along a route: how far along it (mile marker) and how far off it (offset).

Pure numpy/scipy, no Django, so the geometry can be tested against ground truth.

Method (chosen by benchmark; see README):
  1. Work in spherical Web Mercator. It is conformal (angles are preserved), so the foot of the
     perpendicular from a station to the road is correct, unlike plain lon/lat degrees where it
     is skewed by cos(latitude).
  2. Densify the route so no segment exceeds `max_segment_mi`; a KD-tree gives each station's
     nearest route vertex, and the exact projection is taken on the two segments touching it.
  3. Mile marker = geodesic (haversine) cumulative distance at the projected point, so it is in
     the same units as the route's total length. Mercator distances are never used as miles.
  4. Offset = Mercator distance x cos(latitude), converted back to true miles.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree

EARTH_RADIUS_MI = 3958.7613


def haversine_mi(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = (
        np.sin((p2 - p1) / 2) ** 2
        + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MI * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def to_mercator_mi(lat, lon):
    """Spherical Mercator in miles (conformal; distances inflated by 1/cos(lat))."""
    lat = np.clip(lat, -85, 85)
    x = EARTH_RADIUS_MI * np.radians(lon)
    y = EARTH_RADIUS_MI * np.log(np.tan(np.pi / 4 + np.radians(lat) / 2))
    return x, y


@dataclass(frozen=True)
class Route:
    lat: np.ndarray
    lon: np.ndarray
    cum_mi: np.ndarray  # geodesic miles from the start, per vertex
    x: np.ndarray  # Mercator miles
    y: np.ndarray

    @property
    def length_mi(self) -> float:
        return float(self.cum_mi[-1])

    def __len__(self) -> int:
        return len(self.lat)


def build_route(lonlat, max_segment_mi: float = 0.25) -> Route:
    """lonlat: sequence of (lon, lat[, ...]) as in GeoJSON. Densifies long segments."""
    arr = np.asarray([(c[0], c[1]) for c in lonlat], dtype=float)
    if len(arr) < 2:
        raise ValueError("a route needs at least two points")
    lon, lat = arr[:, 0], arr[:, 1]
    keep = np.r_[True, (np.abs(np.diff(lat)) + np.abs(np.diff(lon))) > 1e-9]  # drop repeats
    lon, lat = lon[keep], lat[keep]
    if len(lat) < 2:
        raise ValueError("a route needs at least two distinct points")

    seg = haversine_mi(lat[:-1], lon[:-1], lat[1:], lon[1:])
    pieces = np.maximum(1, np.ceil(seg / max_segment_mi).astype(int))
    if pieces.max() > 1:  # insert evenly spaced points (linear in lon/lat; segments are short)
        idx = np.repeat(np.arange(len(seg)), pieces)
        first = np.r_[0, np.cumsum(pieces)[:-1]]
        frac = (np.arange(len(idx)) - np.repeat(first, pieces)) / np.repeat(pieces, pieces)
        lat = np.r_[lat[idx] + (lat[idx + 1] - lat[idx]) * frac, lat[-1]]
        lon = np.r_[lon[idx] + (lon[idx + 1] - lon[idx]) * frac, lon[-1]]
        seg = haversine_mi(lat[:-1], lon[:-1], lat[1:], lon[1:])
    cum = np.r_[0.0, np.cumsum(seg)]
    x, y = to_mercator_mi(lat, lon)
    return Route(lat, lon, cum, x, y)


@dataclass(frozen=True)
class Located:
    index: np.ndarray  # positions in the input station arrays that lie within the corridor
    mile: np.ndarray  # route mile marker of each
    offset_mi: np.ndarray  # true distance from the route, miles


def locate_stations(route: Route, st_lat, st_lon, max_offset_mi) -> Located:
    """Project stations onto the route. `max_offset_mi` is a scalar or a per-station array
    (a negative limit excludes that station)."""
    st_lat, st_lon = np.asarray(st_lat, float), np.asarray(st_lon, float)
    limit = np.broadcast_to(np.asarray(max_offset_mi, float), st_lat.shape)
    sx, sy = to_mercator_mi(st_lat, st_lon)
    scale = np.cos(np.radians(np.clip(st_lat, -85, 85)))  # true miles per Mercator mile

    # KD-tree prefilter. Mercator inflates distances by at most 1/cos(max |lat| on the route).
    inflate = 1.0 / max(1e-6, float(np.cos(np.radians(min(85.0, np.abs(route.lat).max())))))
    radius = (
        max(float(limit.max()), 0.0) * inflate + 1.0
    )  # +1 mi: nearest vertex may be a segment off
    tree = cKDTree(np.c_[route.x, route.y])
    dist, vi = tree.query(np.c_[sx, sy], k=1, distance_upper_bound=radius)
    ids = np.flatnonzero(np.isfinite(dist))
    if ids.size == 0:
        return Located(ids, np.empty(0), np.empty(0))
    px, py, v = sx[ids], sy[ids], vi[ids]

    best_d = np.full(ids.size, np.inf)
    best_mile = np.zeros(ids.size)
    n = len(route)
    for a_off in (-1, 0):  # the segments before and after the nearest vertex
        a = np.clip(v + a_off, 0, n - 2)
        b = a + 1
        ax, ay, bx, by = route.x[a], route.y[a], route.x[b], route.y[b]
        dx, dy = bx - ax, by - ay
        len2 = np.maximum(dx * dx + dy * dy, 1e-18)
        t = np.clip(((px - ax) * dx + (py - ay) * dy) / len2, 0.0, 1.0)
        d = np.hypot(px - (ax + t * dx), py - (ay + t * dy))
        mile = route.cum_mi[a] + t * (route.cum_mi[b] - route.cum_mi[a])
        better = d < best_d
        best_d = np.where(better, d, best_d)
        best_mile = np.where(better, mile, best_mile)

    offset = best_d * scale[ids]
    ok = (offset <= limit[ids]) & (limit[ids] >= 0)
    return Located(ids[ok], best_mile[ok], offset[ok])
