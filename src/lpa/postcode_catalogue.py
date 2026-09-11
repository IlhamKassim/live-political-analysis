"""Official Malaysian postcode catalogue ingestion and reconciliation.

The catalogue says whether a postcode exists and which city/state labels it
uses. It does not map postcodes to Seats. Verified postcode-to-Seat mappings
remain a separate input; see ADR 0008.
"""

from __future__ import annotations

import csv
import io
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import httpx

DATA_GOV_POSTCODES_URL = "https://storage.data.gov.my/dictionaries/postcodes.csv"
_PACKAGED_SNAPSHOT_PATH = Path(__file__).resolve().parent / "data" / "postcodes_data_gov_my.csv"
DEFAULT_SNAPSHOT_PATH = (
    _PACKAGED_SNAPSHOT_PATH
    if _PACKAGED_SNAPSHOT_PATH.exists()
    else Path(__file__).resolve().parents[2] / "data" / "postcodes_data_gov_my.csv"
)
DEFAULT_REPORT_PATH = Path(__file__).resolve().parents[2] / "data" / "postcode_coverage.json"
_POSTCODE = re.compile(r"^\d{5}$")


@dataclass(frozen=True, order=True)
class PostcodeLocality:
    """One city/state label attached to an official postcode."""

    city: str
    state: str


def parse_postcode_catalogue(raw: str) -> dict[str, tuple[PostcodeLocality, ...]]:
    """Parse data.gov.my's CSV, preserving distinct duplicate localities."""
    reader = csv.DictReader(io.StringIO(raw.lstrip("\ufeff")))
    if reader.fieldnames != ["state", "city", "postcode"]:
        raise ValueError(f"unexpected postcode catalogue columns: {reader.fieldnames!r}")

    grouped: dict[str, set[PostcodeLocality]] = {}
    for row_number, row in enumerate(reader, start=2):
        postcode = row["postcode"].strip()
        if not _POSTCODE.fullmatch(postcode):
            raise ValueError(f"invalid postcode on row {row_number}: {postcode!r}")
        locality = PostcodeLocality(city=row["city"].strip(), state=row["state"].strip())
        if not locality.city or not locality.state:
            raise ValueError(f"missing city/state on row {row_number}")
        grouped.setdefault(postcode, set()).add(locality)
    return {postcode: tuple(sorted(localities)) for postcode, localities in sorted(grouped.items())}


def load_postcode_catalogue(
    path: Path = DEFAULT_SNAPSHOT_PATH,
) -> dict[str, tuple[PostcodeLocality, ...]]:
    """Load the committed official catalogue snapshot."""
    return parse_postcode_catalogue(path.read_text(encoding="utf-8"))


def fetch_postcode_catalogue(url: str = DATA_GOV_POSTCODES_URL) -> str:
    """Fetch the official CSV for an explicit maintainer-run refresh."""
    response = httpx.get(url, timeout=30, follow_redirects=True)
    response.raise_for_status()
    return cast(str, response.text)


def catalogue_for_client(
    catalogue: Mapping[str, Sequence[PostcodeLocality]],
) -> dict[str, list[dict[str, str]]]:
    """Return the compact, JSON-ready official catalogue shape."""
    return {
        postcode: [{"city": item.city, "state": item.state} for item in localities]
        for postcode, localities in sorted(catalogue.items())
    }


def coverage_report(
    catalogue: Mapping[str, Sequence[PostcodeLocality]],
    mapped_postcodes: Iterable[str],
) -> dict[str, object]:
    """Compare official validity coverage with verified Seat mappings."""
    official = set(catalogue)
    mapped = set(mapped_postcodes)
    mapped_official = official & mapped
    return {
        "official_postcode_count": len(official),
        "verified_mapping_count": len(mapped),
        "official_with_verified_mapping_count": len(mapped_official),
        "official_unresolved_count": len(official - mapped),
        "verified_not_in_official_catalogue_count": len(mapped - official),
        "verified_not_in_official_catalogue": sorted(mapped - official),
    }


def write_coverage_report(
    catalogue: Mapping[str, Sequence[PostcodeLocality]],
    mapped_postcodes: Iterable[str],
    path: Path = DEFAULT_REPORT_PATH,
    *,
    retrieved_date: str | None = None,
) -> None:
    """Write a durable, human-readable reconciliation report."""
    if retrieved_date is None and path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(existing, dict) and isinstance(existing.get("_source"), dict):
                val = existing["_source"].get("retrieved")
                if isinstance(val, str) and val:
                    retrieved_date = val
        except (json.JSONDecodeError, OSError):
            pass

    report = {
        "_comment": [
            "Coverage between data.gov.my's official postcode catalogue and the separately",
            "verified postcode-to-Seat mappings. Official validity does not imply a Seat mapping.",
            "Verified mappings absent from the current official catalogue are preserved and listed.",
        ],
        "_source": {
            "name": "data.gov.my Malaysian postcode catalogue",
            "dataset_url": DATA_GOV_POSTCODES_URL,
            "snapshot": "data/postcodes_data_gov_my.csv",
            "retrieved": retrieved_date or datetime.now(UTC).date().isoformat(),
        },
        **coverage_report(catalogue, mapped_postcodes),
    }
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
