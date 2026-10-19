from decimal import Decimal

from apps.stations.dedupe import build_clusters, norm, parse_rows, review_flags


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
    rows, rejects = parse_rows(enumerate(records, start=2))
    return rows, rejects, build_clusters(rows)


PILOT_A = rec(
    20, "PILOT TRAVEL CENTER #1243", "I-8, EXIT 119 & SR-85", "Gila Bend", "AZ", 930, "3.899"
)
PILOT_B = rec(20, "PILOT #1243", "I-8, EXIT 119 & SR-85", "Gila Bend", "AZ", 930, "3.899")


def test_norm_strips_punctuation_and_apostrophes():
    assert norm("I-44, EXIT 283 & US-69") == "I 44 EXIT 283 US 69"
    assert norm("Love's  Travel") == "LOVES TRAVEL"


def test_pilot_duplicates_merge_into_one_station():
    _, _, clusters = run([PILOT_A, PILOT_B])
    assert len(clusters) == 1
    c = clusters[0]
    assert c.n_rows == 2
    assert c.name == "PILOT TRAVEL CENTER #1243"  # longest name wins
    assert c.price == Decimal("3.8990")
    assert not c.price_conflict


def test_conflicting_prices_are_averaged():
    other = {**PILOT_B, "retail price": "3.999"}
    _, _, clusters = run([PILOT_A, other])
    assert clusters[0].price == Decimal("3.9490")
    assert clusters[0].price_conflict


def test_different_brands_at_same_exit_stay_separate():
    a = rec(1, "PILOT #12", "I-40, EXIT 5", "Amarillo", "TX", 1, "3.50")
    b = rec(2, "LOVES #99", "I-40, EXIT 5", "Amarillo", "TX", 1, "3.40")
    _, _, clusters = run([a, b])
    assert len(clusters) == 2


def test_store_number_rule_merges_when_address_text_differs():
    a = rec(5, "PILOT #1243", "I-8, EXIT 119", "Gila Bend", "AZ", 930, "3.90")
    b = rec(6, "PILOT TRAVEL CENTER #1243", "I-8 EXIT 119 & SR-85", "Gila Bend", "AZ", 930, "3.90")
    _, _, clusters = run([a, b])
    assert len(clusters) == 1


def test_station_key_ignores_opis_id_and_row_order():
    _, _, first = run([PILOT_A, PILOT_B])
    renumbered_b = {**PILOT_B, "opis truckstop id": "999"}
    _, _, second = run([renumbered_b, PILOT_A])
    assert first[0].station_key == second[0].station_key


def test_rejects():
    records = [
        rec(1, "A #1", "X", "Toronto", "ON", 1, "3.5"),
        rec(2, "B #2", "X", "Dallas", "TX", 1, "0"),
        rec(3, "C #3", "X", "", "TX", 1, "3.5"),
        rec(4, "D #4", "X", "Dallas", "TX", 1, "abc"),
        rec(5, "E #5", "X", "Dallas", "TX", 1, "3.5"),
    ]
    rows, rejects, clusters = run(records)
    assert len(rows) == 1 and len(clusters) == 1
    assert len(rejects) == 4


def test_same_opis_id_on_different_stations_is_flagged_not_merged():
    a = rec(7, "KWIK TRIP #796", "I-94, EXIT 143", "Tomah", "WI", 420, "3.28")
    b = rec(7, "CASEYS #12", "US-20", "Ames", "IA", 400, "3.10")
    _, _, clusters = run([a, b])
    assert len(clusters) == 2
    assert any("OPIS id 7" in f["reason"] for f in review_flags(clusters))
