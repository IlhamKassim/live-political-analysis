import json

import pytest

from lpa.postcode_catalogue import (
    PostcodeLocality,
    catalogue_for_client,
    coverage_report,
    load_postcode_catalogue,
    parse_postcode_catalogue,
    write_coverage_report,
)


def test_parser_normalizes_whitespace_and_keeps_distinct_duplicate_localities():
    raw = "state,city,postcode\n Selangor , Shah Alam ,40160\nSelangor,Sungai Buloh,40160\n"

    assert parse_postcode_catalogue(raw) == {
        "40160": (
            PostcodeLocality(city="Shah Alam", state="Selangor"),
            PostcodeLocality(city="Sungai Buloh", state="Selangor"),
        )
    }


def test_parser_rejects_schema_drift_and_bad_postcodes():
    with pytest.raises(ValueError, match="columns"):
        parse_postcode_catalogue("postcode,town\n43000,Kajang\n")
    with pytest.raises(ValueError, match="invalid postcode"):
        parse_postcode_catalogue("state,city,postcode\nSelangor,Kajang,4300\n")


def test_reconciliation_preserves_mapped_codes_missing_from_official_catalogue():
    catalogue = {"43000": (PostcodeLocality("Kajang", "Selangor"),), "50000": ()}
    report = coverage_report(catalogue, ["43000", "43701"])

    assert report == {
        "official_postcode_count": 2,
        "verified_mapping_count": 2,
        "official_with_verified_mapping_count": 1,
        "official_unresolved_count": 1,
        "verified_not_in_official_catalogue_count": 1,
        "verified_not_in_official_catalogue": ["43701"],
    }


def test_catalogue_for_client_uses_city_and_state_labels():
    catalogue = {"43000": (PostcodeLocality("Kajang", "Selangor"),)}
    assert catalogue_for_client(catalogue) == {"43000": [{"city": "Kajang", "state": "Selangor"}]}


def test_shipped_snapshot_and_report_cover_the_official_catalogue(tmp_path):
    catalogue = load_postcode_catalogue()
    assert len(catalogue) == 2930
    assert catalogue["40160"] == (
        PostcodeLocality(city="Shah Alam", state="Selangor"),
        PostcodeLocality(city="Sungai Buloh", state="Selangor"),
    )

    output = tmp_path / "coverage.json"
    write_coverage_report(catalogue, ["40160"], output)
    assert json.loads(output.read_text())["official_unresolved_count"] == 2929
