import pytest
from django.contrib.gis.geos import Point
from django.core.management import call_command

from apps.stations.models import Station, StationAlias

HEADER = "OPIS Truckstop ID\tTruckstop Name\tAddress\tCity\tState\tRack ID\tRetail Price\n"
ROWS = [
    (7, "WOODSHED OF BIG CABIN", "I-44, EXIT 283 & US-69", "Big Cabin", "OK", 307, "3.00733333"),
    (9, "KWIK TRIP #796", "I-94, EXIT 143 & US-12 & SR-21", "Tomah", "WI", 420, "3.28733333"),
    (20, "PILOT TRAVEL CENTER #1243", "I-8, EXIT 119 & SR-85", "Gila Bend", "AZ", 930, "3.899"),
    (20, "PILOT #1243", "I-8, EXIT 119 & SR-85", "Gila Bend", "AZ", 930, "3.899"),
    (28, "LITTLEFIELD EXPRESS #2", "I-540, EXIT 12 & US-71", "Fort Smith", "AR", 645, "3.399"),
    (35, "ACI TRUCK STOP", "US-46", "Columbia", "NJ", 90, "3.079"),
]


def write(tmp_path, rows):
    path = tmp_path / "fuel.tsv"
    path.write_text(HEADER + "".join("\t".join(map(str, r)) + "\n" for r in rows))
    return str(path)


def run_import(path, tmp_path, *extra):
    call_command("import_stations", path, "--report-dir", str(tmp_path / "reports"), *extra)


@pytest.mark.django_db
def test_import_dedupes_and_is_idempotent(tmp_path):
    path = write(tmp_path, ROWS)
    run_import(path, tmp_path)
    assert Station.objects.count() == 5
    aliases = StationAlias.objects.count()

    run_import(path, tmp_path)
    assert Station.objects.count() == 5
    assert StationAlias.objects.count() == aliases


@pytest.mark.django_db
def test_dry_run_writes_nothing(tmp_path):
    run_import(write(tmp_path, ROWS), tmp_path, "--dry-run")
    assert Station.objects.count() == 0


@pytest.mark.django_db
def test_reimport_updates_price_but_keeps_location(tmp_path):
    run_import(write(tmp_path, ROWS), tmp_path)
    pilot = Station.objects.get(name="PILOT TRAVEL CENTER #1243")
    pilot.location = Point(-112.7, 32.9, srid=4326)
    pilot.geocode_source = "census"
    pilot.save()

    changed = [(*r[:6], "4.25") if r[0] == 20 else r for r in ROWS]
    run_import(write(tmp_path, changed), tmp_path)

    pilot.refresh_from_db()
    assert str(pilot.price) == "4.2500"
    assert pilot.location is not None
    assert Station.objects.count() == 5


@pytest.mark.django_db
def test_address_change_clears_location_for_regeocoding(tmp_path):
    run_import(write(tmp_path, ROWS), tmp_path)
    pilot = Station.objects.get(name="PILOT TRAVEL CENTER #1243")
    pilot.location = Point(-112.7, 32.9, srid=4326)
    pilot.save()

    # Same brand + store number + city (Rule B) but a different address.
    moved = [r for r in ROWS if r[0] != 20]
    moved.append((20, "PILOT #1243", "I-8, EXIT 120", "Gila Bend", "AZ", 930, "3.899"))
    run_import(write(tmp_path, moved), tmp_path)

    assert Station.objects.count() == 5
    pilot.refresh_from_db()
    assert pilot.location is None
    assert pilot.address == "I-8, EXIT 120"
