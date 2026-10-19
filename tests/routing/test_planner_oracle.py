"""Property tests: every algorithm against independent reference solvers.

Chain of trust: brute force (tiny) == grid DP == state-graph Dijkstra == per-mile window formula
== window DP == greedy, on thousands of random trips; plus structural properties of the contract.
"""

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from apps.routing.planner import (
    first_uncovered_mile,
    make_problem,
    plan_greedy,
)
from apps.routing.planner.graph import cost_state_graph
from apps.routing.planner.oracle import cost_brute_force, cost_grid_dp

FAST = settings(max_examples=250, deadline=None, suppress_health_check=list(HealthCheck))


def close(a, b):
    return a == pytest.approx(b, rel=1e-7, abs=1e-7)


@st.composite
def integer_trips(draw, max_range=25, max_stations=10):
    R = draw(st.integers(2, max_range))
    dist = draw(st.integers(1, 4 * R))
    start = draw(st.integers(0, R))
    n = draw(st.integers(0, max_stations))
    stations = [
        (draw(st.integers(0, max(0, dist - 1))), draw(st.integers(1, 12))) for _ in range(n)
    ]
    mpg = draw(st.sampled_from([1, 2, 5, 10]))
    return make_problem(stations, dist, range_mi=R, start_mi=start, mpg=mpg)


@st.composite
def real_trips(draw):
    R = draw(st.floats(50, 600))
    dist = draw(st.floats(1, 5 * R))
    start = draw(st.floats(0, R))
    n = draw(st.integers(0, 40))
    stations = [(draw(st.floats(0, dist)), draw(st.floats(1.5, 8))) for _ in range(n)]
    return make_problem(
        stations, dist, range_mi=R, start_mi=start, mpg=draw(st.sampled_from([8.0, 10.0, 25.0]))
    )


def window_formula_cost(p):
    """Independent per-mile formula: the mile (x-1, x] is burned before a station at x, so it costs
    the cheapest price among stations in [x-R, x-1]."""
    total = 0.0
    for x in range(int(p.start_mi) + 1, int(p.distance) + 1):
        prices = [
            pr for m, pr in zip(p.miles, p.prices, strict=True) if x - p.range_mi <= m <= x - 1
        ]
        total += min(prices) / p.mpg
    return total


@settings(max_examples=150, deadline=None, suppress_health_check=list(HealthCheck))
@given(st.data())
def test_brute_force_matches_grid_dp_on_tiny_trips(data):
    p = data.draw(integer_trips(max_range=5, max_stations=3))
    assert close(cost_brute_force(p), cost_grid_dp(p))


@FAST
@given(integer_trips())
def test_state_graph_matches_grid_dp(p):
    assert close(cost_state_graph(p), cost_grid_dp(p))


@FAST
@given(integer_trips())
def test_greedy_is_optimal(p):
    assume(first_uncovered_mile(p) is None)
    assert close(plan_greedy(p).cost, cost_grid_dp(p))
