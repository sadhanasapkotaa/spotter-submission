"""Orchestrates one trip: route -> stations along it -> optimal fuel plan -> response dict."""

from __future__ import annotations

import time
from decimal import ROUND_HALF_UP, Decimal
from urllib.parse import quote

import numpy as np
from django.conf import settings

from .corridor import build_route, haversine_mi, locate_stations
from .errors import InvalidRequest, NoFeasiblePlan, NotConfigured
from .locations import Location
from .planner import Infeasible, make_problem, plan_fuel, validate_plan
from .providers import fetch_route
from .station_index import get_index

CENT = Decimal("0.01")
MILLI = Decimal("0.001")


def _dec(x: float, q: Decimal) -> Decimal:
    return Decimal(repr(float(x))).quantize(q, rounding=ROUND_HALF_UP)


def _thin(coords, step_mi: float = 0.5) -> list:
    """Display geometry: roughly one vertex per `step_mi`, 5 decimals (about 1 m)."""
    arr = np.asarray([(c[0], c[1]) for c in coords], dtype=float)
    seg = haversine_mi(arr[:-1, 1], arr[:-1, 0], arr[1:, 1], arr[1:, 0])
    cum = np.r_[0.0, np.cumsum(seg)]
    keep = np.unique(np.r_[np.searchsorted(cum, np.arange(0.0, cum[-1], step_mi)), len(arr) - 1])
    return [[round(float(arr[i, 0]), 5), round(float(arr[i, 1]), 5)] for i in keep]


def plan_trip(
    start: Location,
    end: Location,
    *,
    start_fuel_gallons: float | None = None,
    exclude_approximate: bool = False,
) -> dict:
    t0 = time.perf_counter()
    range_mi, mpg = float(settings.VEHICLE_RANGE_MI), float(settings.VEHICLE_MPG)
    capacity_gal = range_mi / mpg
    start_gal = capacity_gal if start_fuel_gallons is None else float(start_fuel_gallons)
    if not (0 <= start_gal <= capacity_gal):
        raise InvalidRequest(f"start_fuel_gallons must be between 0 and {capacity_gal:g}")

    # 1. The one external call (cached by rounded endpoints).
    rd = fetch_route((start.lat, start.lng), (end.lat, end.lng))
    t_route = time.perf_counter()

    try:
        route = build_route(rd.coords)
    except ValueError:
        raise InvalidRequest("start and end are the same place") from None
    if route.length_mi < 0.1:
        raise InvalidRequest("start and end are the same place")
    distance = route.length_mi

    # 2. Where are the stations relative to this route?
    index = get_index()
    if len(index) == 0:
        raise NotConfigured(
            "No geocoded stations are loaded. Run: make import-stations && make geocode"
        )
    near, far = float(settings.ROUTING_CORRIDOR_MI), float(settings.ROUTING_CENTROID_CORRIDOR_MI)
    limits = np.where(index.approx, -1.0 if exclude_approximate else far, near)
    found = locate_stations(route, index.lat, index.lon, limits)
    t_locate = time.perf_counter()

    # 3. Plan. A station `offset` miles off the road costs 2*offset extra miles of fuel. Plan with a
    #    reserve so a detour can never strand the vehicle: capacity shrinks by 2*reserve and the
    #    starting fuel by `reserve`; the detour fuel is bought (and paid for) at the stop.
    reserve = near if exclude_approximate else max(near, far)
    plan_range = range_mi - 2 * reserve
    plan_start = min(max(start_gal * mpg - reserve, 0.0), plan_range)
    prices = index.price[found.index]
    problem = make_problem(
        zip(found.mile.tolist(), prices.tolist(), strict=True),
        distance,
        range_mi=plan_range,
        start_mi=plan_start,
        mpg=mpg,
    )
    try:
        plan = plan_fuel(problem)
    except Infeasible as exc:
        lat = float(np.interp(exc.at_mile, route.cum_mi, route.lat))
        lng = float(np.interp(exc.at_mile, route.cum_mi, route.lon))
        raise NoFeasiblePlan(
            f"No fuel station within range after about mile {exc.at_mile:.0f} of {distance:.0f}.",
            at_mile=round(exc.at_mile, 1),
            near={"lat": round(lat, 5), "lng": round(lng, 5)},
        ) from exc
    validate_plan(
        problem, plan.purchases
    )  # the referee: never ship a plan that breaks the tank rules
    t_plan = time.perf_counter()

    # 4. Money, at the edge, in Decimal. The total is the sum of the displayed per-stop costs.
    stops, total_cost, total_gal = [], Decimal("0"), Decimal("0")
    for pu in plan.purchases:
        k = problem.source_index[pu.index]  # position within `found`
        si = int(found.index[k])  # position within the station index
        offset = float(found.offset_mi[k])
        detour_gal = _dec(2 * offset / mpg, MILLI)
        gallons = _dec(pu.miles_bought / mpg, MILLI) + detour_gal
        price = _dec(index.price[si], Decimal("0.0001"))
        cost = (gallons * price).quantize(CENT, rounding=ROUND_HALF_UP)
        key, name, address, city, state, _source = index.meta[si]
        stops.append(
            {
                "station_id": key,
                "name": name,
                "address": address,
                "city": city,
                "state": state,
                "location": {
                    "lat": round(float(index.lat[si]), 6),
                    "lng": round(float(index.lon[si]), 6),
                },
                "position_quality": "approximate_city_centroid" if index.approx[si] else "geocoded",
                "route_mile": round(pu.mile, 1),
                "offset_miles": round(offset, 2),
                "price_per_gallon": str(price),
                "gallons": str(gallons),
                "detour_gallons": str(detour_gal),
                "cost": str(cost),
            }
        )
        total_cost += cost
        total_gal += gallons

    consumed = _dec(distance / mpg, MILLI)
    return {
        "distance_miles": round(distance, 1),
        "fuel_gallons_consumed": str(consumed),
        "total_fuel_cost": str(total_cost.quantize(CENT)),
        "currency": "USD",
        "fuel_gallons_purchased": str(total_gal),
        "fuel_stops": stops,
        "route": {
            "type": "Feature",
            "properties": {
                "provider": rd.provider,
                "provider_distance_miles": round(rd.provider_distance_mi, 1),
            },
            "geometry": {"type": "LineString", "coordinates": _thin(rd.coords)},
        },
        "start": {"lat": start.lat, "lng": start.lng},
        "end": {"lat": end.lat, "lng": end.lng},
        "assumptions": {
            "vehicle_range_miles": range_mi,
            "miles_per_gallon": mpg,
            "start_fuel_gallons": start_gal,
            "start_fuel_is_free": True,
            "tank_may_reach_empty_between_stops": True,
            "station_corridor_miles": {
                "geocoded": near,
                "approximate_city_centroid": None if exclude_approximate else far,
            },
            "detour_policy": "stations off the road cost 2 x offset extra miles of fuel, bought at that stop and included in cost",
            "detour_reserve_miles": reserve,
            "algorithm": plan.algorithm,
            "stations_considered": int(len(found.index)),
        },
        "timings_ms": {
            "route_provider": round((t_route - t0) * 1000, 1),
            "locate_stations": round((t_locate - t_route) * 1000, 1),
            "plan": round((t_plan - t_locate) * 1000, 1),
            "total": round((time.perf_counter() - t0) * 1000, 1),
            "route_cached": rd.cached,
        },
        "map_url": f"/api/route/map/?start={quote(start.label)}&end={quote(end.label)}",
    }
