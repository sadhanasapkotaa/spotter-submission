"""Algorithm W (production): per-mile sliding-window minimum.

Mile x in (S0, D] is paid for at the cheapest price among stations in [x - R, x). The windows
change only at station miles and station miles + R, so between those breakpoints the cheapest
station is constant. A monotonic deque keeps it in O(1) amortised: O(n log n) total (sorting
breakpoints), exact, no tuning, and it comes with its own optimality proof (see contract.py).
"""

from __future__ import annotations

from collections import deque

from .contract import Infeasible, Plan, Problem, Purchase, require_feasible


def plan_window(p: Problem) -> Plan:
    if p.distance <= p.start_mi:
        return Plan((), 0.0, "window")
    require_feasible(p)

    R, D, S0 = p.range_mi, p.distance, p.start_mi
    points = {S0, D}
    for m in p.miles:
        if S0 < m < D:
            points.add(m)
        if S0 < m + R < D:
            points.add(m + R)
    ordered = sorted(points)

    window: deque[int] = deque()  # station indices, prices strictly increasing front -> back
    nxt = 0
    bought = [0.0] * p.n
    for a, b in zip(ordered, ordered[1:], strict=False):
        while nxt < p.n and p.miles[nxt] <= a:
            while window and p.prices[window[-1]] >= p.prices[nxt]:
                window.pop()  # older and not cheaper: can never be the best again
            window.append(nxt)
            nxt += 1
        while window and p.miles[window[0]] + R < b:
            window.popleft()  # out of range for this stretch
        if not window:
            raise Infeasible(a)
        bought[window[0]] += b - a

    purchases = tuple(
        Purchase(i, p.miles[i], p.prices[i], bought[i]) for i in range(p.n) if bought[i] > 0
    )
    return Plan(purchases, sum(pu.cost(p.mpg) for pu in purchases), "window")
