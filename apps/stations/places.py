"""Helpers for matching station cities against Census Gazetteer place names."""

import re
import unicodedata

from apps.stations.dedupe import norm

_LSAD = re.compile(
    r"\s+(CITY AND BOROUGH|CITY|TOWN|VILLAGE|BOROUGH|CDP|MUNICIPALITY|TOWNSHIP|PLANTATION|"
    r"CORPORATION|URBAN COUNTY|CONSOLIDATED GOVERNMENT|METROPOLITAN GOVERNMENT|"
    r"UNIFIED GOVERNMENT|GOVERNMENT)$"
)
_SWAPS = (("FT", "FORT"), ("MT", "MOUNT"), ("ST", "SAINT"))


def clean_place_name(raw: str) -> str:
    """'Big Cabin town' -> 'BIG CABIN'. The legal-status suffix is stripped exactly once.

    Accents are folded first ('Cañon City' -> 'CANON CITY') so they match the OPIS spelling."""
    raw = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode()
    name = norm(re.sub(r"\(.*?\)", "", raw))
    return _LSAD.sub("", name, count=1)


def city_variants(city_n: str) -> list[str]:
    """The city plus common abbreviation swaps (FT/FORT, MT/MOUNT, ST/SAINT) in any position."""
    variants = [city_n]
    tokens = city_n.split()
    for short, long in _SWAPS:
        for src, dst in ((short, long), (long, short)):
            if src in tokens:
                swapped = " ".join(dst if t == src else t for t in tokens)
                if swapped not in variants:
                    variants.append(swapped)
    return variants


class PlaceIndex:
    """Looks up a station's city among Gazetteer names, from strictest match to loosest.

    1. exact name (plus FT/FORT-style swaps, and 'CARSON CITY' -> 'CARSON')
    2. spaces ignored ('LA FAYETTE' == 'LAFAYETTE')
    3. the city is the start of exactly one merged-government name in that state
       ('AUGUSTA' -> 'AUGUSTA RICHMOND COUNTY'). Census statistical areas (CCD) are skipped.
    """

    def __init__(self, items):
        self._exact: dict = {}
        self._compact: dict = {}
        self._by_first: dict = {}
        for name, state, value in items:
            self._exact[(name, state)] = value
            self._compact.setdefault((name.replace(" ", ""), state), value)
            if not name.endswith(" CCD") and " " in name:
                self._by_first.setdefault((name.split()[0], state), []).append((name, value))

    def __len__(self) -> int:
        return len(self._exact)

    def find(self, city_n: str, state: str):
        names = city_variants(city_n)
        if city_n.endswith(" CITY"):
            names.append(city_n[: -len(" CITY")])
        for name in names:
            if (name, state) in self._exact:
                return self._exact[(name, state)]
        for name in names:
            hit = self._compact.get((name.replace(" ", ""), state))
            if hit is not None:
                return hit
        tokens = city_n.split()
        if tokens:
            starts = [
                value
                for name, value in self._by_first.get((tokens[0], state), [])
                if name.split()[: len(tokens)] == tokens
            ]
            if len(starts) == 1:
                return starts[0]
        return None
