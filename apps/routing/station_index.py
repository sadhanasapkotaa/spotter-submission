"""In-memory snapshot of geocoded stations, refreshed when the table changes.

~8k rows is tiny, so the per-request cost is one cheap COUNT/MAX query to validate the snapshot;
the heavy lifting (projection onto the route) is done in numpy. PostGIS stays the system of
record (boundary, import, geocoding) and is the right tool if this grew to millions of rows.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from django.db import connection
from django.db.models import Count, Max

from apps.stations.models import Station

APPROX_SOURCES = {"city_centroid"}


@dataclass(frozen=True)
class StationIndex:
    version: tuple
    ids: np.ndarray
    lat: np.ndarray
    lon: np.ndarray
    price: np.ndarray
    approx: np.ndarray  # True when the position is only a city centroid
    meta: tuple  # (station_key, name, address, city, state, geocode_source) per row

    def __len__(self) -> int:
        return len(self.ids)


_snapshot: StationIndex | None = None


def _version() -> tuple:
    agg = Station.objects.filter(location__isnull=False).aggregate(
        n=Count("id"), m=Max("updated_at")
    )
    return (agg["n"], agg["m"])


def get_index() -> StationIndex:
    global _snapshot
    version = _version()
    if _snapshot is not None and _snapshot.version == version:
        return _snapshot
    table = Station._meta.db_table
    with connection.cursor() as cur:
        cur.execute(
            f"SELECT id, station_key, name, address, city, state, price, geocode_source, "  # noqa: S608
            f"ST_Y(location::geometry), ST_X(location::geometry) FROM {table} "
            f"WHERE location IS NOT NULL ORDER BY id"
        )
        rows = cur.fetchall()
    _snapshot = StationIndex(
        version=version,
        ids=np.array([r[0] for r in rows], dtype=np.int64),
        lat=np.array([r[8] for r in rows], dtype=float),
        lon=np.array([r[9] for r in rows], dtype=float),
        price=np.array([float(r[6]) for r in rows], dtype=float),
        approx=np.array([r[7] in APPROX_SOURCES for r in rows], dtype=bool),
        meta=tuple((r[1], r[2], r[3], r[4], r[5], r[7]) for r in rows),
    )
    return _snapshot


def clear_index() -> None:
    global _snapshot
    _snapshot = None
