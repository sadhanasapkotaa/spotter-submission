"""Fuel planner. `plan_fuel` is the single entry point used by the API."""

from .contract import (
    Infeasible,
    InvalidProblem,
    Plan,
    PlanInvalid,
    PlannerError,
    Problem,
    Purchase,
    first_uncovered_mile,
    make_problem,
    validate_plan,
)
from .greedy import plan_greedy

ALGORITHMS = {"greedy": plan_greedy}


def plan_fuel(problem: Problem, algorithm: str = "greedy") -> Plan:
    return ALGORITHMS[algorithm](problem)


__all__ = [
    "ALGORITHMS",
    "Infeasible",
    "InvalidProblem",
    "Plan",
    "PlanInvalid",
    "PlannerError",
    "Problem",
    "Purchase",
    "first_uncovered_mile",
    "make_problem",
    "plan_fuel",
    "plan_greedy",
    "validate_plan",
]
