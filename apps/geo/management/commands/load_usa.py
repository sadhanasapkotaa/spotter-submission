import tempfile
import zipfile
from pathlib import Path

import httpx
from django.contrib.gis.gdal import DataSource
from django.contrib.gis.geos import MultiPolygon
from django.core.management.base import BaseCommand, CommandError

from apps.geo.models import Country
from apps.geo.services import reset_usa_cache

NE_URL = "https://naturalearth.s3.amazonaws.com/10m_cultural/ne_10m_admin_0_countries.zip"


class Command(BaseCommand):
    help = "Load the USA boundary (Natural Earth 10m admin-0 countries) into Country."

    def add_arguments(self, parser):
        parser.add_argument("shapefile", nargs="?", help="Path to ne_10m_admin_0_countries.shp")
        parser.add_argument("--download", action="store_true", help="Download from Natural Earth")

    def handle(self, *args, **opts):
        if opts["download"]:
            with tempfile.TemporaryDirectory() as tmp:
                self.stdout.write("Downloading Natural Earth countries...")
                resp = httpx.get(NE_URL, timeout=180, follow_redirects=True)
                resp.raise_for_status()
                archive = Path(tmp) / "ne.zip"
                archive.write_bytes(resp.content)
                with zipfile.ZipFile(archive) as zf:
                    zf.extractall(tmp)
                self._load(Path(tmp) / "ne_10m_admin_0_countries.shp")
        elif opts["shapefile"]:
            self._load(Path(opts["shapefile"]))
        else:
            raise CommandError("Pass a .shp path or --download")

    def _load(self, shp: Path):
        layer = DataSource(str(shp))[0]
        for feat in layer:
            if feat.get("ADM0_A3") != "USA":
                continue
            geom = feat.geom.geos
            geom.srid = 4326
            if geom.geom_type == "Polygon":
                geom = MultiPolygon(geom, srid=4326)
            Country.objects.update_or_create(
                iso_a3="USA",
                defaults={"name": feat.get("NAME"), "geom": geom},
            )
            reset_usa_cache()
            self.stdout.write(self.style.SUCCESS("USA boundary loaded."))
            return
        raise CommandError("USA feature (ADM0_A3 == 'USA') not found in the shapefile")
