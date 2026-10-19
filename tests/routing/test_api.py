"""End-to-end API tests on real PostGIS, with the routing provider mocked."""

from decimal import Decimal

import httpx
import pytest

from apps.routing import providers
from apps.routing.station_index import clear_index
from apps.stations.models import Station


def get(client, start="40.71,-74.0", end="35.47,-97.52", **extra):
    return client.get("/api/route/", {"start": start, "end": end, **extra})


def test_returns_route_stops_and_total_cost(client, world, provider):
    r = get(client)
    assert r.status_code == 200, r.content
    d = r.json()
    assert d["distance_miles"] == pytest.approx(world["cum"][-1], abs=1)
    assert d["route"]["geometry"]["type"] == "LineString"
    assert len(d["fuel_stops"]) >= 1
    # Total is exactly the sum of the displayed per-stop costs.
    assert Decimal(d["total_fuel_cost"]) == sum(Decimal(s["cost"]) for s in d["fuel_stops"])
    # Gallons bought cover the miles beyond the starting tank (plus small detour fuel).
    needed = d["distance_miles"] / 10 - 50
    assert float(d["fuel_gallons_purchased"]) == pytest.approx(needed, abs=2.5)
    assert (
        d["assumptions"]["miles_per_gallon"] == 10
        and d["assumptions"]["vehicle_range_miles"] == 500
    )


def test_plan_beats_a_naive_fill_at_the_nearest_station(client, world, provider):
    d = get(client).json()
    paid = Decimal(d["total_fuel_cost"])
    worst_case = Decimal(
        str((d["distance_miles"] / 10 - 50) * 4.50)
    )  # everything at the dearest price
    assert paid < worst_case
    cheapest_prices = sorted(Decimal(s["price_per_gallon"]) for s in d["fuel_stops"])
    assert cheapest_prices[0] <= Decimal("3.20")


def test_one_provider_call_then_cached(client, world, provider):
    first = get(client).json()
    second = get(client).json()
    assert len(provider["calls"]) == 1
    assert (
        first["timings_ms"]["route_cached"] is False
        and second["timings_ms"]["route_cached"] is True
    )
    assert first["total_fuel_cost"] == second["total_fuel_cost"]


def test_exclude_approximate_ignores_city_centroid_stations(client, world, provider):
    with_all = get(client).json()
    only_exact = get(client, exclude_approximate="true").json()
    assert all(s["position_quality"] == "geocoded" for s in only_exact["fuel_stops"])
    assert (
        only_exact["assumptions"]["stations_considered"]
        < with_all["assumptions"]["stations_considered"]
    )


def test_city_names_resolve_locally_without_geocoding_calls(client, world, provider):
    r = get(client, start="New York, NY", end="Oklahoma City, OK")
    assert r.status_code == 200
    assert len(provider["calls"]) == 1  # only the routing call; no geocoder


@pytest.mark.parametrize(
    "start,end,who",
    [
        ("51.5074,-0.1278", "35.47,-97.52", ["start"]),
        ("40.71,-74.0", "19.43,-99.13", ["end"]),
        ("51.5,-0.12", "19.43,-99.13", ["start", "end"]),
    ],
)
def test_locations_outside_the_usa_are_rejected_before_any_routing_call(
    client, world, provider, start, end, who
):
    r = get(client, start=start, end=end)
    assert r.status_code == 422
    assert r.json()["error"] == "outside_usa" and r.json()["outside"] == who
    assert provider["calls"] == []


@pytest.mark.parametrize(
    "params",
    [
        {"start": "nonsense", "end": "35,-97"},
        {"start": "95,10", "end": "35,-97"},
        {"start": "Atlantis, ZZ", "end": "35,-97"},
        {"end": "35,-97"},
    ],
)
def test_bad_input_is_a_400(client, world, provider, params):
    assert client.get("/api/route/", params).status_code == 400
    assert provider["calls"] == []


def test_post_with_json_body_works(client, world, provider):
    r = client.post(
        "/api/route/",
        {"start": {"lat": 40.71, "lng": -74.0}, "end": "35.47,-97.52"},
        content_type="application/json",
    )
    assert r.status_code == 200


def test_same_start_and_end_is_a_400(client, world, provider, route, monkeypatch):
    monkeypatch.setattr(
        providers,
        "_client",
        lambda: httpx.Client(
            transport=httpx.MockTransport(
                lambda req: httpx.Response(
                    200,
                    json={
                        "code": "Ok",
                        "routes": [
                            {
                                "distance": 0.0,
                                "geometry": {"coordinates": [[-74.0, 40.71], [-74.0, 40.71]]},
                            }
                        ],
                    },
                )
            )
        ),
    )
    assert get(client, start="40.71,-74.0", end="40.71,-74.0").status_code == 400


def test_provider_server_error_is_a_502_after_one_retry(client, world, provider):
    provider["status"] = 500
    r = get(client)
    assert r.status_code == 502 and r.json()["error"] == "routing_provider_unavailable"
    assert len(provider["calls"]) == 2


def test_no_route_is_a_422(client, world, provider):
    provider["code"] = "NoRoute"
    assert get(client).status_code == 422


def test_no_stations_in_range_reports_where_fuel_runs_out(client, world, provider):
    Station.objects.filter(
        station_key__in=["k0", "k1", "k2"]
    ).delete()  # leaves a gap after mile 0-500
    Station.objects.update(updated_at=Station.objects.first().updated_at)
    clear_index()
    r = get(client)
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "no_feasible_fuel_plan" and 0 < body["at_mile"] < 700 and "near" in body


def test_short_trip_inside_the_starting_tank_costs_nothing(client, world, provider, monkeypatch):
    monkeypatch.setattr(
        providers,
        "_client",
        lambda: httpx.Client(
            transport=httpx.MockTransport(
                lambda req: httpx.Response(
                    200,
                    json={
                        "code": "Ok",
                        "routes": [
                            {
                                "distance": 160934.0,
                                "geometry": {
                                    "coordinates": [[-74.0, 40.71], [-75.0, 40.0], [-76.0, 39.7]]
                                },
                            }
                        ],
                    },
                )
            )
        ),
    )
    d = get(client, end="39.7,-76.0").json()
    assert d["total_fuel_cost"] == "0.00" and d["fuel_stops"] == []


def test_start_fuel_is_validated(client, world, provider):
    assert get(client, start_fuel_gallons=80).status_code == 400
    full, empty = get(client).json(), get(client, start_fuel_gallons=45).json()
    assert Decimal(empty["total_fuel_cost"]) > Decimal(full["total_fuel_cost"])


def test_map_page_renders(client, db):
    r = client.get("/api/route/map/")
    assert r.status_code == 200 and b"leaflet" in r.content.lower()
