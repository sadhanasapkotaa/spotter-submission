"""Routing providers: request shape, error mapping, caching. No network; httpx MockTransport."""

import json

import httpx
import pytest
from django.core.cache import cache

from apps.routing import providers
from apps.routing.errors import NotConfigured, ProviderTimeout, ProviderUnavailable, RouteNotFound
from apps.routing.providers import fetch_route

A, B = (40.71, -74.0), (35.47, -97.52)  # (lat, lng)
ORS_OK = {
    "features": [
        {
            "geometry": {"coordinates": [[-74.0, 40.71], [-97.52, 35.47]]},
            "properties": {"summary": {"distance": 3218688.0}},
        }
    ]
}


@pytest.fixture(autouse=True)
def _clean(settings):
    cache.clear()
    settings.ROUTING_PROVIDER = "ors"
    settings.ORS_API_KEY = "test-key"
    yield
    cache.clear()


def use(monkeypatch, handler):
    calls = []

    def wrapped(request):
        calls.append(request)
        return handler(request)

    monkeypatch.setattr(
        providers, "_client", lambda: httpx.Client(transport=httpx.MockTransport(wrapped))
    )
    return calls


def test_ors_request_is_one_post_with_lng_lat_order_and_key(monkeypatch):
    calls = use(monkeypatch, lambda r: httpx.Response(200, json=ORS_OK))
    rd = fetch_route(A, B)
    assert len(calls) == 1
    req = calls[0]
    assert req.method == "POST" and req.headers["Authorization"] == "test-key"
    body = json.loads(req.content)
    assert body["coordinates"] == [[-74.0, 40.71], [-97.52, 35.47]]  # lng, lat
    assert body["instructions"] is False
    assert rd.provider_distance_mi == pytest.approx(2000, rel=1e-3)


def test_second_identical_request_never_hits_the_provider(monkeypatch):
    calls = use(monkeypatch, lambda r: httpx.Response(200, json=ORS_OK))
    first, second = fetch_route(A, B), fetch_route(A, B)
    assert len(calls) == 1 and not first.cached and second.cached


def test_nearby_start_points_share_a_cache_entry_only_when_equal_at_3_decimals(monkeypatch):
    calls = use(monkeypatch, lambda r: httpx.Response(200, json=ORS_OK))
    fetch_route((40.7100, -74.0), B)
    fetch_route((40.71004, -74.0), B)  # same at 3 decimals (~100 m)
    fetch_route((40.7200, -74.0), B)  # different
    assert len(calls) == 2


def test_missing_key_is_not_configured(monkeypatch, settings):
    settings.ORS_API_KEY = ""
    use(monkeypatch, lambda r: httpx.Response(200, json=ORS_OK))
    with pytest.raises(NotConfigured):
        fetch_route(A, B)


@pytest.mark.parametrize(
    "status,exc", [(404, RouteNotFound), (401, NotConfigured), (403, NotConfigured)]
)
def test_status_codes_map_to_api_errors_without_retry(monkeypatch, status, exc):
    calls = use(monkeypatch, lambda r: httpx.Response(status, json={}))
    with pytest.raises(exc):
        fetch_route(A, B)
    assert len(calls) == 1


@pytest.mark.parametrize("status", [429, 500, 503])
def test_transient_failures_retry_once_then_502(monkeypatch, status):
    calls = use(monkeypatch, lambda r: httpx.Response(status, json={}))
    with pytest.raises(ProviderUnavailable):
        fetch_route(A, B)
    assert len(calls) == 2


def test_recovers_when_the_retry_succeeds(monkeypatch):
    seq = iter([httpx.Response(503, json={}), httpx.Response(200, json=ORS_OK)])
    calls = use(monkeypatch, lambda r: next(seq))
    assert fetch_route(A, B).coords
    assert len(calls) == 2


def test_timeout_is_a_504(monkeypatch):
    def boom(request):
        raise httpx.ReadTimeout("slow", request=request)

    use(monkeypatch, boom)
    with pytest.raises(ProviderTimeout):
        fetch_route(A, B)


def test_malformed_provider_body_is_a_502(monkeypatch):
    use(monkeypatch, lambda r: httpx.Response(200, json={"unexpected": True}))
    with pytest.raises(ProviderUnavailable):
        fetch_route(A, B)


def test_osrm_uses_get_and_lng_lat_in_the_path(monkeypatch, settings):
    settings.ROUTING_PROVIDER = "osrm"
    body = {
        "code": "Ok",
        "routes": [
            {"distance": 1609344.0, "geometry": {"coordinates": [[-74.0, 40.71], [-97.5, 35.4]]}}
        ],
    }
    calls = use(monkeypatch, lambda r: httpx.Response(200, json=body))
    rd = fetch_route(A, B)
    assert calls[0].method == "GET" and "/-74.0,40.71;-97.52,35.47" in str(calls[0].url)
    assert rd.provider_distance_mi == pytest.approx(1000)
