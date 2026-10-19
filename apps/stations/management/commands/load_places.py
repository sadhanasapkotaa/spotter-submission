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

GAZETTEER_URL = (
    "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/"
    "2023_Gazetteer/2023_Gaz_place_national.zip"
)


class Command(BaseCommand):
    help = "Load US city centroids from the Census Gazetteer (geocoding fallback). Idempotent."

    def add_arguments(self, parser):
        parser.add_argument("--url", default=GAZETTEER_URL)
        parser.add_argument("--file", help="Local Gazetteer .zip or .txt instead of downloading")

    def handle(self, *args, **opts):
        text = self._read(opts)
        reader = csv.DictReader(io.StringIO(text), delimiter="\t")
        reader.fieldnames = [(f or "").strip() for f in reader.fieldnames or []]
        needed = {"USPS", "NAME", "ALAND_SQMI", "INTPTLAT", "INTPTLONG"}
        if not needed <= set(reader.fieldnames):
            raise CommandError(f"Unexpected Gazetteer columns: {reader.fieldnames}")

        best: dict[tuple[str, str], tuple[tuple, Point, float]] = {}
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
            if not name:
                continue
            # On a name clash prefer real municipalities over CDPs, then the larger area.
            score = (not rec["NAME"].upper().endswith("CDP"), land)
            current = best.get((name, state))
            if current is None or score > current[0]:
                best[(name, state)] = (score, Point(lon, lat, srid=4326), land)

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

    def _read(self, opts) -> str:
        if opts["file"]:
            data = Path(opts["file"]).read_bytes()
        else:
            self.stdout.write("Downloading Census Gazetteer places...")
            resp = httpx.get(opts["url"], timeout=120, follow_redirects=True)
            resp.raise_for_status()
            data = resp.content
        if data[:2] == b"PK":
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                member = next(n for n in zf.namelist() if n.lower().endswith(".txt"))
                data = zf.read(member)
        return data.decode("utf-8", errors="replace")
