"""Property tests: every algorithm against independent reference solvers.

Chain of trust: brute force (tiny) == grid DP == state-graph Dijkstra == per-mile window formula
== window DP == greedy, on thousands of random trips; plus structural properties of the contract.
"""

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from apps.routing.planner import (
    Infeasible,
    first_uncovered_mile,
    make_problem,
    plan_greedy,
    plan_window,
    validate_plan,
)
from apps.routing.planner.graph import cost_naive_station_graph, cost_state_graph
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
def test_feasibility_rule_matches_the_oracle(p):
    feasible = first_uncovered_mile(p) is None
    assert feasible == (cost_grid_dp(p) != float("inf"))
    if not feasible:
        for algo in (plan_window, plan_greedy):
            with pytest.raises(Infeasible):
                algo(p)


@FAST
@given(integer_trips())
def test_window_dp_is_optimal(p):
    assume(first_uncovered_mile(p) is None)
    assert close(plan_window(p).cost, cost_grid_dp(p))


@FAST
@given(integer_trips())
def test_greedy_is_optimal(p):
    assume(first_uncovered_mile(p) is None)
    assert close(plan_greedy(p).cost, cost_grid_dp(p))


@FAST
@given(integer_trips())
def test_per_mile_window_formula_is_the_optimum(p):
    assume(first_uncovered_mile(p) is None)
    assert close(window_formula_cost(p), cost_grid_dp(p))


@FAST
@given(real_trips())
def test_window_and_greedy_agree_on_real_valued_trips(p):
    assume(first_uncovered_mile(p) is None)
    assert close(plan_window(p).cost, plan_greedy(p).cost)


@FAST
@given(real_trips())
def test_plans_are_valid_and_cost_what_they_claim(p):
    assume(first_uncovered_mile(p) is None)
    for algo in (plan_window, plan_greedy):
        plan = algo(p)
        cost, fuel_left = validate_plan(p, plan.purchases)
        assert close(cost, plan.cost)
        if p.distance > p.start_mi:
            assert fuel_left == pytest.approx(0, abs=1e-5)  # no fuel wasted
            assert sum(pu.miles_bought for pu in plan.purchases) == pytest.approx(
                p.distance - p.start_mi, abs=1e-5
            )


@FAST
@given(real_trips(), st.floats(0.1, 100))
def test_scaling_all_prices_scales_the_cost(p, k):
    assume(first_uncovered_mile(p) is None)
    scaled = make_problem(
        [(m, pr * k) for m, pr in zip(p.miles, p.prices, strict=True)],
        p.distance,
        range_mi=p.range_mi,
        start_mi=p.start_mi,
        mpg=p.mpg,
    )
    assert plan_window(scaled).cost == pytest.approx(plan_window(p).cost * k, rel=1e-7)


@FAST
@given(real_trips(), st.floats(0, 1))
def test_more_starting_fuel_never_costs_more(p, bump):
    assume(first_uncovered_mile(p) is None)
    more = make_problem(
        list(zip(p.miles, p.prices, strict=True)),
        p.distance,
        range_mi=p.range_mi,
        start_mi=p.start_mi + bump * (p.range_mi - p.start_mi),
        mpg=p.mpg,
    )
    assert plan_window(more).cost <= plan_window(p).cost + 1e-7


@FAST
@given(real_trips(), st.floats(0, 1), st.floats(1.5, 8))
def test_adding_a_station_never_costs_more(p, where, price):
    assume(first_uncovered_mile(p) is None)
    extra = [*zip(p.miles, p.prices, strict=True), (where * p.distance * 0.999, price)]
    bigger = make_problem(extra, p.distance, range_mi=p.range_mi, start_mi=p.start_mi, mpg=p.mpg)
    assert plan_window(bigger).cost <= plan_window(p).cost + 1e-7


def test_naive_station_graph_is_suboptimal_on_a_known_trip():
    # Optimal: fill 500 at the $2 station, carry it past the $6 one: 500mi@$2 + 100mi@$6 = $160.
    # Naive "arrive empty at every stop": 200mi@$2 + 400mi@$6 = $280.
    p = make_problem([(100, 2.0), (300, 6.0)], 700, range_mi=500, start_mi=100, mpg=10)
    assert plan_window(p).cost == pytest.approx(160.0)
    assert cost_naive_station_graph(p) == pytest.approx(280.0)
