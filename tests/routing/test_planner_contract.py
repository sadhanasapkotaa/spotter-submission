"""Worked examples for the fuel-planning contract (see apps/routing/planner/contract.py)."""

import math

import pytest

from apps.routing.planner import (
    InvalidProblem,
    PlanInvalid,
    Purchase,
    make_problem,
    validate_plan,
)


def prob(stations, distance, **kw):
    return make_problem(stations, distance, **kw)


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
