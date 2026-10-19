"""Shared fixtures: a USA box, two cities, stations at known route miles, and a mocked provider."""

from decimal import Decimal

import httpx
import numpy as np
import pytest
from django.contrib.gis.geos import MultiPolygon, Point, Polygon
from django.core.cache import cache

from apps.geo.models import Country
from apps.geo.services import reset_usa_cache
from apps.routing import providers
from apps.routing.station_index import clear_index
from apps.stations.models import Place, Station
from tests.routing.helpers import meandering_route, point_beside

WAYPOINTS = [(40.71, -74.0), (40.44, -80.0), (39.77, -86.16), (38.63, -90.2), (35.47, -97.52)]


@pytest.fixture
def route():
    return meandering_route(waypoints=WAYPOINTS)


@pytest.fixture
def world(db, route, settings):
    """USA box, two cities, and stations at known route miles: cheap at 400, 1000, 1500."""
    settings.ROUTING_PROVIDER = "osrm"
    cache.clear()
    clear_index()
    reset_usa_cache()
    box = Polygon.from_bbox((-125, 24, -66, 49))
    Country.objects.create(name="USA", iso_a3="USA", geom=MultiPolygon(box, srid=4326))
    Place.objects.create(name="NEW YORK", state="NY", location=Point(-74.0, 40.71, srid=4326))
    Place.objects.create(name="OKLAHOMA CITY", state="OK", location=Point(-97.52, 35.47, srid=4326))

    lat, lon, cum = route
    spec = [
        (400, 3.00, 0.5, "geocoded"),
        (700, 4.50, 0.2, "geocoded"),
        (1000, 3.20, 1.0, "geocoded"),
        (1500, 3.10, 0.3, "geocoded"),
        (1800, 4.00, 0.0, "geocoded"),
        (1300, 2.00, 4.0, "city_centroid"),
    ]
    for i, (mile, price, off, source) in enumerate(spec):
        plat, plon = point_beside(lat, lon, cum, mile, off)
        Station.objects.create(
            station_key=f"k{i}",
            name=f"STATION {i}",
            address="X",
            city="C",
            state="OH",
            price=Decimal(str(price)),
            location=Point(float(plon), float(plat), srid=4326),
            geocode_source=source,
        )
    yield {"cum": cum}
    clear_index()
    reset_usa_cache()
    cache.clear()


@pytest.fixture
def provider(monkeypatch, route, settings):
    """Mock OSRM. Records every outgoing call so tests can assert on the call count."""
    settings.ROUTING_PROVIDER = "osrm"
    settings.ROUTING_PROVIDER = "osrm"
    lat, lon, cum = route
    calls = []
    state = {"status": 200, "code": "Ok"}

    def handler(request):
        calls.append(request.url)
        if state["status"] != 200:
            return httpx.Response(state["status"], json={})
        if state["code"] != "Ok":
            return httpx.Response(200, json={"code": state["code"]})
        coords = np.c_[lon, lat][::25].tolist() + [[float(lon[-1]), float(lat[-1])]]
        return httpx.Response(
            200,
            json={
                "code": "Ok",
                "routes": [
                    {"distance": float(cum[-1]) * 1609.344, "geometry": {"coordinates": coords}}
                ],
            },
        )

    monkeypatch.setattr(
        providers, "_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )
    state["calls"] = calls
    return state
