import pytest
from django.contrib.gis.geos import MultiPolygon, Polygon
from django.core.exceptions import ImproperlyConfigured

from apps.geo.models import Country
from apps.geo.services import in_usa, reset_usa_cache


@pytest.fixture
def usa(db):
    reset_usa_cache()
    box = Polygon.from_bbox((-125, 24, -66, 49))  # crude contiguous-US box, enough for logic tests
    Country.objects.create(
        name="United States of America", iso_a3="USA", geom=MultiPolygon(box, srid=4326)
    )
    yield
    reset_usa_cache()


def test_points_inside(usa):
    assert in_usa(40.7128, -74.0060)  # NYC
    assert in_usa(34.0522, -118.2437)  # LA


def test_points_outside(usa):
    assert not in_usa(51.5074, -0.1278)  # London
    assert not in_usa(19.4326, -99.1332)  # Mexico City


def test_swapped_lat_lng_is_outside(usa):
    assert not in_usa(-74.0060, 40.7128)


def test_out_of_range_coordinates(usa):
    assert not in_usa(95, 10)
    assert not in_usa(10, 200)


def test_raises_when_boundary_not_loaded(db):
    reset_usa_cache()
    with pytest.raises(ImproperlyConfigured):
        in_usa(40.7, -74.0)
