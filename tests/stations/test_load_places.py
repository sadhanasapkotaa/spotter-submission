import pytest
from django.core.management import call_command

from apps.stations.models import Place

PLACES = (
    "USPS\tGEOID\tANSICODE\tNAME\tLSAD\tFUNCSTAT\tALAND\tAWATER\tALAND_SQMI\tAWATER_SQMI\t"
    "INTPTLAT\tINTPTLONG\n"
    "NJ\t1\t1\tMahwah CDP\t57\tS\t1\t1\t5.0\t0.0\t41.0900\t-74.1500\n"
    "OK\t2\t1\tOklahoma City city\t25\tA\t1\t1\t600.0\t0.0\t35.4671\t-97.5137\n"
)
COUSUBS = (
    "USPS\tGEOID\tANSICODE\tNAME\tFUNCSTAT\tALAND\tAWATER\tALAND_SQMI\tAWATER_SQMI\t"
    "INTPTLAT\tINTPTLONG\n"
    "NJ\t3\t1\tMahwah township\tA\t1\t1\t26.0\t0.0\t41.0800\t-74.1700\n"
    "ME\t4\t1\tWest Paris town\tA\t1\t1\t39.0\t0.3\t44.3800\t-70.5700\n"
    "CO\t5\t1\tCañon City city\tA\t1\t1\t17.0\t0.0\t38.4400\t-105.2400\n"
    "ME\t6\t1\tCounty subdivisions not defined\tN\t0\t0\t0.0\t0.0\t44.0000\t-70.0000\n"
    "ON\t7\t1\tToronto city\tA\t1\t1\t1.0\t0.0\t43.6500\t-79.3800\n"
)


@pytest.fixture
def gaz(tmp_path):
    places, cousubs = tmp_path / "places.txt", tmp_path / "cousubs.txt"
    places.write_text(PLACES)
    cousubs.write_text(COUSUBS)
    return str(places), str(cousubs)


def test_county_subdivisions_fill_in_new_england_style_towns(db, gaz):
    call_command("load_places", "--file", gaz[0], "--file", gaz[1])
    assert Place.objects.filter(name="WEST PARIS", state="ME").exists()
    assert Place.objects.filter(name="CANON CITY", state="CO").exists()


def test_the_first_file_wins_when_names_clash(db, gaz):
    call_command("load_places", "--file", gaz[0], "--file", gaz[1])
    mahwah = Place.objects.get(name="MAHWAH", state="NJ")
    assert mahwah.location.y == pytest.approx(41.09)


def test_junk_rows_and_non_us_states_are_skipped(db, gaz):
    call_command("load_places", "--file", gaz[0], "--file", gaz[1])
    assert not Place.objects.filter(name__startswith="COUNTY SUBDIVISIONS").exists()
    assert not Place.objects.filter(name="TORONTO").exists()


def test_loading_twice_is_idempotent(db, gaz):
    call_command("load_places", "--file", gaz[0], "--file", gaz[1])
    first = Place.objects.count()
    call_command("load_places", "--file", gaz[0], "--file", gaz[1])
    assert Place.objects.count() == first
