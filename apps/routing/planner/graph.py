"""Algorithms N and S: shortest-path formulations (shown for comparison; not for production).

N (naive station graph): nodes are stations, edge i -> j costs p_i * (m_j - m_i)/mpg, meaning
"fill exactly enough at i to reach j empty". It is NOT optimal: it can't carry cheap fuel past a
dearer station. Kept to show why the fuel level has to be part of the state.

S (state graph): nodes are (station, fuel level), edges are "buy one unit" and "drive to the next
station". Exact, but needs integer miles and costs O(n * R) states. This is a test oracle.
"""

from __future__ import annotations

import heapq
import math

from .contract import Problem, require_feasible


def cost_naive_station_graph(p: Problem) -> float:
    if p.distance <= p.start_mi:
        return 0.0
    require_feasible(p)
    R = p.range_mi
    miles = [*p.miles, p.distance]
    n = p.n
    dist = [math.inf] * (n + 1)
    heap: list[tuple[float, int]] = []
    for k in range(n):  # the starting fuel is free, but whatever is left on arrival is wasted
        if miles[k] <= p.start_mi:
            dist[k] = 0.0
            heap.append((0.0, k))
    heapq.heapify(heap)
    while heap:
        d, i = heapq.heappop(heap)
        if d > dist[i]:
            continue
        if i == n:
            return d
        for j in range(i + 1, n + 1):
            leg = miles[j] - miles[i]
            if leg > R:
                break
            nd = d + p.prices[i] * leg / p.mpg
            if nd < dist[j]:
                dist[j] = nd
                heapq.heappush(heap, (nd, j))
    return math.inf


def cost_state_graph(p: Problem) -> float:
    """Dijkstra over (station, integer fuel). Requires integer miles/range/start."""
    for v in (*p.miles, p.distance, p.range_mi, p.start_mi):
        if abs(v - round(v)) > 1e-9:
            raise ValueError("state graph needs integer miles")
    if p.distance <= p.start_mi:
        return 0.0
    R, S0 = int(round(p.range_mi)), int(round(p.start_mi))
    miles = [int(round(m)) for m in p.miles] + [int(round(p.distance))]
    n = p.n
    if miles[0] > S0:
        return math.inf
    heap = [(0.0, 0, S0 - miles[0])]
    best: dict[tuple[int, int], float] = {(0, S0 - miles[0]): 0.0}
    while heap:
        d, i, f = heapq.heappop(heap)
        if d > best.get((i, f), math.inf):
            continue
        if i == n:
            return d
        if f < R:  # buy one mile of fuel
            nd = d + p.prices[i] / p.mpg
            if nd < best.get((i, f + 1), math.inf):
                best[(i, f + 1)] = nd
                heapq.heappush(heap, (nd, i, f + 1))
        gap = miles[i + 1] - miles[i]  # drive to the next station
        if f >= gap and d < best.get((i + 1, f - gap), math.inf):
            best[(i + 1, f - gap)] = d
            heapq.heappush(heap, (d, i + 1, f - gap))
    return math.inf
