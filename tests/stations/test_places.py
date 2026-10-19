from apps.stations.places import PlaceIndex, city_variants, clean_place_name


def test_legal_suffix_is_removed_once():
    assert clean_place_name("Big Cabin town") == "BIG CABIN"
    assert clean_place_name("Oklahoma City city") == "OKLAHOMA CITY"
    assert clean_place_name("Salt Lake City city") == "SALT LAKE CITY"


def test_parenthesised_notes_are_dropped():
    assert clean_place_name("Nashville-Davidson (balance)") == "NASHVILLE DAVIDSON"


def test_abbreviation_variants_are_generated_both_ways():
    assert city_variants("FT WORTH") == ["FT WORTH", "FORT WORTH"]
    assert city_variants("SAINT LOUIS") == ["SAINT LOUIS", "ST LOUIS"]
    assert city_variants("DALLAS") == ["DALLAS"]


def test_accents_are_folded_to_match_the_opis_spelling():
    assert clean_place_name("Cañon City city") == "CANON CITY"


def test_abbreviation_swaps_work_in_any_position():
    assert city_variants("EAST SAINT LOUIS") == ["EAST SAINT LOUIS", "EAST ST LOUIS"]
    assert city_variants("WEST ST PAUL") == ["WEST ST PAUL", "WEST SAINT PAUL"]


def _index():
    names = [
        "LAFAYETTE", "CARSON", "AUGUSTA RICHMOND COUNTY", "AUGUSTA CCD", "LEXINGTON FAYETTE",
        "SPRINGFIELD NORTH", "SPRINGFIELD SOUTH", "FORT WORTH",
    ]  # fmt: skip
    return PlaceIndex((n, "XX", n) for n in names)


def test_index_ignores_spaces_in_the_station_city():
    assert _index().find("LA FAYETTE", "XX") == "LAFAYETTE"


def test_index_drops_a_trailing_city_word():
    assert _index().find("CARSON CITY", "XX") == "CARSON"


def test_index_finds_merged_city_county_names():
    assert _index().find("AUGUSTA", "XX") == "AUGUSTA RICHMOND COUNTY"
    assert _index().find("LEXINGTON", "XX") == "LEXINGTON FAYETTE"


def test_index_refuses_ambiguous_prefixes_and_other_states():
    assert _index().find("SPRINGFIELD", "XX") is None
    assert _index().find("AUGUSTA", "YY") is None


def test_index_applies_abbreviation_swaps():
    assert _index().find("FT WORTH", "XX") == "FORT WORTH"
