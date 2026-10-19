import csv
import io
from pathlib import Path

import httpx
from django.conf import settings
from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.geo.models import Country
from apps.geo.services import haversine_miles, in_usa
from apps.stations.dedupe import norm
from apps.stations.models import Place, Station
from apps.stations.places import city_variants

CENSUS_URL = "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"
MAX_CENSUS_DISTANCE_MI = 50  # reject a street match this far from the station's city centroid
UPDATE_FIELDS = ["location", "geocode_source", "updated_at"]


class Command(BaseCommand):
    help = (
        "Geocode stations that have no location: Census batch geocoder first, then city "
        "centroid. Resumable. Use --export-csv / --load-csv to share results via git."
    )

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=1000)
        parser.add_argument("--limit", type=int, help="Only geocode the first N pending stations")
        parser.add_argument("--skip-census", action="store_true", help="City centroid only")
        parser.add_argument("--export-csv", help="Write all located stations to this CSV")
        parser.add_argument("--load-csv", help="Load coordinates from a previously exported CSV")
        parser.add_argument("--overwrite", action="store_true", help="With --load-csv")
        parser.add_argument("--report-dir", default=str(settings.DATA_DIR / "reports"))

    def handle(self, *args, **opts):
        if opts["load_csv"]:
            self._load_csv(Path(opts["load_csv"]), opts["overwrite"])
        else:
            self._geocode(opts)
        if opts["export_csv"]:
            self._export_csv(Path(opts["export_csv"]))

    # ------------------------------------------------------------------ geocoding
    def _geocode(self, opts):
        pending = list(Station.objects.filter(location__isnull=True).order_by("id"))
        if opts["limit"]:
            pending = pending[: opts["limit"]]
        if not pending:
            self.stdout.write("Nothing to geocode.")
            return

        usa_ready = Country.objects.filter(iso_a3="USA").exists()
        if not usa_ready:
            self.stdout.write(self.style.WARNING("USA boundary not loaded: skipping USA check."))
        centroids = {
            (name, state): (pt.y, pt.x)
            for name, state, pt in Place.objects.values_list("name", "state", "location")
        }
        if not centroids:
            self.stdout.write(self.style.WARNING("No Place rows: run load_places first."))

        def centroid_for(s: Station):
            for variant in city_variants(norm(s.city)):
                hit = centroids.get((variant, s.state))
                if hit:
                    return hit
            return None

        now = timezone.now()
        census_hits = 0
        if not opts["skip_census"]:
            size = opts["batch_size"]
            with httpx.Client() as client:
                for i in range(0, len(pending), size):
                    chunk = pending[i : i + size]
                    try:
                        found = self._census_batch(client, chunk)
                    except httpx.HTTPError as exc:
                        self.stderr.write(f"Census batch {i // size + 1} failed: {exc}")
                        continue
                    updates = []
                    for s in chunk:
                        hit = found.get(s.pk)
                        if not hit:
                            continue
                        lat, lon, source = hit
                        if not self._plausible(lat, lon, centroid_for(s), usa_ready):
                            continue
                        s.location = Point(lon, lat, srid=4326)
                        s.geocode_source = source
                        s.updated_at = now
                        updates.append(s)
                    Station.objects.bulk_update(updates, UPDATE_FIELDS)
                    census_hits += len(updates)
                    self.stdout.write(f"  census batch {i // size + 1}: {len(updates)} accepted")

        fallback, failures = [], []
        for s in pending:
            if s.location is not None:
                continue
            hit = centroid_for(s)
            if hit is None:
                failures.append(s)
                continue
            s.location = Point(hit[1], hit[0], srid=4326)
            s.geocode_source = "city_centroid"
            s.updated_at = now
            fallback.append(s)
        Station.objects.bulk_update(fallback, UPDATE_FIELDS, batch_size=500)

        self.stdout.write(f"Pending:            {len(pending)}")
        self.stdout.write(f"Census matches:     {census_hits}")
        self.stdout.write(f"City centroid:      {len(fallback)}")
        self.stdout.write(f"Failed (no point):  {len(failures)}")
        self._write_failures(Path(opts["report_dir"]), failures)

    @staticmethod
    def _plausible(lat, lon, centroid, usa_ready) -> bool:
        if usa_ready and not in_usa(lat, lon):
            return False
        if centroid and haversine_miles(lat, lon, *centroid) > MAX_CENSUS_DISTANCE_MI:
            return False
        return True

    @staticmethod
    def _census_batch(client: httpx.Client, stations) -> dict[int, tuple[float, float, str]]:
        buf = io.StringIO()
        writer = csv.writer(buf)
        for s in stations:
            writer.writerow([s.pk, s.address, s.city, s.state, ""])
        resp = client.post(
            CENSUS_URL,
            data={"benchmark": "Public_AR_Current"},
            files={"addressFile": ("addresses.csv", buf.getvalue().encode(), "text/csv")},
            timeout=300,
        )
        resp.raise_for_status()
        found = {}
        for rec in csv.reader(io.StringIO(resp.text)):
            # id, input, Match|No_Match|Tie, Exact|Non_Exact, matched address, "lon,lat", ...
            if len(rec) < 6 or rec[2] != "Match" or not rec[5]:
                continue
            try:
                lon, lat = (float(x) for x in rec[5].split(","))
                found[int(rec[0])] = (lat, lon, "census" if rec[3] == "Exact" else "census_approx")
            except ValueError:
                continue
        return found

    def _write_failures(self, directory: Path, failures):
        try:
            directory.mkdir(parents=True, exist_ok=True)
            with (directory / "geocode_failures.csv").open("w", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(["station_key", "name", "address", "city", "state"])
                for s in failures:
                    w.writerow([s.station_key, s.name, s.address, s.city, s.state])
        except OSError as exc:
            self.stderr.write(f"Could not write failure report ({exc}); use --report-dir /tmp")

    # ------------------------------------------------------------------ csv exchange
    def _export_csv(self, path: Path):
        qs = Station.objects.filter(location__isnull=False).order_by("station_key")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(
                [
                    "station_key",
                    "name",
                    "address",
                    "city",
                    "state",
                    "price",
                    "lat",
                    "lng",
                    "geocode_source",
                ]
            )
            n = 0
            for s in qs.iterator():
                w.writerow(
                    [
                        s.station_key,
                        s.name,
                        s.address,
                        s.city,
                        s.state,
                        s.price,
                        round(s.location.y, 6),
                        round(s.location.x, 6),
                        s.geocode_source,
                    ]
                )
                n += 1
        self.stdout.write(self.style.SUCCESS(f"Exported {n} stations to {path}"))

    def _load_csv(self, path: Path, overwrite: bool):
        if not path.exists():
            raise CommandError(f"File not found: {path}")
        with path.open(newline="") as fh:
            records = [r for r in csv.DictReader(fh) if r.get("lat") and r.get("lng")]
        now = timezone.now()
        loaded = 0
        for i in range(0, len(records), 1000):
            chunk = {r["station_key"]: r for r in records[i : i + 1000]}
            updates = []
            for s in Station.objects.filter(station_key__in=chunk):
                if s.location is not None and not overwrite:
                    continue
                r = chunk[s.station_key]
                s.location = Point(float(r["lng"]), float(r["lat"]), srid=4326)
                s.geocode_source = r.get("geocode_source", "")
                s.updated_at = now
                updates.append(s)
            Station.objects.bulk_update(updates, UPDATE_FIELDS)
            loaded += len(updates)
        self.stdout.write(self.style.SUCCESS(f"Loaded coordinates for {loaded} stations."))
