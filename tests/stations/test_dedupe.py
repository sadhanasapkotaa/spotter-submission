from decimal import Decimal

from apps.stations.dedupe import norm, parse_rows


def rec(opis, name, address, city, state, rack, price):
    return {
        "opis truckstop id": str(opis),
        "truckstop name": name,
        "address": address,
        "city": city,
        "state": state,
        "rack id": str(rack),
        "retail price": str(price),
    }


def run(records):
    return parse_rows(enumerate(records, start=2))


def test_norm_strips_punctuation_and_apostrophes():
    assert norm("I-44, EXIT 283 & US-69") == "I 44 EXIT 283 US 69"
    assert norm("Love's  Travel") == "LOVES TRAVEL"


def test_parse_normalises_prices_names_and_store_numbers():
    rows, rejects = run(
        [rec(7, "Pilot Travel Center #01243", " I-8, EXIT 119 ", "Gila Bend", "az", 930, "3.8999")]
    )
    assert rejects == []
    (row,) = rows
    assert row.state == "AZ"
    assert row.price == Decimal("3.8999")
    assert row.number == "1243"


def test_rejects():
    records = [
        rec(1, "A #1", "X", "Toronto", "ON", 1, "3.5"),
        rec(2, "B #2", "X", "Dallas", "TX", 1, "0"),
        rec(3, "C #3", "X", "", "TX", 1, "3.5"),
        rec(4, "D #4", "X", "Dallas", "TX", 1, "abc"),
        rec(5, "E #5", "X", "Dallas", "TX", 1, "3.5"),
    ]
    rows, rejects = run(records)
    assert len(rows) == 1
    assert len(rejects) == 4
