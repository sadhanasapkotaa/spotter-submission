"""Compare fuel-planning algorithms. Run: python scripts/compare_planners.py [--save [FILE]]

--save also writes the report to FILE (default docs/benchmarks.txt) so a run can be committed.

Correctness: every method vs the slow reference solvers on thousands of random trips.
Speed:       realistic and adversarial sizes (stations inside the corridor of one route).
"""

import argparse
import os
import platform
import random
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")

from apps.routing.planner import (  # noqa: E402
    first_uncovered_mile,
    make_problem,
    plan_greedy,
    plan_window,
)
from apps.routing.planner.graph import cost_naive_station_graph, cost_state_graph  # noqa: E402
from apps.routing.planner.oracle import cost_brute_force, cost_grid_dp  # noqa: E402


def feasible_instances(rng, count, n, R):
    out = []
    while len(out) < count:
        dist, start = rng.randint(1, R * 4), rng.randint(0, R)
        stations = [(rng.randint(0, max(0, dist - 1)), rng.randint(1, 10)) for _ in range(n)]
        p = make_problem(stations, dist, range_mi=R, start_mi=start, mpg=10)
        if first_uncovered_mile(p) is None:
            out.append(p)
    return out


def close(a, b):
    return abs(a - b) <= 1e-7 * max(1.0, abs(a), abs(b))


def correctness():
    rng = random.Random(2026)
    tiny = feasible_instances(rng, 300, 3, 5)
    print("== CORRECTNESS ==")
    print(
        "oracle check (300 tiny trips): brute force vs grid DP mismatches =",
        sum(not close(cost_brute_force(p), cost_grid_dp(p)) for p in tiny),
    )
    methods = {
        "window DP (production)": lambda p: plan_window(p).cost,
        "greedy next-cheaper": lambda p: plan_greedy(p).cost,
        "state graph (Dijkstra)": cost_state_graph,
        "naive station graph": cost_naive_station_graph,
    }
    instances = feasible_instances(rng, 3000, 12, 30)
    print("\n3000 random trips (12 stations, range 30) vs the grid-DP optimum:")
    print(f"{'method':26} {'optimal':>8} {'worse':>7} {'avg overpay':>12} {'worst overpay':>14}")
    for name, fn in methods.items():
        ok, over = 0, []
        for p in instances:
            opt, got = cost_grid_dp(p), fn(p)
            if close(opt, got):
                ok += 1
            else:
                over.append((got - opt) / opt if opt else float("inf"))
        avg = f"{100 * statistics.mean(over):.1f}%" if over else "-"
        mx = f"{100 * max(over):.1f}%" if over else "-"
        print(f"{name:26} {ok:8d} {len(over):7d} {avg:>12} {mx:>14}")


def speed_all_methods():
    """All four methods on a small trip: the state graph needs integer miles and O(n*R) states."""
    rng = random.Random(4)
    n, dist = 150, 1500
    st = [(rng.randint(0, dist - 1), rng.randint(290, 440) / 100) for _ in range(n)]
    p = make_problem(st, dist)
    while first_uncovered_mile(p) is not None:  # keep the draw feasible
        st = [(rng.randint(0, dist - 1), rng.randint(290, 440) / 100) for _ in range(n)]
        p = make_problem(st, dist)
    print(f"\n== SPEED, ALL METHODS ({n} stations, {dist} mile route, range 500) ==")
    print(f"{'method':26} {'ms':>10} {'cost $':>10}")
    methods = {
        "window DP (production)": lambda: plan_window(p).cost,
        "greedy next-cheaper": lambda: plan_greedy(p).cost,
        "state graph (Dijkstra)": lambda: cost_state_graph(p),
        "naive station graph": lambda: cost_naive_station_graph(p),
    }
    for name, fn in methods.items():
        t = time.perf_counter()
        cost = fn()
        print(f"{name:26} {(time.perf_counter() - t) * 1000:10.1f} {cost:10.2f}")


def speed():
    rng = random.Random(3)
    n = 20000
    cases = {
        "random prices": [(rng.uniform(0, 2800), rng.uniform(2.9, 4.4)) for _ in range(n)],
        "prices rising along route": [(i * 2800 / n, 2.9 + 1.5 * i / n) for i in range(n)],
        "prices falling along route": [(i * 2800 / n, 4.4 - 1.5 * i / n) for i in range(n)],
    }
    print(f"\n== SPEED ({n:,} stations, 2,800 mile route) ==")
    print(f"{'case':30} {'window ms':>10} {'greedy ms':>10}")
    for name, st in cases.items():
        p = make_problem(st, 2800)
        row = []
        for fn in (plan_window, plan_greedy):
            t = time.perf_counter()
            fn(p)
            row.append((time.perf_counter() - t) * 1000)
        print(f"{name:30} {row[0]:10.1f} {row[1]:10.1f}")


class Tee:
    """Write to the terminal and, when asked, to a file."""

    def __init__(self, *streams):
        self.streams = streams

    def write(self, text):
        for stream in self.streams:
            stream.write(text)

    def flush(self):
        for stream in self.streams:
            stream.flush()


def report():
    print(f"python {platform.python_version()} on {platform.machine()}, {platform.system()}\n")
    correctness()
    speed_all_methods()
    speed()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--save", nargs="?", const="docs/benchmarks.txt", metavar="FILE")
    args = parser.parse_args()
    if args.save:
        with open(args.save, "w", encoding="utf-8") as fh:
            real, sys.stdout = sys.stdout, Tee(sys.stdout, fh)
            try:
                report()
            finally:
                sys.stdout = real
        print(f"\nSaved to {args.save}")
    else:
        report()
