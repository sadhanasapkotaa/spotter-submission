import pytest
from django.contrib.gis.geos import Point

from apps.routing.station_index import clear_index, get_index
from apps.stations.models import Station


def make(key, price, lat=40.0, lon=-90.0, source="census", located=True):
    return Station.objects.create(
        station_key=key,
        name=key,
        address="",
        city="C",
        state="OH",
        price=price,
        location=Point(lon, lat, srid=4326) if located else None,
        geocode_source=source,
    )


@pytest.fixture(autouse=True)
def _fresh():
    clear_index()
    yield
    clear_index()


@pytest.mark.django_db
def test_only_located_stations_are_indexed_and_flags_are_set():
    make("a", "3.1000")
    make("b", "3.2000", source="city_centroid")
    make("c", "3.3000", located=False)
    idx = get_index()
    assert len(idx) == 2
    assert sorted(idx.approx.tolist()) == [False, True]
    assert idx.price.tolist() == [3.1, 3.2]


@pytest.mark.django_db
def test_snapshot_is_reused_until_the_table_changes():
    make("a", "3.1000")
    first = get_index()
    assert get_index() is first
    make("b", "3.2000")
    assert get_index() is not first and len(get_index()) == 2


@pytest.mark.django_db
def test_price_update_refreshes_the_snapshot():
    s = make("a", "3.1000")
    assert get_index().price[0] == pytest.approx(3.1)
    s.price = "4.0000"
    s.save()  # auto_now bumps updated_at
    assert get_index().price[0] == pytest.approx(4.0)
