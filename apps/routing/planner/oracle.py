"""Reference implementations used only by tests: slow, obviously correct, independent.

* cost_grid_dp: textbook DP over (station, fuel level) on an integer grid.
* cost_brute_force: tries every integer purchase vector (tiny instances only).
"""

from __future__ import annotations

import itertools
import math

from .contract import PlanInvalid, Problem, Purchase, validate_plan


def cost_grid_dp(p: Problem) -> float:
    if p.distance <= p.start_mi:
        return 0.0
    R, S0 = int(round(p.range_mi)), int(round(p.start_mi))
    miles = [int(round(m)) for m in p.miles] + [int(round(p.distance))]
    if miles[0] > S0:
        return math.inf
    inf = math.inf
    dp = [inf] * (R + 1)
    dp[S0 - miles[0]] = 0.0
    for i in range(p.n):
        price = p.prices[i] / p.mpg
        for f in range(1, R + 1):  # buying: dp[f] = min(dp[f], dp[f-1] + price)
            if dp[f - 1] + price < dp[f]:
                dp[f] = dp[f - 1] + price
        gap = miles[i + 1] - miles[i]
        nxt = [inf] * (R + 1)
        for f in range(gap, R + 1):
            nxt[f - gap] = dp[f]
        dp = nxt
    return min(dp)


def cost_brute_force(p: Problem) -> float:
    best = math.inf
    R = int(round(p.range_mi))
    for combo in itertools.product(range(R + 1), repeat=p.n):
        purchases = [Purchase(i, p.miles[i], p.prices[i], float(b)) for i, b in enumerate(combo)]
        try:
            cost, _ = validate_plan(p, purchases)
        except PlanInvalid:
            continue
        best = min(best, cost)
    return best
