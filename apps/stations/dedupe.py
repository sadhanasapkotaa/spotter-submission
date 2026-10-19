"""Parse, normalise and de-duplicate the OPIS fuel price file.

Pure Python (no Django imports) so it is trivial to unit test. The OPIS truckstop id is NOT
trusted: identity comes from normalised address / brand / store number, and every station gets
its own stable `station_key`.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

KEY_VERSION = "v1"
US_STATES = frozenset(
    "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH "
    "NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split()
)
MIN_PRICE = Decimal("0.01")
MAX_PRICE = Decimal("10")
PRICE_QUANT = Decimal("0.0001")

# Expected (lower-cased) header names of the source file.
COLUMNS = {
    "opis_id": "opis truckstop id",
    "name": "truckstop name",
    "address": "address",
    "city": "city",
    "state": "state",
    "rack_id": "rack id",
    "price": "retail price",
}

_NON_ALNUM = re.compile(r"[^A-Z0-9]+")
_STORE_NO = re.compile(r"#\s*0*(\d+)")
_STORE_NO_STRIP = re.compile(r"#\s*\d+")


def norm(text: str | None) -> str:
    """Upper-case, drop apostrophes, replace every other non-alphanumeric run with one space."""
    return _NON_ALNUM.sub(" ", (text or "").upper().replace("'", "")).strip()


def display(text: str | None) -> str:
    return " ".join((text or "").split())


def store_number(name: str) -> str:
    match = _STORE_NO.search(name or "")
    return match.group(1) if match else ""


def brand_of(name: str) -> str:
    cleaned = norm(_STORE_NO_STRIP.sub(" ", name or ""))
    return cleaned.split()[0] if cleaned else ""


def hash_key(raw: str) -> str:
    return hashlib.sha1(f"{KEY_VERSION}|{raw}".encode(), usedforsecurity=False).hexdigest()


@dataclass(frozen=True)
class Row:
    line_no: int
    opis_id: int | None
    name: str
    address: str
    city: str
    state: str
    rack_id: int | None
    price: Decimal

    @property
    def addr_n(self) -> str:
        return norm(self.address) or f"NOADDR {norm(self.name)}"

    @property
    def city_n(self) -> str:
        return norm(self.city)

    @property
    def brand(self) -> str:
        return brand_of(self.name)

    @property
    def number(self) -> str:
        return store_number(self.name)

    @property
    def group_key(self) -> tuple[str, str, str, str]:
        return (self.addr_n, self.city_n, self.state, self.brand)

    @property
    def key_a(self) -> str:
        """Rule A: same address + city + state + brand + store number."""
        return "A|" + "|".join((*self.group_key, self.number))

    @property
    def key_b(self) -> str | None:
        """Rule B: same state + city + brand + store number (address text may differ)."""
        if not self.number:
            return None
        return "B|" + "|".join((self.state, self.city_n, self.brand, self.number))


@dataclass(frozen=True)
class Reject:
    line_no: int
    reason: str
    raw: str


@dataclass(frozen=True)
class Cluster:
    station_key: str
    keys: tuple[str, ...]
    name: str
    address: str
    city: str
    state: str
    price: Decimal
    opis_id: int | None
    opis_ids: tuple[int, ...]
    rack_id: int | None
    n_rows: int
    price_conflict: bool

    @property
    def alias_hashes(self) -> tuple[str, ...]:
        return tuple(hash_key(k) for k in self.keys)

    @property
    def address_n(self) -> str:
        return norm(self.address)


def _to_int(value) -> int | None:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def parse_rows(records) -> tuple[list[Row], list[Reject]]:
    """records: iterable of (line_no, dict with lower-cased header keys)."""
    rows: list[Row] = []
    rejects: list[Reject] = []
    for line_no, rec in records:
        raw = " | ".join(str(v) for v in rec.values())
        name = display(rec.get(COLUMNS["name"]))[:255]
        address = display(rec.get(COLUMNS["address"]))[:255]
        city = display(rec.get(COLUMNS["city"]))[:100]
        state = display(rec.get(COLUMNS["state"])).upper()

        if not name:
            rejects.append(Reject(line_no, "missing name", raw))
            continue
        if not city:
            rejects.append(Reject(line_no, "missing city", raw))
            continue
        if state not in US_STATES:
            rejects.append(Reject(line_no, f"non-US or unknown state '{state}'", raw))
            continue
        try:
            price = Decimal(str(rec.get(COLUMNS["price"]) or "").strip())
        except InvalidOperation:
            rejects.append(Reject(line_no, "unparseable price", raw))
            continue
        if not price.is_finite() or not (MIN_PRICE <= price <= MAX_PRICE):
            rejects.append(Reject(line_no, f"price out of range ({price})", raw))
            continue

        rows.append(
            Row(
                line_no=line_no,
                opis_id=_to_int(rec.get(COLUMNS["opis_id"])),
                name=name,
                address=address,
                city=city,
                state=state,
                rack_id=_to_int(rec.get(COLUMNS["rack_id"])),
                price=price.quantize(PRICE_QUANT, ROUND_HALF_UP),
            )
        )
    return rows, rejects


def _mode(values) -> str:
    counts = Counter(values)
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def _make_cluster(rows: list[Row]) -> Cluster:
    keys = sorted({k for r in rows for k in (r.key_a, r.key_b) if k})
    canonical = min(r.key_a for r in rows)
    prices = [r.price for r in rows]
    mean = (sum(prices, Decimal(0)) / len(prices)).quantize(PRICE_QUANT, ROUND_HALF_UP)
    opis_ids = tuple(sorted({r.opis_id for r in rows if r.opis_id is not None}))
    racks = [r.rack_id for r in rows if r.rack_id is not None]
    return Cluster(
        station_key=hash_key(canonical),
        keys=tuple(keys),
        name=max((r.name for r in rows), key=lambda n: (len(n), n)),
        address=_mode(r.address for r in rows),
        city=_mode(r.city for r in rows),
        state=rows[0].state,
        price=mean,
        opis_id=opis_ids[0] if opis_ids else None,
        opis_ids=opis_ids,
        rack_id=min(racks) if racks else None,
        n_rows=len(rows),
        price_conflict=len(set(prices)) > 1,
    )


def build_clusters(rows: list[Row]) -> list[Cluster]:
    """Union-find over Rule A and Rule B keys; each connected group is one station."""
    parent = list(range(len(rows)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    first_seen: dict[str, int] = {}
    for i, row in enumerate(rows):
        for key in (row.key_a, row.key_b):
            if key is None:
                continue
            if key in first_seen:
                a, b = find(i), find(first_seen[key])
                if a != b:
                    parent[max(a, b)] = min(a, b)
            else:
                first_seen[key] = i

    groups: dict[int, list[Row]] = defaultdict(list)
    for i, row in enumerate(rows):
        groups[find(i)].append(row)
    return sorted((_make_cluster(g) for g in groups.values()), key=lambda c: c.station_key)


def review_flags(clusters: list[Cluster]) -> list[dict]:
    """Cases worth a human look. These are flagged only, never merged automatically."""
    flags: list[dict] = []
    by_key = {c.station_key: c for c in clusters}

    def describe(keys) -> str:
        return "; ".join(
            f"{by_key[k].name} @ {by_key[k].address}, {by_key[k].city} {by_key[k].state}"
            for k in sorted(keys)
        )

    by_opis: dict[int, set[str]] = defaultdict(set)
    by_group: dict[tuple, set[str]] = defaultdict(set)
    for c in clusters:
        for oid in c.opis_ids:
            by_opis[oid].add(c.station_key)
        for k in c.keys:
            if k.startswith("A|"):
                by_group[tuple(k.split("|")[1:5])].add(c.station_key)

    for oid, keys in sorted(by_opis.items()):
        if len(keys) > 1:
            flags.append(
                {
                    "reason": f"OPIS id {oid} used by {len(keys)} different stations",
                    "detail": describe(keys),
                }
            )
    for _group, keys in sorted(by_group.items()):
        if len(keys) > 1:
            flags.append(
                {
                    "reason": "same address + brand but different/missing store number",
                    "detail": describe(keys),
                }
            )
    return flags
