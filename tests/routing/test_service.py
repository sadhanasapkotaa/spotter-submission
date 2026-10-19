from decimal import Decimal

import httpx
import pytest

from apps.routing import providers
from apps.routing.errors import InvalidRequest, NoFeasiblePlan, NotConfigured
from apps.routing.locations import Location
from apps.routing.service import plan_trip

START = Location(40.71, -74.0, "start")
END = Location(35.47, -97.52, "end")


def test_total_is_the_sum_of_the_displayed_stop_costs(world, provider):
    result = plan_trip(START, END)
    assert result["fuel_stops"]
    assert Decimal(result["total_fuel_cost"]) == sum(
        Decimal(s["cost"]) for s in result["fuel_stops"]
    )


def test_one_routing_call_per_trip(world, provider):
    plan_trip(START, END)
    assert len(provider["calls"]) == 1


def test_same_start_and_end_is_rejected(world, provider, monkeypatch):
    body = {
        "code": "Ok",
        "routes": [
            {"distance": 0.0, "geometry": {"coordinates": [[-74.0, 40.71], [-74.0, 40.71]]}}
        ],
    }
    monkeypatch.setattr(
        providers,
        "_client",
        lambda: httpx.Client(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body))
        ),
    )
    with pytest.raises(InvalidRequest):
        plan_trip(START, START)


def test_start_fuel_outside_the_tank_is_rejected(world, provider):
    with pytest.raises(InvalidRequest):
        plan_trip(START, END, start_fuel_gallons=51)


def test_an_empty_tank_with_no_station_at_the_start_has_no_feasible_plan(world, provider):
    with pytest.raises(NoFeasiblePlan):
        plan_trip(START, END, start_fuel_gallons=0)


def test_no_stations_loaded_means_service_not_ready(db, provider, route):
    with pytest.raises(NotConfigured):
        plan_trip(START, END)
