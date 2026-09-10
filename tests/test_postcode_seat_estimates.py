from __future__ import annotations

import json
from pathlib import Path

import pytest

from lpa.postcode_seat_estimates import (
    DEFAULT_ESTIMATES_PATH,
    DEFAULT_QUALITY_PATH,
    GeoNamesPoint,
    build_estimates,
    build_quality_report,
    load_estimates,
    parse_geonames,
    parse_seat_boundaries,
    point_in_geometry,
    write_estimates,
)


def geonames_row(postcode: str, latitude: str, longitude: str, accuracy: str = "3") -> str:
    return f"MY\t{postcode}\tPlace\tState\tST\t\t\t\t\t{latitude}\t{longitude}\t{accuracy}"


def test_parse_geonames_preserves_distinct_points_and_removes_exact_duplicates():
    raw = "\n".join(
        [
            geonames_row("89607", "5.6064", "115.9625"),
            geonames_row("89607", "5.7000", "116.0000"),
            geonames_row("89607", "5.6064", "115.9625"),
            geonames_row("89607", "5.6064", "115.9625", "4"),
        ]
    )

    assert parse_geonames(raw) == {
        "89607": (
            GeoNamesPoint(longitude=115.9625, latitude=5.6064, accuracy=4),
            GeoNamesPoint(longitude=116.0, latitude=5.7, accuracy=3),
        )
    }


@pytest.mark.parametrize(
    "raw, message",
    [
        ("MY\t1234\tPlace\tState\tST\t\t\t\t\t1\t2\t3", "postcode"),
        (geonames_row("12345", "north", "2"), "coordinate"),
        ("SG\t12345\tPlace\tState\tST\t\t\t\t\t1\t2\t3", "country"),
    ],
)
def test_parse_geonames_rejects_malformed_rows(raw: str, message: str):
    with pytest.raises(ValueError, match=message):
        parse_geonames(raw)


def square(x0: float, y0: float, x1: float, y1: float) -> list[list[float]]:
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]


def multipolygon(*rings: list[list[float]]) -> dict[str, object]:
    return {"type": "MultiPolygon", "coordinates": [[[point for point in ring]] for ring in rings]}


def test_point_in_geometry_includes_outer_boundaries_and_excludes_hole_interiors():
    geometry = {
        "type": "MultiPolygon",
        "coordinates": [[square(0, 0, 10, 10), square(3, 3, 7, 7)]],
    }

    assert point_in_geometry(1, 1, geometry)
    assert point_in_geometry(0, 5, geometry)
    assert point_in_geometry(3, 5, geometry)  # touching a hole boundary
    assert not point_in_geometry(5, 5, geometry)
    assert not point_in_geometry(20, 20, geometry)


def test_boundary_point_matches_every_touching_seat_and_duplicate_points_are_unioned():
    boundaries = {
        "P.001": multipolygon(square(0, 0, 1, 1)),
        "P.002": multipolygon(square(1, 0, 2, 1)),
    }
    points = {
        "12345": (
            GeoNamesPoint(longitude=1, latitude=0.5, accuracy=3),
            GeoNamesPoint(longitude=0.5, latitude=0.5, accuracy=3),
        )
    }

    assert build_estimates(points, boundaries) == {"12345": ("P.001", "P.002")}


def test_parse_seat_boundaries_requires_crs84_and_unique_seat_codes():
    feature = {
        "type": "Feature",
        "properties": {"code_parlimen": "P.001"},
        "geometry": multipolygon(square(0, 0, 1, 1)),
    }
    data = {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": [feature],
    }
    assert set(parse_seat_boundaries(data)) == {"P.001"}

    data["crs"] = {"type": "name", "properties": {"name": "EPSG:3857"}}
    with pytest.raises(ValueError, match="CRS84"):
        parse_seat_boundaries(data)


def test_quality_report_measures_recall_agreement_sizes_and_failures():
    verified = {"11111": ("P.001",), "22222": ("P.001", "P.002"), "33333": ("P.003",)}
    estimates = {"11111": ("P.001",), "22222": ("P.002",), "44444": ("P.004",)}
    states = {"11111": "A", "22222": "A", "33333": "B"}

    report = build_quality_report(verified, estimates, states)

    assert report["validation_postcode_count"] == 3
    assert report["verified_seat_recall"] == 0.5
    assert report["exact_set_agreement"] == pytest.approx(1 / 3)
    assert report["unresolved_count"] == 1
    assert report["candidate_set_size"]["histogram"] == {"1": 2}
    assert report["recall_failures"] == [
        {"postcode": "22222", "state": "A", "verified": ["P.001", "P.002"], "estimated": ["P.002"]},
        {"postcode": "33333", "state": "B", "verified": ["P.003"], "estimated": []},
    ]
    assert report["by_state"]["B"]["unresolved_count"] == 1


def test_estimate_file_round_trips_and_rejects_bad_data(tmp_path: Path):
    path = tmp_path / "estimates.json"
    write_estimates(path, {"89607": ("P.175",)}, point_count=1, generated_at="2026-09-10")

    assert load_estimates(path) == {"89607": ("P.175",)}
    payload = json.loads(path.read_text())
    assert payload["_source"]["postcode_points"]["licence"] == "CC BY 4.0"
    assert payload["postcodes"]["89607"] == ["P.175"]

    path.write_text('{"postcodes":{"bad":[]}}')
    with pytest.raises(ValueError, match="invalid postcode estimate"):
        load_estimates(path)


def test_shipped_estimates_and_quality_report_record_the_failed_public_gate():
    estimates = load_estimates(DEFAULT_ESTIMATES_PATH)
    quality = json.loads(DEFAULT_QUALITY_PATH.read_text(encoding="utf-8"))

    assert estimates["89607"] == ("P.176",)
    assert quality["postcode_89607"] == ["P.176"]
    assert quality["geonames_postcode_count"] == 2757
    assert quality["estimated_postcode_count"] == len(estimates) == 2740
    assert quality["verified_seat_recall"] < 0.6
    assert quality["exact_set_agreement"] < 0.6
    assert len(quality["recall_failures"]) == 143
