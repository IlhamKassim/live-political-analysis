"""Build clearly labelled postcode-to-Seat estimates from GeoNames points.

These estimates are separate from the verified postcode index. GeoNames says
its coordinates are estimated and may be inferred from nearby postcodes. A
point inside a Seat is therefore useful as a fallback, but is not proof that
the whole postcode belongs to that Seat.
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lpa.config import data_file

GEONAMES_URL = "https://download.geonames.org/export/zip/MY.zip"
GEONAMES_SITE = "https://www.geonames.org/"
GEONAMES_LICENCE_URL = "https://creativecommons.org/licenses/by/4.0/"
DOSM_BOUNDARIES_URL = (
    "https://raw.githubusercontent.com/dosm-malaysia/data-open/main/"
    "datasets/geodata/electoral_0_parlimen.geojson"
)
DEFAULT_ESTIMATES_PATH = data_file("postcode_seat_estimates.json")
DEFAULT_QUALITY_PATH = data_file("postcode_seat_estimate_quality.json")


@dataclass(frozen=True, order=True)
class GeoNamesPoint:
    longitude: float
    latitude: float
    accuracy: int | None


def parse_geonames(raw: str) -> dict[str, tuple[GeoNamesPoint, ...]]:
    """Parse GeoNames' 12-column Malaysian postal-code text file."""
    points: dict[str, dict[tuple[float, float], GeoNamesPoint]] = defaultdict(dict)
    for line_number, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            continue
        fields = line.split("\t")
        if len(fields) != 12:
            raise ValueError(f"GeoNames line {line_number} has {len(fields)} columns, expected 12")
        country, postcode = fields[0], fields[1]
        if country != "MY":
            raise ValueError(f"GeoNames line {line_number} has unexpected country {country!r}")
        if len(postcode) != 5 or not postcode.isdigit():
            raise ValueError(f"GeoNames line {line_number} has invalid postcode {postcode!r}")
        try:
            latitude = float(fields[9])
            longitude = float(fields[10])
            accuracy = int(fields[11]) if fields[11] else None
        except ValueError as exc:
            raise ValueError(
                f"GeoNames line {line_number} has an invalid coordinate or accuracy"
            ) from exc
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError(f"GeoNames line {line_number} has an out-of-range coordinate")
        coordinate = (longitude, latitude)
        existing = points[postcode].get(coordinate)
        if existing is None or (accuracy or -1) > (existing.accuracy or -1):
            points[postcode][coordinate] = GeoNamesPoint(longitude, latitude, accuracy)
    return {
        postcode: tuple(sorted(postcode_points.values()))
        for postcode, postcode_points in sorted(points.items())
    }


def parse_seat_boundaries(data: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    """Validate and return Seat geometries from the unsimplified DOSM GeoJSON."""
    crs_name = data.get("crs", {}).get("properties", {}).get("name")
    if crs_name != "urn:ogc:def:crs:OGC:1.3:CRS84":
        raise ValueError("Seat boundaries must explicitly declare OGC CRS84")
    features = data.get("features")
    if not isinstance(features, list):
        raise TypeError("Seat boundaries are missing a features array")
    boundaries: dict[str, Mapping[str, Any]] = {}
    for feature in features:
        if not isinstance(feature, dict):
            raise TypeError("Seat boundary feature is not an object")
        properties = feature.get("properties")
        geometry = feature.get("geometry")
        code = properties.get("code_parlimen") if isinstance(properties, dict) else None
        if not isinstance(code, str) or not code.startswith("P."):
            raise ValueError("Seat boundary feature has an invalid code_parlimen")
        if code in boundaries:
            raise ValueError(f"Seat boundary code is duplicated: {code}")
        if not isinstance(geometry, dict) or geometry.get("type") not in {
            "Polygon",
            "MultiPolygon",
        }:
            raise ValueError(f"Seat {code} has unsupported geometry")
        boundaries[code] = geometry
    return dict(sorted(boundaries.items()))


def _point_on_segment(x: float, y: float, ax: float, ay: float, bx: float, by: float) -> bool:
    cross = (x - ax) * (by - ay) - (y - ay) * (bx - ax)
    tolerance = 1e-12 * max(1.0, abs(x), abs(y), abs(ax), abs(ay), abs(bx), abs(by))
    if abs(cross) > tolerance:
        return False
    return (
        min(ax, bx) - tolerance <= x <= max(ax, bx) + tolerance
        and min(ay, by) - tolerance <= y <= max(ay, by) + tolerance
    )


def _ring_location(x: float, y: float, ring: Sequence[Sequence[float]]) -> int:
    """Return 1 inside, 0 outside, or 2 on the ring boundary."""
    inside = False
    closed_ring = list(ring)
    for first, second in zip(closed_ring, closed_ring[1:] + closed_ring[:1]):
        ax, ay = float(first[0]), float(first[1])
        bx, by = float(second[0]), float(second[1])
        if _point_on_segment(x, y, ax, ay, bx, by):
            return 2
        if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
            inside = not inside
    return 1 if inside else 0


def point_in_geometry(x: float, y: float, geometry: Mapping[str, Any]) -> bool:
    """Return whether a point is inside or touches a Polygon/MultiPolygon."""
    coordinates = geometry.get("coordinates")
    polygons = [coordinates] if geometry.get("type") == "Polygon" else coordinates
    if not isinstance(polygons, list):
        raise TypeError("geometry coordinates must be an array")
    for polygon in polygons:
        if not isinstance(polygon, list) or not polygon:
            continue
        outer = _ring_location(x, y, polygon[0])
        if outer == 0:
            continue
        if outer == 2:
            return True
        excluded_by_hole = False
        for hole in polygon[1:]:
            hole_location = _ring_location(x, y, hole)
            if hole_location == 2:
                return True
            if hole_location == 1:
                excluded_by_hole = True
                break
        if not excluded_by_hole:
            return True
    return False


def build_estimates(
    points: Mapping[str, Sequence[GeoNamesPoint]],
    boundaries: Mapping[str, Mapping[str, Any]],
) -> dict[str, tuple[str, ...]]:
    """Union every Seat containing any GeoNames point for each postcode."""
    result: dict[str, tuple[str, ...]] = {}
    for postcode, postcode_points in sorted(points.items()):
        matches = {
            code
            for point in postcode_points
            for code, geometry in boundaries.items()
            if point_in_geometry(point.longitude, point.latitude, geometry)
        }
        if matches:
            result[postcode] = tuple(sorted(matches))
    return result


def _percentile(values: Sequence[int], percentile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    rank = (len(ordered) - 1) * percentile
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return float(ordered[lower])
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower)


def _quality_metrics(
    verified: Mapping[str, Sequence[str]], estimates: Mapping[str, Sequence[str]]
) -> dict[str, Any]:
    postcodes = sorted(verified)
    verified_seats = sum(len(set(verified[p])) for p in postcodes)
    recalled = sum(len(set(verified[p]) & set(estimates.get(p, ()))) for p in postcodes)
    exact = sum(set(verified[p]) == set(estimates.get(p, ())) for p in postcodes)
    sizes = [len(set(estimates[p])) for p in postcodes if estimates.get(p)]
    unresolved = sum(not estimates.get(p) for p in postcodes)
    return {
        "validation_postcode_count": len(postcodes),
        "verified_seat_count": verified_seats,
        "verified_seat_recall": recalled / verified_seats if verified_seats else 0.0,
        "exact_set_agreement": exact / len(postcodes) if postcodes else 0.0,
        "exact_set_agreement_count": exact,
        "unresolved_count": unresolved,
        "unresolved_rate": unresolved / len(postcodes) if postcodes else 0.0,
        "candidate_set_size": {
            "mean": sum(sizes) / len(sizes) if sizes else 0.0,
            "median": _percentile(sizes, 0.5),
            "p95": _percentile(sizes, 0.95),
            "maximum": max(sizes, default=0),
            "histogram": dict(
                sorted(Counter(map(str, sizes)).items(), key=lambda item: int(item[0]))
            ),
        },
    }


def build_quality_report(
    verified: Mapping[str, Sequence[str]],
    estimates: Mapping[str, Sequence[str]],
    postcode_states: Mapping[str, str],
    *,
    maximum_candidate_set: int = 2,
) -> dict[str, Any]:
    """Compare point estimates with every existing verified postcode mapping."""
    report = _quality_metrics(verified, estimates)
    failures = []
    for postcode in sorted(verified):
        missing = set(verified[postcode]) - set(estimates.get(postcode, ()))
        if missing:
            failures.append(
                {
                    "postcode": postcode,
                    "state": postcode_states.get(postcode, "Unknown"),
                    "verified": sorted(set(verified[postcode])),
                    "estimated": sorted(set(estimates.get(postcode, ()))),
                }
            )
    by_state: dict[str, Any] = {}
    states = sorted({postcode_states.get(postcode, "Unknown") for postcode in verified})
    for state in states:
        state_verified = {
            postcode: codes
            for postcode, codes in verified.items()
            if postcode_states.get(postcode, "Unknown") == state
        }
        by_state[state] = _quality_metrics(state_verified, estimates)
    large_sets = [
        {"postcode": postcode, "estimated": list(codes), "size": len(codes)}
        for postcode, codes in sorted(estimates.items())
        if len(codes) > maximum_candidate_set
    ]
    report.update(
        {
            "recall_failures": failures,
            "candidate_sets_above_proposed_maximum": large_sets,
            "proposed_maximum_candidate_set": maximum_candidate_set,
            "by_state": by_state,
            "postcode_89607": list(estimates.get("89607", ())),
        }
    )
    return report


def estimates_document(
    estimates: Mapping[str, Sequence[str]], point_count: int, generated_at: str | None = None
) -> dict[str, Any]:
    return {
        "_comment": [
            "Estimated postcode -> candidate Seat code(s), kept separate from verified mappings.",
            "Each result is the union of Seats containing GeoNames estimated points for that postcode.",
            "A point is not a postcode boundary. These entries must always be labelled as estimates.",
        ],
        "_source": {
            "postcode_points": {
                "name": "GeoNames Postal Codes — Malaysia",
                "dataset_url": GEONAMES_URL,
                "website": GEONAMES_SITE,
                "licence": "CC BY 4.0",
                "licence_url": GEONAMES_LICENCE_URL,
                "coordinate_note": "GeoNames describes latitude/longitude as estimated.",
            },
            "seat_boundaries": {
                "name": "Department of Statistics Malaysia parliamentary boundaries",
                "dataset_url": DOSM_BOUNDARIES_URL,
                "crs": "OGC CRS84 (longitude, latitude)",
                "vintage_note": "The published file does not state its delimitation vintage.",
            },
            "generated": generated_at or "not recorded",
            "generated_by": "scripts/refresh_postcode_seat_estimates.py",
        },
        "point_count": point_count,
        "postcode_count": len(estimates),
        "postcodes": {postcode: list(codes) for postcode, codes in sorted(estimates.items())},
    }


def write_estimates(
    path: Path,
    estimates: Mapping[str, Sequence[str]],
    point_count: int,
    generated_at: str | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(estimates_document(estimates, point_count, generated_at), indent=2) + "\n",
        encoding="utf-8",
    )


def load_estimates(path: Path = DEFAULT_ESTIMATES_PATH) -> dict[str, tuple[str, ...]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    raw = data.get("postcodes") if isinstance(data, dict) else None
    if not isinstance(raw, dict):
        raise TypeError("postcode estimate file is missing postcodes")
    estimates: dict[str, tuple[str, ...]] = {}
    for postcode, codes in raw.items():
        if (
            not isinstance(postcode, str)
            or len(postcode) != 5
            or not postcode.isdigit()
            or not isinstance(codes, list)
            or not codes
            or any(not isinstance(code, str) or not code.startswith("P.") for code in codes)
        ):
            raise ValueError(f"invalid postcode estimate for {postcode!r}")
        estimates[postcode] = tuple(sorted(set(codes)))
    return estimates
