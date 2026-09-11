"""Export and verify the shared dataset consumed by the published site."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from sqlalchemy.engine import Engine

from lpa.public_export import build_export as projection_export
from lpa.sentiment_export import build_export as sentiment_export


def validate_payloads(projection: dict, sentiment: dict) -> None:
    """Reject mismatched snapshots or totals before writing release files."""
    if not projection.get("computed_at") or projection["computed_at"] != sentiment.get(
        "computed_at"
    ):
        raise ValueError("Projection and Sentiment must describe the same snapshot date")
    seats = projection["seats"]
    if not seats or len({seat["code"] for seat in seats}) != len(seats):
        raise ValueError("Projection must contain unique Seat Calls")
    counts = Counter(seat["coalition"] for seat in seats)
    totals = projection["coalition_seat_totals"]
    if counts != Counter({key: value for key, value in totals.items() if value}):
        raise ValueError("Coalition totals disagree with Seat Calls")


def export_release(engine: Engine, output: Path) -> None:
    """Write identical Projection data for downloads, the app and prerendering."""
    projection, csv_body = projection_export(engine)
    sentiment = sentiment_export(engine)
    validate_payloads(json.loads(projection), json.loads(sentiment))
    files = {
        "projection.json": projection,
        "projection.csv": csv_body,
        "app/data/projection.json": projection,
        "app/data/sentiment.json": sentiment,
    }
    for name, body in files.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    manifest = {
        "computed_at": json.loads(projection)["computed_at"],
        "sha256": {
            name: hashlib.sha256((output / name).read_bytes()).hexdigest() for name in files
        },
    }
    (output / "release.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def check_release(output: Path) -> None:
    """Reject stale copies, altered exports and inconsistent figures."""
    manifest = json.loads((output / "release.json").read_text())
    required = {
        "projection.json",
        "projection.csv",
        "app/data/projection.json",
        "app/data/sentiment.json",
    }
    if set(manifest["sha256"]) != required:
        raise ValueError("Release manifest must cover every export")
    for name, digest in manifest["sha256"].items():
        if hashlib.sha256((output / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Release export changed after generation: {name}")
    projection = json.loads((output / "projection.json").read_text())
    app_projection = json.loads((output / "app/data/projection.json").read_text())
    sentiment = json.loads((output / "app/data/sentiment.json").read_text())
    if projection != app_projection or projection["computed_at"] != manifest["computed_at"]:
        raise ValueError("Published Projection copies disagree")
    validate_payloads(projection, sentiment)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("public"))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        check_release(args.output_dir)
    else:
        from lpa.storage import connect

        engine = connect()
        try:
            export_release(engine, args.output_dir)
        finally:
            engine.dispose()


if __name__ == "__main__":
    main()
