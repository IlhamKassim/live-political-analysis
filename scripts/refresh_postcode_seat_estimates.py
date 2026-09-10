#!/usr/bin/env python3
"""Refresh GeoNames postcode-point Seat estimates and their quality report."""

from __future__ import annotations

import argparse
import io
import json
import urllib.request
import zipfile
from pathlib import Path

from lpa.config import load_postcode_seat_index
from lpa.postcode_catalogue import load_postcode_catalogue
from lpa.postcode_seat_estimates import (
    DEFAULT_ESTIMATES_PATH,
    DEFAULT_QUALITY_PATH,
    DOSM_BOUNDARIES_URL,
    GEONAMES_URL,
    build_estimates,
    build_quality_report,
    parse_geonames,
    parse_seat_boundaries,
    write_estimates,
)


def read_url(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--geonames", help="local MY.zip; downloads GeoNames when omitted")
    parser.add_argument("--boundaries", help="local GeoJSON; downloads DOSM when omitted")
    parser.add_argument(
        "--generated-at",
        help="optional ISO date for metadata; omitted by default for deterministic output",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_ESTIMATES_PATH)
    parser.add_argument("--quality-output", type=Path, default=DEFAULT_QUALITY_PATH)
    args = parser.parse_args()

    archive_bytes = Path(args.geonames).read_bytes() if args.geonames else read_url(GEONAMES_URL)
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        points = parse_geonames(archive.read("MY.txt").decode("utf-8"))

    boundary_bytes = Path(args.boundaries).read_bytes() if args.boundaries else read_url(DOSM_BOUNDARIES_URL)
    boundaries = parse_seat_boundaries(json.loads(boundary_bytes))
    estimates = build_estimates(points, boundaries)

    verified = {
        postcode: tuple(match.seat_code for match in matches)
        for postcode, matches in load_postcode_seat_index().items()
    }
    catalogue = load_postcode_catalogue()
    states = {
        postcode: " / ".join(sorted({locality.state for locality in localities}))
        for postcode, localities in catalogue.items()
    }
    quality = build_quality_report(verified, estimates, states)
    quality.update(
        {
            "_comment": [
                "Quality audit against all existing verified postcode-to-Seat mappings.",
                "Review this report before exposing estimates in the public lookup.",
            ],
            "estimated_postcode_count": len(estimates),
            "geonames_postcode_count": len(points),
            "geonames_point_count": sum(map(len, points.values())),
        }
    )

    write_estimates(
        args.output,
        estimates,
        sum(map(len, points.values())),
        generated_at=args.generated_at,
    )
    args.quality_output.parent.mkdir(parents=True, exist_ok=True)
    args.quality_output.write_text(json.dumps(quality, indent=2) + "\n", encoding="utf-8")
    print(
        f"Wrote {args.output} ({len(estimates)} postcodes) and {args.quality_output}; "
        f"verified-Seat recall={quality['verified_seat_recall']:.1%}, "
        f"exact agreement={quality['exact_set_agreement']:.1%}, "
        f"unresolved={quality['unresolved_rate']:.1%}, "
        f"89607={quality['postcode_89607']}"
    )


if __name__ == "__main__":
    main()