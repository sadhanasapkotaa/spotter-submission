"""Algorithm G: the classic "next cheaper station" greedy.

At a station: if a station that is no dearer lies within range, buy just enough to reach the first
such station. Otherwise fill the tank and drive to the cheapest station in range. The destination
counts as a free station, so the final leg buys only what is needed.
Worst case O(n^2) (e.g. steadily rising prices), which is why it is not the production choice.
"""

from __future__ import annotations

from .contract import Infeasible, Plan, Problem, Purchase, require_feasible


def plan_greedy(p: Problem) -> Plan:
    if p.distance <= p.start_mi:
        return Plan((), 0.0, "greedy")
    require_feasible(p)

    R = p.range_mi
    miles = [*p.miles, p.distance]
    prices = [*p.prices, 0.0]  # the destination is a station selling at $0
    dest = p.n

    i, fuel = 0, p.start_mi - miles[0]
    bought = [0.0] * p.n
    while i != dest:
        reach = miles[i] + R
        target = None
        j = i + 1
        while j <= dest and miles[j] <= reach:
            if prices[j] <= prices[i]:
                target = j
                break
            j += 1
        if target is not None:
            need = miles[target] - miles[i]
            buy = max(0.0, need - fuel)
            bought[i] += buy
            fuel += buy - need
            i = target
            continue
        in_range = [k for k in range(i + 1, dest + 1) if miles[k] <= reach]
        if not in_range:
            raise Infeasible(reach)
        target = min(in_range, key=lambda k: (prices[k], miles[k]))
        buy = R - fuel
        bought[i] += buy
        fuel = R - (miles[target] - miles[i])
        i = target

    purchases = tuple(
        Purchase(k, p.miles[k], p.prices[k], bought[k]) for k in range(p.n) if bought[k] > 0
    )
    return Plan(purchases, sum(pu.cost(p.mpg) for pu in purchases), "greedy")
