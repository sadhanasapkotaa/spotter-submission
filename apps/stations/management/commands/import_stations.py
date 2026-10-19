import csv
import json
from collections import Counter
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.stations.dedupe import (
    COLUMNS,
    build_clusters,
    norm,
    parse_rows,
    review_flags,
)
from apps.stations.models import Station, StationAlias

FIELDS = ("name", "price", "opis_id", "rack_id", "address", "city", "state")


def _chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i : i + size]


class Command(BaseCommand):
    help = "Import the OPIS fuel price file: normalise, de-duplicate, upsert. Safe to re-run."

    def add_arguments(self, parser):
        parser.add_argument("path", nargs="?", default=str(settings.DATA_DIR / "fuel-prices.csv"))
        parser.add_argument("--dry-run", action="store_true", help="Do everything, then roll back")
        parser.add_argument("--report-dir", default=str(settings.DATA_DIR / "reports"))

    def handle(self, *args, **opts):
        path = Path(opts["path"])
        if not path.exists():
            raise CommandError(f"File not found: {path}")

        rows, rejects = parse_rows(self._read(path))
        clusters = build_clusters(rows)
        flags = review_flags(clusters)

        with transaction.atomic():
            stats = self._sync(clusters)
            if opts["dry_run"]:
                transaction.set_rollback(True)

        self._write_reports(Path(opts["report_dir"]), rejects, flags)

        self.stdout.write(f"Rows read:               {len(rows) + len(rejects)}")
        self.stdout.write(f"Rows rejected:           {len(rejects)}")
        self.stdout.write(f"Duplicate rows merged:   {len(rows) - len(clusters)}")
        self.stdout.write(f"Unique stations in file: {len(clusters)}")
        self.stdout.write(f"  created:               {stats['created']}")
        self.stdout.write(f"  updated:               {stats['updated']}")
        self.stdout.write(f"  unchanged:             {stats['unchanged']}")
        self.stdout.write(f"  address changed (re-geocode needed): {stats['regeocode']}")
        self.stdout.write(f"  price conflicts averaged: {sum(c.price_conflict for c in clusters)}")
        self.stdout.write(f"Alias conflicts:         {stats['alias_conflicts']}")
        self.stdout.write(f"Flagged for review:      {len(flags)}")
        self.stdout.write(f"In DB but not in file:   {stats['not_in_file']}")
        if opts["dry_run"]:
            self.stdout.write(self.style.WARNING("DRY RUN: nothing was written."))

    # ------------------------------------------------------------------ reading
    def _read(self, path: Path):
        with path.open(newline="", encoding="utf-8-sig") as fh:
            head = fh.readline()
            fh.seek(0)
            reader = csv.DictReader(fh, delimiter="\t" if "\t" in head else ",")
            reader.fieldnames = [(n or "").strip().lower() for n in reader.fieldnames or []]
            missing = set(COLUMNS.values()) - set(reader.fieldnames)
            if missing:
                raise CommandError(f"Missing columns: {sorted(missing)}")
            yield from enumerate(reader, start=2)

    # ------------------------------------------------------------------ database
    def _sync(self, clusters):
        stats = Counter()

        hashes = [h for c in clusters for h in c.alias_hashes]
        alias_map: dict[str, int] = {}
        for chunk in _chunks(hashes, 5000):
            alias_map.update(
                StationAlias.objects.filter(key__in=chunk).values_list("key", "station_id")
            )

        matched = []
        for c in clusters:
            ids = sorted({alias_map[h] for h in c.alias_hashes if h in alias_map})
            if len(ids) > 1:
                stats["alias_conflicts"] += (
                    1  # cluster touches 2+ existing stations: keep the oldest
                )
            matched.append((c, ids[0] if ids else None))

        existing = Station.objects.in_bulk([sid for _, sid in matched if sid])
        now = timezone.now()
        pairs, to_create, to_update = [], [], []
        for c, sid in matched:
            if sid is None:
                obj = Station(
                    station_key=c.station_key,
                    **{f: getattr(c, f) for f in FIELDS},
                )
                to_create.append(obj)
                stats["created"] += 1
            else:
                obj = existing[sid]
                changed, regeocode = self._apply(obj, c, now)
                if changed:
                    to_update.append(obj)
                    stats["updated"] += 1
                else:
                    stats["unchanged"] += 1
                stats["regeocode"] += regeocode
            pairs.append((c, obj))

        Station.objects.bulk_create(to_create, batch_size=1000)
        Station.objects.bulk_update(
            to_update,
            [*FIELDS, "location", "geocode_source", "updated_at"],
            batch_size=500,
        )
        aliases = [StationAlias(key=h, station=obj) for c, obj in pairs for h in c.alias_hashes]
        StationAlias.objects.bulk_create(aliases, batch_size=2000, ignore_conflicts=True)

        stats["not_in_file"] = Station.objects.exclude(pk__in=[o.pk for _, o in pairs]).count()
        return stats

    @staticmethod
    def _apply(obj: Station, c, now) -> tuple[bool, int]:
        """Copy cluster data onto an existing station. Returns (changed, needs_regeocode)."""
        # Decide "moved" BEFORE overwriting the fields it compares against.
        moved = norm(obj.address) != c.address_n or obj.city != c.city or obj.state != c.state
        changed = False
        for f in FIELDS:
            new = getattr(c, f)
            if getattr(obj, f) != new:
                setattr(obj, f, new)
                changed = True
        regeocode = 0
        # Coordinates are only discarded when the address itself changed.
        if moved and obj.location is not None:
            obj.location = None
            obj.geocode_source = ""
            regeocode = 1
        if changed:
            obj.updated_at = now
        return changed, regeocode

    # ------------------------------------------------------------------ reports
    def _write_reports(self, directory: Path, rejects, flags):
        try:
            directory.mkdir(parents=True, exist_ok=True)
            with (directory / "import_rejects.csv").open("w", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(["line", "reason", "raw"])
                for r in rejects:
                    w.writerow([r.line_no, r.reason, r.raw])
            with (directory / "import_review.csv").open("w", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(["reason", "detail"])
                for f in flags:
                    w.writerow([f["reason"], f["detail"]])
        except OSError as exc:
            self.stderr.write(f"Could not write reports ({exc}); use --report-dir /tmp")
            self.stderr.write(json.dumps({"rejects": len(rejects), "flags": len(flags)}))
