"""Parse, normalise and de-duplicate the OPIS fuel price file.

Pure Python (no Django imports) so it is trivial to unit test. The OPIS truckstop id is NOT
trusted: identity comes from normalised address / brand / store number, and every station gets
its own stable `station_key`.
"""

from __future__ import annotations

import hashlib
import re
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
