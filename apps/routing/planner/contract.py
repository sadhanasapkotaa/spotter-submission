"""The fuel-planning contract: the problem, what a valid plan is, and how to check one.

MODEL (every algorithm in this package solves exactly this):

* The route is a line of length D miles. A vehicle drives it start -> end without detours.
* Station i sits at mile m_i in [0, D) and sells fuel at price p_i > 0 dollars/gallon.
* The tank holds R miles of fuel (R / mpg gallons). The vehicle starts with S0 miles of fuel
  (0 <= S0 <= R); that fuel is already paid for and is not part of the cost.
* Fuel can be bought, in any real amount, only at a station, only while the tank stays <= R.
* The tank may reach exactly 0 on arrival anywhere (no safety reserve; lower R to add one).
* Fuel burn is 1 mile per mile driven, i.e. 1/mpg gallons per mile.

OBJECTIVE: minimise sum_i p_i * b_i / mpg, where b_i >= 0 is the miles of fuel bought at i.

DERIVED FACTS (each is checked by the tests):

* FEASIBILITY: a plan exists iff m_first <= S0, every gap between consecutive stations <= R, and
  D - m_last <= R (when D > S0). Otherwise the trip is impossible; we report the mile where fuel
  runs out.
* NO WASTE: an optimal plan buys exactly max(0, D - S0) miles of fuel and arrives with an empty tank.
* LOWER BOUND = ACHIEVABLE: label each mile (x-1, x] with the cheapest station in [x - R, x - 1].
  No plan can beat that (a unit of fuel bought at i is burned within R miles after i, FIFO), and
  a plan achieving it always exists. Hence it is the exact optimum.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

TOL = 1e-7


class PlannerError(Exception):
    """Base class for planner failures."""


class InvalidProblem(PlannerError):
    """The inputs themselves are nonsense (negative range, NaN price, ...)."""


class Infeasible(PlannerError):
    """No plan exists. `at_mile` is the mile where the vehicle runs out of fuel."""

    def __init__(self, at_mile: float):
        super().__init__(f"fuel runs out at mile {at_mile:.1f}: no station within range ahead")
        self.at_mile = at_mile


class PlanInvalid(PlannerError):
    """A produced plan violates the tank constraints (should never happen; used by tests)."""


@dataclass(frozen=True)
class Problem:
    distance: float
    miles: tuple[float, ...]  # station mile markers, ascending, all in [0, distance)
    prices: tuple[float, ...]  # $/gallon, same order
    source_index: tuple[int, ...]  # index of each station in the caller's original list
    range_mi: float = 500.0
    start_mi: float = 500.0
    mpg: float = 10.0
    dropped: int = 0  # stations outside [0, distance) that were ignored

    @property
    def n(self) -> int:
        return len(self.miles)


@dataclass(frozen=True)
class Purchase:
    index: int  # index into Problem.miles / Problem.prices
    mile: float
    price: float
    miles_bought: float  # miles of range bought here

    def gallons(self, mpg: float) -> float:
        return self.miles_bought / mpg

    def cost(self, mpg: float) -> float:
        return self.price * self.miles_bought / mpg


@dataclass(frozen=True)
class Plan:
    purchases: tuple[Purchase, ...]
    cost: float  # dollars
    algorithm: str = ""


def make_problem(
    stations,
    distance: float,
    *,
    range_mi: float = 500.0,
    start_mi: float | None = None,
    mpg: float = 10.0,
) -> Problem:
    """Validate inputs and build a Problem. `stations` is an iterable of (mile, price)."""
    if start_mi is None:
        start_mi = range_mi
    for name, value in (("distance", distance), ("range_mi", range_mi), ("mpg", mpg)):
        if not (math.isfinite(value) and value > 0):
            raise InvalidProblem(f"{name} must be a positive number, got {value!r}")
    if not (math.isfinite(start_mi) and 0 <= start_mi <= range_mi + TOL):
        raise InvalidProblem(f"start_mi must be within [0, range_mi], got {start_mi!r}")
    start_mi = min(start_mi, range_mi)

    rows = []
    dropped = 0
    for i, (mile, price) in enumerate(stations):
        if not (math.isfinite(mile) and math.isfinite(price) and price > 0):
            raise InvalidProblem(f"station {i}: bad mile/price ({mile!r}, {price!r})")
        if 0 <= mile < distance:
            rows.append((mile, price, i))
        else:
            dropped += 1
    rows.sort()  # by mile, then price, then original index: fully deterministic
    return Problem(
        distance=float(distance),
        miles=tuple(r[0] for r in rows),
        prices=tuple(r[1] for r in rows),
        source_index=tuple(r[2] for r in rows),
        range_mi=float(range_mi),
        start_mi=float(start_mi),
        mpg=float(mpg),
        dropped=dropped,
    )


def first_uncovered_mile(p: Problem) -> float | None:
    """Mile where fuel would run out, or None if the trip is feasible."""
    if p.distance <= p.start_mi:
        return None
    if p.n == 0 or p.miles[0] > p.start_mi:
        return p.start_mi
    for a, b in zip(p.miles, p.miles[1:], strict=False):
        if b - a > p.range_mi:
            return a + p.range_mi
    if p.distance - p.miles[-1] > p.range_mi:
        return p.miles[-1] + p.range_mi
    return None


def require_feasible(p: Problem) -> None:
    gap = first_uncovered_mile(p)
    if gap is not None:
        raise Infeasible(gap)


def validate_plan(p: Problem, purchases, *, tol: float = TOL) -> tuple[float, float]:
    """Simulate a plan against the tank rules. Returns (cost_dollars, fuel_left_at_end).

    This is the referee: it shares no code with any algorithm.
    """
    by_index: dict[int, float] = {}
    for pu in purchases:
        if pu.miles_bought < -tol:
            raise PlanInvalid(f"negative purchase at station {pu.index}")
        by_index[pu.index] = by_index.get(pu.index, 0.0) + pu.miles_bought

    fuel, pos, cost = p.start_mi, 0.0, 0.0
    for i in range(p.n):
        fuel -= p.miles[i] - pos
        pos = p.miles[i]
        if fuel < -tol:
            raise PlanInvalid(f"ran dry before station {i} (mile {pos:.2f}), fuel {fuel:.4f}")
        bought = by_index.pop(i, 0.0)
        fuel += bought
        if fuel > p.range_mi + tol:
            raise PlanInvalid(f"tank overflow at station {i}: {fuel:.4f} > {p.range_mi}")
        cost += p.prices[i] * bought / p.mpg
    if by_index:
        raise PlanInvalid(f"purchases at unknown stations: {sorted(by_index)}")
    fuel -= p.distance - pos
    if fuel < -tol:
        raise PlanInvalid(f"ran dry before the destination, fuel {fuel:.4f}")
    return cost, fuel
