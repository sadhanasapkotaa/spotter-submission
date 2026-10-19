from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.routing.locations import Location
from apps.routing.management.commands.compare_trip import build_problem
from apps.routing.planner import plan_window
from apps.routing.service import plan_trip

START = Location(40.71, -74.0, "start")
END = Location(35.47, -97.52, "end")


def test_report_lists_every_method_and_the_exact_ones_agree(world, provider, tmp_path):
    out, report = StringIO(), tmp_path / "report.md"
    call_command("compare_trip", "New York, NY", "Oklahoma City, OK", "--save", report, stdout=out)
    text = report.read_text()
    for method in ("window DP", "greedy", "naive station graph", "grid DP", "state graph"):
        assert method in text
    assert "They agree." in text
    assert "Trip comparison: New York, NY to Oklahoma City, OK" in out.getvalue()


def test_the_report_solves_the_same_problem_the_api_solves(world, provider):
    problem, _ = build_problem(START, END)
    api_miles = {s["route_mile"] for s in plan_trip(START, END)["fuel_stops"]}
    assert {round(pu.mile, 1) for pu in plan_window(problem).purchases} == api_miles


def test_a_bad_location_is_a_command_error(world, provider):
    with pytest.raises(CommandError, match="invalid_location"):
        call_command("compare_trip", "nowhere", "Oklahoma City, OK")
