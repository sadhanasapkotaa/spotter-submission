"""Station location: mile marker and offset, checked against stations placed at known positions."""

import numpy as np
import pytest

from apps.routing.corridor import build_route, haversine_mi, locate_stations
from tests.routing.helpers import meandering_route, point_beside


@pytest.fixture(scope="module")
def world():
    lat, lon, cum = meandering_route()
    rng = np.random.default_rng(42)
    mile = rng.uniform(5, cum[-1] - 5, 1500)
    off = rng.uniform(0, 3, 1500)
    slat, slon = point_beside(lat, lon, cum, mile, off)
    return {
        "route": build_route(np.c_[lon, lat]),
        "cum": cum,
        "mile": mile,
        "off": off,
        "slat": slat,
        "slon": slon,
    }


def test_route_length_matches_the_geodesic_sum(world):
    assert world["route"].length_mi == pytest.approx(world["cum"][-1], rel=1e-6)


def test_mile_markers_and_offsets_are_accurate(world):
    r = locate_stations(world["route"], world["slat"], world["slon"], 3.5)
    assert len(r.index) == 1500  # every station is within 3 mi, so none is lost
    mile_err = np.abs(r.mile - world["mile"][r.index])
    off_err = np.abs(r.offset_mi - world["off"][r.index])
    assert np.percentile(mile_err, 99) < 0.02  # about 100 feet
    assert np.percentile(off_err, 99) < 0.02
    assert mile_err.mean() < 0.01


def test_stations_beyond_the_corridor_are_dropped(world):
    r = locate_stations(world["route"], world["slat"], world["slon"], 1.0)
    assert 0 < len(r.index) < 1500
    assert (r.offset_mi <= 1.0).all()


def test_per_station_limits_and_exclusion(world):
    limits = np.full(len(world["slat"]), 3.5)
    limits[:100] = -1  # excluded entirely
    r = locate_stations(world["route"], world["slat"], world["slon"], limits)
    assert not (r.index < 100).any()
    assert len(r.index) == 1400


def test_far_away_stations_are_ignored(world):
    r = locate_stations(world["route"], np.array([25.0, 47.5]), np.array([-80.0, -120.0]), 5.0)
    assert len(r.index) == 0


def test_a_naive_degree_based_projection_would_be_wrong(world):
    """Guard for the method choice: planar lon/lat fraction x total length is off by miles."""
    from shapely.geometry import LineString, Point

    route = world["route"]
    line = LineString(np.c_[route.lon, route.lat])
    k = 0
    naive = (
        line.project(Point(world["slon"][k], world["slat"][k]), normalized=True) * route.length_mi
    )
    assert abs(naive - world["mile"][k]) > 1.0  # the method we rejected
    r = locate_stations(route, world["slat"][k : k + 1], world["slon"][k : k + 1], 3.5)
    assert abs(r.mile[0] - world["mile"][k]) < 0.05  # the method we use


def test_sparse_route_is_densified_so_a_midpoint_station_lands_mid_way():
    route = build_route([(-100.0, 39.0), (-98.5, 39.0)])  # one ~80 mile segment, two vertices
    assert len(route) > 100
    r = locate_stations(route, np.array([39.02]), np.array([-99.25]), 3.0)
    assert r.mile[0] == pytest.approx(route.length_mi / 2, abs=0.3)
    assert r.offset_mi[0] == pytest.approx(0.02 * 69.09, abs=0.05)


def test_route_needs_two_distinct_points():
    with pytest.raises(ValueError):
        build_route([(-100.0, 39.0), (-100.0, 39.0)])


def test_haversine_known_distance():
    # New York -> Los Angeles great circle is about 2,445 miles.
    assert haversine_mi(40.7128, -74.0060, 34.0522, -118.2437) == pytest.approx(2445, abs=10)
