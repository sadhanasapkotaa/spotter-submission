"""Parse a user-supplied location: {"lat","lng"}, "lat,lng", or "City, ST" (local lookup, no API)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from apps.geo.services import in_usa
from apps.stations.dedupe import US_STATES, norm
from apps.stations.models import Place
from apps.stations.places import city_variants

from .errors import LocationError, OutsideUSA

_COORDS = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*[,;\s]\s*(-?\d+(?:\.\d+)?)\s*$")


@dataclass(frozen=True)
class Location:
    lat: float
    lng: float
    label: str


def parse_location(value, field: str) -> Location:
    if isinstance(value, dict):
        try:
            lat, lng = float(value["lat"]), float(value.get("lng", value.get("lon")))
        except (KeyError, TypeError, ValueError):
            raise LocationError(f"{field}: expected {{'lat': .., 'lng': ..}}") from None
        return _checked(lat, lng, f"{lat:.5f},{lng:.5f}", field)
    if not isinstance(value, str) or not value.strip():
        raise LocationError(f"{field}: a location is required")
    m = _COORDS.match(value)
    if m:
        lat, lng = float(m.group(1)), float(m.group(2))
        return _checked(lat, lng, f"{lat:.5f},{lng:.5f}", field)
    if "," in value:
        city, _, state = value.rpartition(",")
        city, state = norm(city), state.strip().upper()
        if state in US_STATES and city:
            for variant in city_variants(city):
                place = Place.objects.filter(name=variant, state=state).first()
                if place:
                    return _checked(place.location.y, place.location.x, value.strip(), field)
            raise LocationError(
                f"{field}: city '{value.strip()}' not found; send 'lat,lng' instead"
            )
    raise LocationError(f"{field}: use 'lat,lng' or 'City, ST' (got {value!r})")


def _checked(lat: float, lng: float, label: str, field: str) -> Location:
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise LocationError(
            f"{field}: latitude must be -90..90 and longitude -180..180 (lat first)"
        )
    return Location(lat, lng, label)


def require_in_usa(**points: Location) -> None:
    outside = [name for name, p in points.items() if not in_usa(p.lat, p.lng)]
    if outside:
        raise OutsideUSA(
            "Both locations must be inside the USA. Outside: " + ", ".join(outside) + ".",
            outside=outside,
        )
