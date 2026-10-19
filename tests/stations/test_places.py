from apps.stations.places import city_variants, clean_place_name


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
