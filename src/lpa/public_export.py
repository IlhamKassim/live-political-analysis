"""A machine-readable export of the Projection, alongside the public page.

The public page (`public_page.py`) is HTML for a reader. This is the same
Projection as JSON and CSV, for a journalist, researcher, or third-party app
that wants to build on the numbers or cite them directly — one of the ways
this project can earn the kind of vouching that routes trust through a known,
credible source (ISEAS Perspective, "Media Literacy in Malaysia").

Follows public_page's seam: `export_model` reads Storage-shaped data and
returns a plain, JSON-serializable `dict` — no file I/O, no string
formatting decisions baked in. `to_json`/`to_csv` turn that dict into the two
on-disk shapes. `build_export` is the I/O half, reading Storage the way
`public_page.build_page` does, from the same data.

The export carries the page's own caveats as fields, not only as prose on the
HTML page — a copy of the numbers that travels without the page's framing
should not lose the caveat either.

`SCHEMA_VERSION` exists so a future breaking change to this shape has
somewhere to say so; there is no consumer yet to break, so this ships a
reasonable v1 rather than a versioning scheme nobody needs.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy.engine import Engine

from lpa.domain import Coalition, Projection, SeatBaseline
from lpa.public_page import StateRollupRow, TrendReading

SCHEMA_VERSION = 1

CAVEAT = (
    "Two constants in the Swing Model were set by judgement, not fitted to "
    "data. Treat every figure here as a direction, not a forecast. Every "
    "Seat's call is arithmetic against its GE15 result under a "
    "state-uniform swing, never a bespoke judgement about that constituency."
)


def export_model(
    projection: Projection,
    baseline: Sequence[SeatBaseline],
    names: Mapping[Coalition, str],
    sensitivity_table: Sequence[tuple[float, int]] = (),
    state_rollup: Sequence[StateRollupRow] = (),
    trend: Sequence[TrendReading] = (),
) -> dict[str, Any]:
    """Build the export payload as a plain, JSON-serializable dict.

    Pure: reads only its arguments, decides no file shape. A Seat Call
    without a matching Baseline Seat is a Storage inconsistency the export
    surfaces rather than papers over — `seat_call_card.build_all_cards`
    raises on the same condition.

    `sensitivity_table`, `state_rollup`, and `trend` default to empty rather
    than being required, so every existing caller (and every existing test)
    that only cares about the per-Seat ledger keeps working unchanged; only
    `build_export` — which builds a full `PageModel` via `public_page.
    page_model` the way `public_page.build_page` does — passes them. They
    are `PageModel`'s own computed values, not re-derived here: this
    function only reshapes them into plain, JSON-serializable structures,
    the same way it already does for `seats`.

    `trend` is carried exactly as `PageModel.trend` computed it — 0, 1, or
    several readings — never padded or faked to look like a trend line. The
    frontend applies the same "need >= 2 readings to plot a line" rule
    `PageModel.trend_is_plotted`/`trend_is_joined` state, rather than this
    export deciding that for it.
    """
    baseline_by_code = {seat.code: seat for seat in baseline}
    seats = []
    for call in projection.seat_calls:
        seat = baseline_by_code.get(call.code)
        if seat is None:
            raise ValueError(f"Seat Call {call.code!r} has no Baseline Seat.")
        seats.append(
            {
                "code": call.code,
                "name": seat.name,
                "state": seat.state,
                "coalition": call.coalition,
                "coalition_name": names.get(call.coalition, call.coalition),
                "margin": call.margin,
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "computed_at": projection.computed_at.isoformat(),
        "coalition_seat_totals": dict(projection.coalition_seat_totals),
        "government_majority": projection.government_majority,
        "seats": seats,
        "caveat": CAVEAT,
        "sensitivity_table": [
            {"sentiment_sensitivity": value, "government_seat_total": total}
            for value, total in sensitivity_table
        ],
        "state_rollup": [
            {
                "state": row.state,
                "seats": row.seats,
                "baseline_totals": [
                    {"coalition": coalition, "seats": count}
                    for coalition, count in row.baseline_totals
                ],
                "projected_totals": [
                    {"coalition": coalition, "seats": count}
                    for coalition, count in row.projected_totals
                ],
                "swing": [
                    {"coalition": coalition, "swing": swing} for coalition, swing in row.swing
                ],
                "signal_active": row.signal_active,
            }
            for row in state_rollup
        ],
        "trend": [
            {
                "day": reading.day.isoformat(),
                "government_seats": reading.government_seats,
                "margin": reading.margin,
            }
            for reading in trend
        ],
    }


def to_json(payload: Mapping[str, Any]) -> str:
    """`payload` as pretty-printed JSON, newline-terminated."""
    return json.dumps(payload, indent=2) + "\n"


_CSV_FIELDS = ("code", "name", "state", "coalition", "coalition_name", "margin")


def to_csv(payload: Mapping[str, Any]) -> str:
    """`payload`'s Seats as CSV — one row per Seat, header first.

    Flattens only the per-Seat rows; `coalition_seat_totals`, `caveat` and
    the other whole-Projection fields have no natural row and stay in the
    JSON export.
    """
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=_CSV_FIELDS)
    writer.writeheader()
    for seat in payload["seats"]:
        writer.writerow({field: seat[field] for field in _CSV_FIELDS})
    return buf.getvalue()


def build_export(engine: Engine) -> tuple[str, str]:
    """Read Storage and return `(json_body, csv_body)` for the latest Projection.

    Builds a full `PageModel` via `public_page.page_model` — the same
    construction `public_page.build_page` uses — so the sensitivity table,
    per-state rollup, and Majority-margin trend the export carries are the
    identical numbers the public page states, never a second derivation of
    them that could drift from the first.
    """
    from lpa.config import (
        coalition_names,
        load_coalition_config,
        load_election_status,
        load_state_election_signals,
        swing_model_config,
    )
    from lpa.public_page import page_model
    from lpa.storage import (
        load_projections,
        load_seat_baselines,
        load_sentiment_snapshots,
        load_state_swing,
    )

    projections = load_projections(engine)
    if not projections:
        raise SystemExit("No Projection stored. Run `python -m lpa.pipeline` to compute one.")
    baseline = load_seat_baselines(engine)
    if not baseline:
        raise SystemExit("No Seat Baseline in Storage. Run `python -m lpa.baseline_loader` first.")

    config = load_coalition_config()
    names = coalition_names(config)
    snapshots = load_sentiment_snapshots(engine)
    latest_sentiment = snapshots[-1].sentiment if snapshots else None
    model = page_model(
        projection=projections[-1],
        baseline=baseline,
        status=load_election_status(),
        config=swing_model_config(config),
        names=names,
        sentiment=latest_sentiment,
        state_election_signals=load_state_election_signals(),
        total_seats=config["total_seats"],
        state_swing=load_state_swing(engine, projections[-1].computed_at),
        history=projections,
    )
    payload = export_model(
        projections[-1],
        baseline,
        names,
        sensitivity_table=model.sensitivity_table,
        state_rollup=model.state_rollup,
        trend=model.trend,
    )
    return to_json(payload), to_csv(payload)


def main() -> None:
    """Render the export from Storage and write it to disk."""
    import argparse
    from pathlib import Path

    from lpa.storage import connect

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("public"),
        help="directory to write projection.json/projection.csv into (default: public)",
    )
    args = parser.parse_args()

    json_body, csv_body = build_export(connect())
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "projection.json").write_text(json_body, encoding="utf-8")
    (args.output_dir / "projection.csv").write_text(csv_body, encoding="utf-8")
    print(f"Wrote projection.json and projection.csv to {args.output_dir}")


if __name__ == "__main__":
    main()
