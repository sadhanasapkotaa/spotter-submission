import pytest
from django.contrib.gis.geos import MultiPolygon, Point, Polygon

from apps.geo.models import Country
from apps.geo.services import reset_usa_cache
from apps.routing.errors import LocationError, OutsideUSA
from apps.routing.locations import parse_location, require_in_usa
from apps.stations.models import Place


@pytest.fixture
def places(db):
    reset_usa_cache()
    box = Polygon.from_bbox((-125, 24, -66, 49))
    Country.objects.create(name="USA", iso_a3="USA", geom=MultiPolygon(box, srid=4326))
    Place.objects.create(name="FORT WORTH", state="TX", location=Point(-97.33, 32.75, srid=4326))
    yield
    reset_usa_cache()


def test_lat_lng_string_and_dict_are_equivalent():
    a = parse_location("40.71,-74.0", "start")
    b = parse_location({"lat": 40.71, "lng": -74.0}, "start")
    assert (a.lat, a.lng) == (b.lat, b.lng) == (40.71, -74.0)


def test_city_state_uses_the_local_gazetteer_including_abbreviations(places):
    loc = parse_location("Ft Worth, TX", "start")
    assert loc.lat == pytest.approx(32.75) and loc.lng == pytest.approx(-97.33)


@pytest.mark.parametrize("value", ["", "somewhere", "91,0", "10,200", None, 5])
def test_garbage_is_a_location_error(value, places):
    with pytest.raises(LocationError):
        parse_location(value, "start")


def test_unknown_city_asks_for_coordinates(places):
    with pytest.raises(LocationError, match="lat,lng"):
        parse_location("Atlantis, TX", "end")


def test_outside_usa_names_the_offending_field(places):
    inside = parse_location("32.75,-97.33", "start")
    outside = parse_location("19.43,-99.13", "end")
    with pytest.raises(OutsideUSA) as err:
        require_in_usa(start=inside, end=outside)
    assert err.value.extra["outside"] == ["end"]
    require_in_usa(start=inside, end=inside)
