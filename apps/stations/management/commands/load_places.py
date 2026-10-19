import csv
import io
import zipfile
from pathlib import Path

import httpx
from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand, CommandError

from apps.stations.dedupe import US_STATES
from apps.stations.models import Place
from apps.stations.places import clean_place_name

GAZETTEER_BASE = "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2023_Gazetteer/"
# Incorporated places and CDPs first; county subdivisions (New England towns, NJ/PA/NY/MI/WI
# townships, ...) second. They are not "places" in the Census sense but OPIS lists them as cities.
GAZETTEER_URLS = (
    GAZETTEER_BASE + "2023_Gaz_place_national.zip",
    GAZETTEER_BASE + "2023_Gaz_cousubs_national.zip",
)


class Command(BaseCommand):
    help = "Load US city centroids from the Census Gazetteer (geocoding fallback). Idempotent."

    def add_arguments(self, parser):
        parser.add_argument(
            "--url", action="append", help="Gazetteer zip URL (repeatable; earlier wins on clashes)"
        )
        parser.add_argument(
            "--file", action="append", help="Local Gazetteer .zip/.txt (repeatable; earlier wins)"
        )

    def handle(self, *args, **opts):
        best: dict[tuple[str, str], tuple[tuple, Point, float]] = {}
        sources = opts["file"] or opts["url"] or list(GAZETTEER_URLS)
        for rank, source in enumerate(sources):
            text = self._read(source, is_file=bool(opts["file"]))
            # Earlier sources outrank later ones when two places share a name and state.
            self._collect(text, priority=len(sources) - rank, best=best)

        places = [
            Place(name=n, state=s, location=pt, land_sq_mi=land)
            for (n, s), (_, pt, land) in best.items()
        ]
        Place.objects.bulk_create(
            places,
            batch_size=2000,
            update_conflicts=True,
            unique_fields=["name", "state"],
            update_fields=["location", "land_sq_mi"],
        )
        self.stdout.write(self.style.SUCCESS(f"{len(places)} places loaded."))

    @staticmethod
    def _collect(text: str, priority: int, best: dict) -> None:
        reader = csv.DictReader(io.StringIO(text), delimiter="\t")
        reader.fieldnames = [(f or "").strip() for f in reader.fieldnames or []]
        needed = {"USPS", "NAME", "ALAND_SQMI", "INTPTLAT", "INTPTLONG"}
        if not needed <= set(reader.fieldnames):
            raise CommandError(f"Unexpected Gazetteer columns: {reader.fieldnames}")
        for rec in reader:
            rec = {k: (v or "").strip() for k, v in rec.items() if k}
            state = rec["USPS"]
            if state not in US_STATES:
                continue
            name = clean_place_name(rec["NAME"])
            try:
                lat, lon = float(rec["INTPTLAT"]), float(rec["INTPTLONG"])
                land = float(rec["ALAND_SQMI"] or 0)
            except ValueError:
                continue
            if not name or name.startswith("COUNTY SUBDIVISIONS NOT DEFINED"):
                continue
            # On a name clash: higher-priority source, then real municipalities over CDPs,
            # then the larger area.
            score = (priority, not rec["NAME"].upper().endswith("CDP"), land)
            current = best.get((name, state))
            if current is None or score > current[0]:
                best[(name, state)] = (score, Point(lon, lat, srid=4326), land)

    def _read(self, source: str, is_file: bool) -> str:
        if is_file:
            data = Path(source).read_bytes()
        else:
            self.stdout.write(f"Downloading {source.rsplit('/', 1)[-1]}...")
            resp = httpx.get(source, timeout=120, follow_redirects=True)
            resp.raise_for_status()
            data = resp.content
        if data[:2] == b"PK":
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                member = next(n for n in zf.namelist() if n.lower().endswith(".txt"))
                data = zf.read(member)
        return data.decode("utf-8", errors="replace")
