"""Routing providers (one HTTP call per uncached route). Both are free:

* OSRM public demo server: no key, fair-use only. Default when no ORS key is set.
* OpenRouteService: free key (2,000 requests/day). Preferred when ORS_API_KEY is set.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx
from django.conf import settings
from django.core.cache import cache

from .errors import NotConfigured, ProviderTimeout, ProviderUnavailable, RouteNotFound

log = logging.getLogger(__name__)
METERS_PER_MILE = 1609.344


@dataclass(frozen=True)
class RouteData:
    coords: list  # [[lon, lat], ...]
    provider_distance_mi: float
    provider: str
    cached: bool = False


class _Transient(Exception):
    pass


def _client() -> httpx.Client:  # tests replace this with a MockTransport client
    return httpx.Client(timeout=settings.ROUTING_TIMEOUT_S)


def _cache_key(provider, a, b) -> str:
    return f"route:{provider}:{a[0]:.3f},{a[1]:.3f}:{b[0]:.3f},{b[1]:.3f}"


def fetch_route(start: tuple[float, float], end: tuple[float, float]) -> RouteData:
    """start/end are (lat, lng). Returns the driving route, using the cache when possible."""
    provider = settings.ROUTING_PROVIDER
    key = _cache_key(provider, start, end)
    hit = cache.get(key)
    if hit is not None:
        return RouteData(hit["coords"], hit["dist"], provider, cached=True)

    call = {"ors": _ors, "osrm": _osrm}[provider]
    last: Exception | None = None
    for attempt in (1, 2):  # one retry, only for transient failures
        try:
            with _client() as client:
                coords, dist_mi = call(client, start, end)
            cache.set(key, {"coords": coords, "dist": dist_mi}, settings.ROUTING_CACHE_TTL)
            return RouteData(coords, dist_mi, provider)
        except httpx.TimeoutException as exc:
            last = ProviderTimeout("The routing provider timed out.")
            log.warning("routing timeout (attempt %s): %s", attempt, exc)
        except _Transient as exc:
            last = ProviderUnavailable(f"The routing provider failed: {exc}")
            log.warning("routing transient error (attempt %s): %s", attempt, exc)
        except httpx.HTTPError as exc:
            last = ProviderUnavailable("Could not reach the routing provider.")
            log.warning("routing network error (attempt %s): %s", attempt, exc)
    raise last  # type: ignore[misc]


def _check(resp: httpx.Response) -> dict:
    if resp.status_code in (400, 404, 422):
        raise RouteNotFound("No drivable route was found between those two locations.")
    if resp.status_code in (401, 403):
        raise NotConfigured("The routing provider rejected the API key.")
    if resp.status_code == 429 or resp.status_code >= 500:
        raise _Transient(f"HTTP {resp.status_code}")
    resp.raise_for_status()
    return resp.json()


def _ors(client: httpx.Client, a, b):
    if not settings.ORS_API_KEY:
        raise NotConfigured("ROUTING_PROVIDER is 'ors' but ORS_API_KEY is not set.")
    url = f"{settings.ORS_BASE_URL}/v2/directions/{settings.ORS_PROFILE}/geojson"
    resp = client.post(
        url,
        headers={"Authorization": settings.ORS_API_KEY},
        json={
            "coordinates": [[a[1], a[0]], [b[1], b[0]]],
            "instructions": False,
            "radiuses": [-1, -1],  # snap to the nearest road however far it is
        },
    )
    data = _check(resp)
    try:
        feature = data["features"][0]
        return feature["geometry"]["coordinates"], feature["properties"]["summary"][
            "distance"
        ] / METERS_PER_MILE
    except (KeyError, IndexError, TypeError) as exc:
        raise _Transient(f"unexpected ORS response shape: {exc}") from exc


def _osrm(client: httpx.Client, a, b):
    url = f"{settings.OSRM_BASE_URL}/route/v1/driving/{a[1]},{a[0]};{b[1]},{b[0]}"
    resp = client.get(url, params={"overview": "full", "geometries": "geojson", "steps": "false"})
    data = _check(resp)
    if data.get("code") in ("NoRoute", "NoSegment"):
        raise RouteNotFound("No drivable route was found between those two locations.")
    try:
        route = data["routes"][0]
        return route["geometry"]["coordinates"], route["distance"] / METERS_PER_MILE
    except (KeyError, IndexError, TypeError) as exc:
        raise _Transient(f"unexpected OSRM response shape: {exc}") from exc
