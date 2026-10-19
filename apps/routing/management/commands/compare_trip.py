"""Run one real trip through every planning algorithm and report cost, speed and agreement.

    make compare-trip ARGS='"New York, NY" "Chicago, IL" --save docs/trip_report.md'

Steps 1-3 mirror `service.plan_trip` (same route, same stations, same planner inputs), so every
algorithm sees exactly the problem the API solves. A test checks that the two stay in agreement.
"""

from __future__ import annotations

import time
from datetime import date

import numpy as np
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.routing.corridor import build_route, locate_stations
from apps.routing.errors import TripError
from apps.routing.locations import parse_location, require_in_usa
from apps.routing.planner import (
    Infeasible,
    make_problem,
    plan_greedy,
    plan_window,
    validate_plan,
)
from apps.routing.planner.graph import cost_naive_station_graph, cost_state_graph
from apps.routing.planner.oracle import cost_grid_dp
from apps.routing.providers import fetch_route
from apps.routing.station_index import get_index


def build_problem(start, end, *, start_fuel_gallons=None, exclude_approximate=False):
    """The planner input for a trip, built the same way `plan_trip` builds it."""
    range_mi, mpg = float(settings.VEHICLE_RANGE_MI), float(settings.VEHICLE_MPG)
    start_gal = range_mi / mpg if start_fuel_gallons is None else float(start_fuel_gallons)
    rd = fetch_route((start.lat, start.lng), (end.lat, end.lng))
    route = build_route(rd.coords)
    index = get_index()
    near = float(settings.ROUTING_CORRIDOR_MI)
    far = float(settings.ROUTING_CENTROID_CORRIDOR_MI)
    limits = np.where(index.approx, -1.0 if exclude_approximate else far, near)
    found = locate_stations(route, index.lat, index.lon, limits)
    reserve = near if exclude_approximate else max(near, far)
    plan_range = range_mi - 2 * reserve
    plan_start = min(max(start_gal * mpg - reserve, 0.0), plan_range)
    problem = make_problem(
        zip(found.mile.tolist(), index.price[found.index].tolist(), strict=True),
        route.length_mi,
        range_mi=plan_range,
        start_mi=plan_start,
        mpg=mpg,
    )
    return problem, rd


def rounded(problem):
    """The same trip on a 1-mile grid, which the grid-DP and state-graph solvers require."""
    return make_problem(
        zip([round(m) for m in problem.miles], problem.prices, strict=True),
        round(problem.distance),
        range_mi=round(problem.range_mi),
        start_mi=round(problem.start_mi),
        mpg=problem.mpg,
    )


def _timed(fn, *args):
    t = time.perf_counter()
    out = fn(*args)
    return out, (time.perf_counter() - t) * 1000


def _row(name, cost, ms, stops, base, note=""):
    diff = "-" if base is None else f"{cost - base:+.2f}"
    return [name, f"{cost:.2f}", diff, f"{ms:.1f}", "-" if stops is None else str(stops), note]


def _table(header, rows):
    widths = [max(len(str(r[i])) for r in [header, *rows]) for i in range(len(header))]

    def line(cells):
        return "| " + " | ".join(str(c).ljust(w) for c, w in zip(cells, widths, strict=True)) + " |"

    rule = "|" + "|".join("-" * (w + 2) for w in widths) + "|"
    return "\n".join([line(header), rule, *[line(r) for r in rows]])


class Command(BaseCommand):
    help = "Run one real trip through every planning algorithm and compare the results."

    def add_arguments(self, parser):
        parser.add_argument("start")
        parser.add_argument("end")
        parser.add_argument("--start-fuel-gallons", type=float)
        parser.add_argument("--exclude-approximate", action="store_true")
        parser.add_argument("--save", nargs="?", const="docs/trip_report.md", metavar="FILE")

    def handle(self, *args, **opts):
        try:
            start = parse_location(opts["start"], "start")
            end = parse_location(opts["end"], "end")
            require_in_usa(start=start, end=end)
            problem, rd = build_problem(
                start,
                end,
                start_fuel_gallons=opts["start_fuel_gallons"],
                exclude_approximate=opts["exclude_approximate"],
            )
        except TripError as exc:
            raise CommandError(f"{exc.code}: {exc.message}") from exc

        try:
            window, w_ms = _timed(plan_window, problem)
            greedy, g_ms = _timed(plan_greedy, problem)
        except Infeasible as exc:
            raise CommandError(
                f"no feasible plan: fuel runs out at mile {exc.at_mile:.0f}"
            ) from exc
        for plan in (window, greedy):
            validate_plan(problem, plan.purchases)  # the referee checks both plans
        naive, n_ms = _timed(cost_naive_station_graph, problem)

        grid = rounded(problem)
        gw, gw_ms = _timed(plan_window, grid)
        gg, gg_ms = _timed(plan_greedy, grid)
        sg, sg_ms = _timed(cost_state_graph, grid)
        dp, dp_ms = _timed(cost_grid_dp, grid)

        real_rows = [
            _row("window DP (production)", window.cost, w_ms, len(window.purchases), window.cost),
            _row("greedy next-cheaper", greedy.cost, g_ms, len(greedy.purchases), window.cost),
            _row("naive station graph", naive, n_ms, None, window.cost, "ignores fuel carried"),
        ]
        grid_rows = [
            _row("grid DP (oracle)", dp, dp_ms, None, dp),
            _row("state graph (Dijkstra)", sg, sg_ms, None, dp),
            _row("window DP (production)", gw.cost, gw_ms, len(gw.purchases), dp),
            _row("greedy next-cheaper", gg.cost, gg_ms, len(gg.purchases), dp),
        ]
        exact = max(abs(gw.cost - dp), abs(sg - dp), abs(gg.cost - dp))
        header = ["method", "cost $", "vs best", "ms", "stops", "note"]
        report = "\n".join(
            [
                f"# Trip comparison: {start.label} to {end.label}",
                "",
                f"Generated {date.today().isoformat()}. Route from `{rd.provider}`: "
                f"{problem.distance:.1f} mi. Stations in the corridor: {problem.n}. "
                f"Tank {problem.range_mi:g} mi (after the detour reserve), start fuel "
                f"{problem.start_mi:g} mi (free), {problem.mpg:g} mpg.",
                "",
                "Costs are the planner's fuel cost for the stops chosen, before the detour fuel "
                "that the API adds. 'vs best' is the difference from the first row.",
                "",
                "## Real route miles",
                "",
                _table(header, real_rows),
                "",
                "## Same trip on a 1-mile grid (what the oracle and the state graph need)",
                "",
                _table(header, grid_rows),
                "",
                f"Largest gap between the exact methods: ${exact:.6f}. "
                + ("They agree." if exact < 1e-6 else "THEY DISAGREE: investigate."),
                "",
            ]
        )
        self.stdout.write(report)
        if opts["save"]:
            with open(opts["save"], "w", encoding="utf-8") as fh:
                fh.write(report)
            self.stdout.write(self.style.SUCCESS(f"Saved to {opts['save']}"))
