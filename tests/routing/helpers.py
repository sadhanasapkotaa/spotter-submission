"""Synthetic routes with ground truth, shared by the corridor and API tests."""

import numpy as np

from apps.routing.corridor import haversine_mi

WAYPOINTS = [(40.71, -74.0), (40.44, -80.0), (39.77, -86.16), (38.63, -90.2), (35.47, -97.52)]


def meandering_route(seed=1, step=0.2, waypoints=WAYPOINTS):
    """Dense lat/lon polyline with gentle wobble; returns (lat, lon, cumulative_miles)."""
    rng = np.random.default_rng(seed)
    parts = []
    for (la1, lo1), (la2, lo2) in zip(waypoints, waypoints[1:], strict=False):
        length = float(haversine_mi(la1, lo1, la2, lo2))
        t = np.sort(rng.uniform(0, 1, max(2, int(length / step))))
        t = np.r_[0, t, 1]
        wob = 0.3 / 69 * np.sin(t * rng.uniform(5, 15))
        parts.append(np.c_[la1 + (la2 - la1) * t + wob, lo1 + (lo2 - lo1) * t][:-1])
    parts.append(np.array([waypoints[-1]]))
    pts = np.vstack(parts)
    pts = pts[np.r_[True, np.abs(np.diff(pts, axis=0)).sum(1) > 1e-7]]
    lat, lon = pts[:, 0], pts[:, 1]
    cum = np.r_[0, np.cumsum(haversine_mi(lat[:-1], lon[:-1], lat[1:], lon[1:]))]
    return lat, lon, cum


def point_beside(lat, lon, cum, mile, offset_mi):
    """The point `offset_mi` to the left of the route at route-mile `mile` (vectorised)."""
    mile = np.asarray(mile, float)
    i = np.clip(np.searchsorted(cum, mile, side="right") - 1, 0, len(cum) - 2)
    t = (mile - cum[i]) / (cum[i + 1] - cum[i])
    la = lat[i] + (lat[i + 1] - lat[i]) * t
    lo = lon[i] + (lon[i + 1] - lon[i]) * t
    north_mi = (lat[i + 1] - lat[i]) * 69.09
    east_mi = (lon[i + 1] - lon[i]) * 69.17 * np.cos(np.radians(la))
    norm = np.hypot(north_mi, east_mi)
    left_east, left_north = -north_mi / norm, east_mi / norm
    return (
        la + left_north * offset_mi / 69.09,
        lo + left_east * offset_mi / (69.17 * np.cos(np.radians(la))),
    )
