"""USA containment checks and small geodesy helpers."""

import math
from functools import lru_cache

from django.contrib.gis.geos import Point
from django.core.exceptions import ImproperlyConfigured

from apps.geo.models import Country

EARTH_RADIUS_MI = 3958.7613


@lru_cache(maxsize=1)
def _usa_prepared():
    """Prepared (indexed) USA geometry, cached per process so checks need no DB hit."""
    country = Country.objects.filter(iso_a3="USA").only("geom").first()
    if country is None:
        raise ImproperlyConfigured(
            "USA boundary not loaded. Run: python manage.py load_usa --download"
        )
    return country.geom.prepared


def reset_usa_cache() -> None:
    _usa_prepared.cache_clear()


def in_usa(lat: float, lng: float) -> bool:
    """True if the point is inside (or on the edge of) the USA. NOTE: lat first, lng second."""
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return False
    return _usa_prepared().intersects(Point(lng, lat, srid=4326))


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_MI * math.asin(math.sqrt(a))
