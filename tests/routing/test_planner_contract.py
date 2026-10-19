"""Worked examples for the fuel-planning contract (see apps/routing/planner/contract.py)."""

import math

import pytest

from apps.routing.planner import (
    Infeasible,
    InvalidProblem,
    PlanInvalid,
    Purchase,
    first_uncovered_mile,
    make_problem,
    plan_greedy,
    plan_window,
    validate_plan,
)

ALGOS = [plan_window, plan_greedy]


def prob(stations, distance, **kw):
    return make_problem(stations, distance, **kw)


@pytest.mark.parametrize("algo", ALGOS)
def test_trip_within_starting_range_costs_nothing(algo):
    plan = algo(prob([(100, 3.0)], 450))
    assert plan.purchases == () and plan.cost == 0


@pytest.mark.parametrize("algo", ALGOS)
def test_single_station_buys_exactly_what_is_needed(algo):
    # 800 mi trip, 500 free. One station at mile 300: buy the missing 300 miles = 30 gal at $3.
    plan = algo(prob([(300, 3.0)], 800))
    assert [p.index for p in plan.purchases] == [0]
    assert plan.purchases[0].miles_bought == pytest.approx(300)
    assert plan.cost == pytest.approx(90.0)


@pytest.mark.parametrize("algo", ALGOS)
def test_buys_all_fuel_at_the_cheaper_reachable_station(algo):
    plan = algo(prob([(100, 4.0), (400, 3.0)], 900))
    assert [p.index for p in plan.purchases] == [1]
    assert plan.cost == pytest.approx(400 / 10 * 3.0)


@pytest.mark.parametrize("algo", ALGOS)
def test_tops_up_at_a_cheap_station_only_for_miles_nothing_else_can_serve(algo):
    # Cheap A at mile 50, dear B at mile 450, destination 900, start with 500.
    # Miles 500-550 can be served by A (it reaches to 550): 50 miles at $2.
    # Miles 550-900 are out of A's reach, so B supplies them: 350 miles at $5.
    plan = algo(prob([(50, 2.0), (450, 5.0)], 900))
    by_idx = {p.index: p.miles_bought for p in plan.purchases}
    assert by_idx[0] == pytest.approx(50)
    assert by_idx[1] == pytest.approx(350)
    assert plan.cost == pytest.approx(50 / 10 * 2.0 + 350 / 10 * 5.0)


def test_equal_prices_choose_the_later_station():
    plan = plan_window(prob([(100, 3.0), (400, 3.0)], 800))
    assert [p.index for p in plan.purchases] == [1]


def test_stations_at_or_past_the_destination_are_ignored():
    p = prob([(800, 1.0), (900, 1.0), (300, 3.0)], 800)
    assert p.n == 1 and p.dropped == 2
    assert plan_window(p).cost == pytest.approx(90.0)


def test_starting_empty_needs_a_station_at_mile_zero():
    assert first_uncovered_mile(prob([(5, 3.0)], 100, start_mi=0)) == 0
    assert plan_window(prob([(0, 3.0)], 100, start_mi=0)).cost == pytest.approx(30.0)


@pytest.mark.parametrize("algo", ALGOS)
def test_gap_longer_than_range_is_infeasible_and_names_the_mile(algo):
    with pytest.raises(Infeasible) as err:
        algo(prob([(100, 3.0), (700, 3.0)], 1000))
    assert err.value.at_mile == pytest.approx(600)


def test_first_station_beyond_starting_fuel_is_infeasible():
    with pytest.raises(Infeasible) as err:
        plan_window(prob([(300, 3.0)], 1000, start_mi=200))
    assert err.value.at_mile == pytest.approx(200)


def test_last_stretch_longer_than_range_is_infeasible():
    with pytest.raises(Infeasible):
        plan_window(prob([(100, 3.0)], 700))  # 600 miles left after the only station


@pytest.mark.parametrize("algo", ALGOS)
def test_optimal_plan_arrives_with_an_empty_tank(algo):
    p = prob([(120, 3.1), (350, 2.9), (610, 3.4), (900, 3.0)], 1300)
    _, fuel_left = validate_plan(p, algo(p).purchases)
    assert fuel_left == pytest.approx(0, abs=1e-6)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"range_mi": 0},
        {"range_mi": -5},
        {"mpg": 0},
        {"start_mi": 600},
        {"start_mi": -1},
        {"distance": -3},
    ],
)
def test_nonsense_parameters_are_rejected(kwargs):
    args = {"stations": [(1, 3.0)], "distance": 100.0, "range_mi": 500.0, "mpg": 10.0}
    args.update(kwargs)
    with pytest.raises(InvalidProblem):
        make_problem(**args)


@pytest.mark.parametrize("station", [(10, 0), (10, -1), (10, math.nan), (math.inf, 3.0)])
def test_bad_stations_are_rejected(station):
    with pytest.raises(InvalidProblem):
        make_problem([station], 100)


def test_referee_catches_running_dry():
    p = prob([(300, 3.0)], 800)
    with pytest.raises(PlanInvalid, match="dry"):
        validate_plan(p, [Purchase(0, 300, 3.0, 100)])


def test_referee_catches_tank_overflow():
    p = prob([(300, 3.0)], 800)
    with pytest.raises(PlanInvalid, match="overflow"):
        validate_plan(p, [Purchase(0, 300, 3.0, 400)])  # 200 left + 400 > 500


def test_referee_accepts_a_correct_plan_and_prices_it():
    p = prob([(300, 3.0)], 800)
    cost, left = validate_plan(p, [Purchase(0, 300, 3.0, 300)])
    assert cost == pytest.approx(90.0) and left == pytest.approx(0)
