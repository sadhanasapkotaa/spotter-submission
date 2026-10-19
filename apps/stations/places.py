"""Helpers for matching station cities against Census Gazetteer place names."""

import re

from apps.stations.dedupe import norm

_LSAD = re.compile(
    r"\s+(CITY AND BOROUGH|CITY|TOWN|VILLAGE|BOROUGH|CDP|MUNICIPALITY|TOWNSHIP|PLANTATION|"
    r"CORPORATION|URBAN COUNTY|CONSOLIDATED GOVERNMENT|METROPOLITAN GOVERNMENT|"
    r"UNIFIED GOVERNMENT|GOVERNMENT)$"
)
_SWAPS = (("FT", "FORT"), ("MT", "MOUNT"), ("ST", "SAINT"))


def clean_place_name(raw: str) -> str:
    """'Big Cabin town' -> 'BIG CABIN'. The legal-status suffix is stripped exactly once."""
    name = norm(re.sub(r"\(.*?\)", "", raw))
    return _LSAD.sub("", name, count=1)


def city_variants(city_n: str) -> list[str]:
    """The city plus common abbreviation swaps (FT/FORT, MT/MOUNT, ST/SAINT)."""
    variants = [city_n]
    for short, long in _SWAPS:
        for src, dst in ((short, long), (long, short)):
            if city_n.startswith(src + " "):
                variants.append(dst + city_n[len(src) :])
    return variants
