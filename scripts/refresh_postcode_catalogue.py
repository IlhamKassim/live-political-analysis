"""Refresh the committed data.gov.my postcode snapshot and coverage report."""

from __future__ import annotations

from lpa.config import load_postcode_seat_index
from lpa.postcode_catalogue import (
    DEFAULT_SNAPSHOT_PATH,
    fetch_postcode_catalogue,
    load_postcode_catalogue,
    write_coverage_report,
)


def main() -> None:
    raw = fetch_postcode_catalogue()
    DEFAULT_SNAPSHOT_PATH.write_text(raw, encoding="utf-8")
    catalogue = load_postcode_catalogue()
    mapped = load_postcode_seat_index()
    write_coverage_report(catalogue, mapped)
    print(f"Wrote {len(catalogue):,} official postcodes to {DEFAULT_SNAPSHOT_PATH}")


if __name__ == "__main__":
    main()