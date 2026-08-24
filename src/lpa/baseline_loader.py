"""Baseline Loader: GE15 public-dataset rows -> per-Seat Baseline records.

The transform is pure — rows in, `SeatBaseline`s out. Fetching the rows and
writing them to Storage are separate steps (`lpa.sources`, `lpa.storage`) so
this stays testable against fixtures.

Source rows come from Thevesh Theva's Malaysian election dataset, which
publishes GE15 at candidate level plus a parliamentary census. Candidates are
rolled up to Coalitions because the winning ballot line is a party, and some
component parties stood under their own banner where their Coalition was not
registered — DAP in Sarawak, PAS in Sabah and Sarawak.

The rollup reconciles with the published GE15 result: PN 74, BN 30, GPS 23,
GRS 6, WARISAN 3. PH comes to 81 rather than the 82 usually reported, because
MUDA's single Seat is counted to MUDA here — it contested on PH's ticket but
is not a PH component, and Coalition membership is config either way.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence

from lpa.domain import Coalition, SeatBaseline

DEMOGRAPHIC_FIELDS = (
    "ethnicity_proportion_bumi",
    "ethnicity_proportion_chinese",
    "ethnicity_proportion_indian",
    "ethnicity_proportion_other",
    "age_proportion_18_above",
    "income_median",
)

_SEAT = re.compile(r"^(P\.\d+)\s+(.*)$")
_SHORT_CODE = re.compile(r"\(([^)]+)\)\s*$")


def build_seat_baselines(
    candidates: Iterable[Mapping[str, str]],
    census: Iterable[Mapping[str, str]],
    party_to_coalition: Mapping[str, Coalition],
) -> list[SeatBaseline]:
    """Roll GE15 candidate rows up into one Baseline per Seat.

    `party_to_coalition` maps a ballot party name to the Coalition it contested
    under; a party absent from the map keeps its own bracketed short code, so a
    minor party is never merged into a bloc it does not belong to.
    """
    demographics_by_seat = {
        split_seat_label(row["parlimen"])[0]: _demographics(row) for row in census
    }

    votes: dict[str, dict[Coalition, float]] = {}
    seats: dict[str, tuple[str, str]] = {}
    for row in candidates:
        code, name = split_seat_label(row["parlimen"])
        seats[code] = (name, row["state"])
        coalition = coalition_of(row["party"], party_to_coalition)
        tally = votes.setdefault(code, {})
        tally[coalition] = tally.get(coalition, 0.0) + float(row["votes"])

    baselines = []
    for code, (name, state) in seats.items():
        shares = _as_shares(votes[code])
        baselines.append(
            SeatBaseline(
                code=code,
                name=name,
                state=state,
                vote_share=shares,
                margin=_margin(shares),
                demographics=demographics_by_seat.get(code, {}),
            )
        )
    return baselines


def split_seat_label(parlimen: str) -> tuple[str, str]:
    """Split a "P.001 Padang Besar" label into its code and its name.

    Shared with `scripts/build_mp_profiles.py`, which reads the same Thevesh
    Theva dataset for a different purpose — one parser for the label's shape,
    so the two never drift apart on what counts as a valid one.
    """
    match = _SEAT.match(parlimen.strip())
    if not match:
        raise ValueError(f"unrecognised Seat label: {parlimen!r}")
    return match.group(1), match.group(2).strip()


def coalition_of(party: str, party_to_coalition: Mapping[str, Coalition]) -> Coalition:
    """A ballot party's Coalition: the configured rollup, or its own short code.

    Shared with `scripts/build_mp_profiles.py`'s runner-up lookup — the same
    rollup a Seat's `SeatBaseline` uses, so a profile's `runner_up_coalition`
    can never name a Coalition its own Seat's Baseline disagrees with.
    """
    if party in party_to_coalition:
        return party_to_coalition[party]
    match = _SHORT_CODE.search(party.strip())
    return match.group(1) if match else party.strip()


def _as_shares(votes: Mapping[Coalition, float]) -> dict[Coalition, float]:
    total = sum(votes.values())
    if total <= 0:
        raise ValueError("a Seat cannot have zero votes cast")
    return {
        coalition: count / total
        for coalition, count in sorted(votes.items(), key=lambda item: -item[1])
    }


def _margin(shares: Mapping[Coalition, float]) -> float:
    """The winner's lead over the runner-up, at Coalition level.

    A Seat where every candidate rolls up to one Coalition has no Coalition
    runner-up, and so a full margin — correct for a Coalition-level Baseline
    even where the ballot itself was contested.
    """
    ranked: Sequence[float] = sorted(shares.values(), reverse=True)
    return ranked[0] - ranked[1] if len(ranked) > 1 else ranked[0]


def _demographics(row: Mapping[str, str]) -> dict[str, float]:
    return {
        field: float(row[field]) for field in DEMOGRAPHIC_FIELDS if row.get(field) not in (None, "")
    }


def main() -> None:
    """Fetch the GE15 Baseline and write it to Storage. Run once, not daily."""
    from lpa.config import load_coalition_config, party_to_coalition
    from lpa.sources import fetch_ge15_candidates, fetch_parliamentary_census
    from lpa.storage import connect, save_seat_baselines

    config = load_coalition_config()
    baselines = build_seat_baselines(
        fetch_ge15_candidates(),
        fetch_parliamentary_census(),
        party_to_coalition(config),
    )

    expected = config["total_seats"]
    if len(baselines) != expected:
        raise ValueError(
            f"expected a Baseline for all {expected} Seats, built {len(baselines)} "
            "— the upstream dataset may have changed or the fetch was truncated"
        )

    written = save_seat_baselines(connect(), baselines)
    print(f"Wrote {written} Seat Baselines.")


if __name__ == "__main__":
    main()
