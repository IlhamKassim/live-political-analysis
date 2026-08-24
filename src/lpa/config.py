"""Reading the Coalition configuration that lives in `data/coalitions.json`.

Government Coalition membership and the party rollup are data, not code, so a
realignment is a config edit (issue #1, story 20).
"""

from __future__ import annotations

import json
from collections.abc import Collection, Mapping
from datetime import date
from pathlib import Path
from typing import Any, cast

from lpa.domain import (
    Coalition,
    ElectionStatus,
    Outlet,
    StateElectionSignal,
    SwingModelConfig,
)
from lpa.mp_profile import (
    Contact,
    Division,
    GE15Result,
    MPProfile,
    unexplained_fields,
)
from lpa.poll_calibration import LeaderRating, PollCalibration
from lpa.postcode_index import SeatMatch


def data_file(name: str) -> Path:
    """Locate a file from `data/`, installed or in a checkout.

    An installed wheel carries these alongside the package; a checkout keeps
    them at the repo root, where they are easier to find and edit. The
    packaged copy wins so an install never silently reads a stale checkout.
    """
    packaged = Path(__file__).resolve().parent / "data" / name
    if packaged.exists():
        return packaged
    return Path(__file__).resolve().parents[2] / "data" / name


DEFAULT_CONFIG_PATH = data_file("coalitions.json")


def load_coalition_config(path: Path | None = None) -> Mapping[str, Any]:
    return cast(Mapping[str, Any], json.loads((path or DEFAULT_CONFIG_PATH).read_text()))


def party_to_coalition(config: Mapping[str, Any]) -> Mapping[str, Coalition]:
    return cast(Mapping[str, Coalition], config["party_to_coalition"])


def coalition_aliases(config: Mapping[str, Any]) -> Mapping[Coalition, list[str]]:
    """How each Coalition is named in coverage, for the Sentiment Scorer."""
    return cast(Mapping[Coalition, list[str]], config["coalition_aliases"])


def coalition_names(config: Mapping[str, Any]) -> Mapping[Coalition, str]:
    """How each Coalition is written out in full, for the public page.

    Absences are expected rather than exceptional: the Baseline gives a minor
    party that is in no bloc its own bracketed code as its Coalition, so the
    map cannot be complete and a caller must be ready to fall back to the
    code. `.get(code, code)` is the intended reading.
    """
    return cast(Mapping[Coalition, str], config.get("coalition_names", {}))


def swing_model_config(config: Mapping[str, Any], **overrides: Any) -> SwingModelConfig:
    """Build the Swing Model's config from the Coalition configuration file."""
    settings: dict[str, Any] = {
        "government_coalitions": frozenset(config["government_coalitions"]),
        "majority_threshold": config["majority_threshold"],
    }
    settings.update(overrides)
    return SwingModelConfig(**settings)


DEFAULT_OUTLETS_PATH = data_file("outlets.json")


def load_outlets(path: Path | None = None) -> list[Outlet]:
    """The outlets the Scraper reads, from `data/outlets.json`."""
    config = json.loads((path or DEFAULT_OUTLETS_PATH).read_text())
    return [Outlet(name=o["name"], feed_url=o["feed_url"]) for o in config["outlets"]]


DEFAULT_POLL_CALIBRATION_PATH = data_file("poll_calibration.json")


def load_transcribed_polls(
    path: Path | None = None,
    known_coalitions: Collection[Coalition] | None = None,
) -> list[PollCalibration]:
    """Transcribed Merdeka Center reports, from `data/poll_calibration.json`.

    Named for the transcription rather than for the record type, so it does
    not read the same as `storage.load_poll_calibrations` — the two return the
    same records from opposite ends of ingestion, and `main` calls both.

    `known_coalitions` — normally the Coalitions `coalitions.json` names — is
    checked rather than used: a report attributes a leader to a Coalition, and
    a typo there would otherwise invent a Coalition that scores alongside the
    real ones on the dashboard and is never noticed. Nothing about a stored
    report is derived from current configuration; a leader's Coalition is a
    historical fact about the fieldwork window (ADR 0004).
    """
    config = json.loads((path or DEFAULT_POLL_CALIBRATION_PATH).read_text())
    reports = [
        PollCalibration(
            publisher=entry["publisher"],
            title=entry["title"],
            report_url=entry["report_url"],
            published_on=date.fromisoformat(entry["published_on"]),
            fieldwork_start=date.fromisoformat(entry["fieldwork_start"]),
            fieldwork_end=date.fromisoformat(entry["fieldwork_end"]),
            sample_size=entry["sample_size"],
            margin_of_error=entry.get("margin_of_error"),
            leader_ratings=tuple(
                LeaderRating.from_mapping(rating) for rating in entry["leader_ratings"]
            ),
        )
        for entry in config["reports"]
    ]

    if known_coalitions is not None:
        for report in reports:
            for rating in report.leader_ratings:
                if rating.coalition is not None and (rating.coalition not in known_coalitions):
                    raise ValueError(
                        f"{report.title!r} attributes {rating.leader!r} to "
                        f"Coalition {rating.coalition!r}, which is not one of "
                        f"{sorted(known_coalitions)}"
                    )
    for report in reports:
        if report.fieldwork_end < report.fieldwork_start:
            raise ValueError(
                f"{report.title!r} ends its fieldwork on "
                f"{report.fieldwork_end}, before it starts on "
                f"{report.fieldwork_start}"
            )
    return reports


DEFAULT_ELECTION_STATUS_PATH = data_file("election_status.json")


def load_election_status(path: Path | None = None) -> ElectionStatus:
    """Whether GE16 has been called, from `data/election_status.json`.

    The date fields are checked against each other rather than trusted.
    This file is edited by hand at exactly one moment — the day the Dewan
    Rakyat is dissolved, probably in a hurry — and it is the only input to a
    statement the Dashboard makes in its own voice near the headline. A
    polling date with no dissolution behind it would have the page announce
    an election that constitutionally cannot have been called yet.
    """
    config = json.loads((path or DEFAULT_ELECTION_STATUS_PATH).read_text())
    dissolved_on = _optional_date(config["dissolved_on"])
    nomination_date = _optional_date(config["nomination_date"])
    polling_date = _optional_date(config["polling_date"])

    if polling_date is not None and dissolved_on is None:
        raise ValueError(
            f"election status gives a polling date of {polling_date} but no "
            "dissolution date. Polling is announced after the Dewan Rakyat is "
            "dissolved, so set dissolved_on too."
        )
    if dissolved_on is not None and polling_date is not None and (polling_date < dissolved_on):
        raise ValueError(
            f"election status polls on {polling_date}, before the dissolution on {dissolved_on}."
        )
    if nomination_date is not None and dissolved_on is None:
        raise ValueError(
            f"election status gives a nomination date of {nomination_date} but no "
            "dissolution date. Nomination is gazetted after the Dewan Rakyat is "
            "dissolved, so set dissolved_on too."
        )
    if (
        dissolved_on is not None
        and nomination_date is not None
        and (nomination_date < dissolved_on)
    ):
        raise ValueError(
            f"election status nominates on {nomination_date}, before the dissolution "
            f"on {dissolved_on}."
        )
    if (
        nomination_date is not None
        and polling_date is not None
        and (polling_date < nomination_date)
    ):
        raise ValueError(
            f"election status polls on {polling_date}, before nomination on {nomination_date}."
        )

    return ElectionStatus(
        constitutional_deadline=date.fromisoformat(config["constitutional_deadline"]),
        source=config["source"],
        dissolved_on=dissolved_on,
        nomination_date=nomination_date,
        polling_date=polling_date,
    )


def _optional_date(raw: str | None) -> date | None:
    """A date field that may be `null`, and only `null`.

    Distrusts the file like the checks above it: an empty string reaches
    `fromisoformat` and raises, rather than passing as "no date" and having
    the Dashboard report an election nobody has called.
    """
    return date.fromisoformat(raw) if raw is not None else None


DEFAULT_STATE_ELECTIONS_PATH = data_file("state_elections.json")


def load_state_election_signals(path: Path | None = None) -> list[StateElectionSignal]:
    """State elections held since GE15, from `data/state_elections.json`."""
    config = json.loads((path or DEFAULT_STATE_ELECTIONS_PATH).read_text())
    return [
        StateElectionSignal(
            state=entry["state"],
            held_on=date.fromisoformat(entry["held_on"]),
            vote_share=entry["vote_share"],
        )
        for entry in config["state_elections"]
    ]


DEFAULT_POSTCODE_SEAT_INDEX_PATH = data_file("postcode_seat_index.json")


def load_postcode_seat_index(path: Path | None = None) -> Mapping[str, tuple[SeatMatch, ...]]:
    """Postcode -> candidate Seat(s), from `data/postcode_seat_index.json`.

    A pilot slice, not all 222 Seats — see the module docstring on
    `lpa.postcode_index` and ADR 0008. Every entry names at least one Seat;
    an empty tuple for a postcode not in the returned mapping is the caller's
    job (`lpa.postcode_index.lookup_postcode` does this), not this loader's.
    """
    config = json.loads((path or DEFAULT_POSTCODE_SEAT_INDEX_PATH).read_text())
    index = {}
    for postcode, seat_codes in config["postcodes"].items():
        if not seat_codes:
            raise ValueError(f"postcode {postcode!r} lists no Seats")
        index[postcode] = tuple(SeatMatch(seat_code=code) for code in seat_codes)
    return index


DEFAULT_MP_PROFILES_PATH = data_file("mp_profiles.json")


def load_mp_profiles(path: Path | None = None) -> Mapping[str, MPProfile]:
    """Seat code -> its sitting Member's profile, from `data/mp_profiles.json`.

    A pilot slice, not all 222 Seats — see `lpa.mp_profile` and ADR 0009.

    Distrusts the file the way `load_election_status` does, and for a sharper
    reason: every figure in a profile is attached to a named person, so the
    cost of a bad record is a real-world misattribution rather than a wrong
    chart. Two checks beyond reading the shape:

    A profile that leaves an optional field unset without saying why is
    rejected. That is the whole discipline of #78 made mechanical — the
    design mock this schema replaces shipped an invented address, phone
    number, four voting rows and two bill titles, and the way that happens
    is an unexplained blank sitting there looking fillable.

    A Division whose tallies are negative or account for more Members than
    the House has is rejected too, by `Division` itself. Note what is *not*
    checked: that they account for all 222. They often do not, for reasons
    that are real rather than erroneous — see `Division.members_accounted`.
    """
    config = json.loads((path or DEFAULT_MP_PROFILES_PATH).read_text())
    profiles = {}
    for seat_code, entry in config["profiles"].items():
        profile = MPProfile(
            seat_code=seat_code,
            name=entry["name"],
            coalition=entry["coalition"],
            term_start=date.fromisoformat(entry["term_start"]),
            ge15=_ge15_result(entry["ge15"]),
            contact=_contact(entry.get("contact", {})),
            divisions=tuple(_division(row) for row in entry.get("divisions", ())),
            bills_sponsored=tuple(entry.get("bills_sponsored", ())),
            party=entry.get("party"),
            attendance=entry.get("attendance"),
            unverified=entry.get("unverified", {}),
        )
        unexplained = unexplained_fields(profile)
        if unexplained:
            raise ValueError(
                f"{seat_code} leaves {', '.join(unexplained)} unset without an entry "
                "in 'unverified' saying why. An unexplained blank is how an invented "
                "value gets in — record what was checked and what it did not have."
            )
        profiles[seat_code] = profile
    return profiles


def _ge15_result(values: Mapping[str, Any]) -> GE15Result:
    return GE15Result(
        votes=values["votes"],
        majority=values["majority"],
        vote_share=values["vote_share"],
        valid_votes=values["valid_votes"],
        runner_up_votes=values["runner_up_votes"],
        runner_up_coalition=values["runner_up_coalition"],
        electors=values["electors"],
        turnout=values["turnout"],
        source_url=values["source_url"],
    )


def _contact(values: Mapping[str, Any]) -> Contact:
    return Contact(
        address=values.get("address"),
        phone=values.get("phone"),
        email=values.get("email"),
        opening_hours=values.get("opening_hours"),
        profile_url=values.get("profile_url"),
    )


def _division(values: Mapping[str, Any]) -> Division:
    return Division(
        sitting_date=date.fromisoformat(values["sitting_date"]),
        subject=values["subject"],
        vote=values["vote"],
        ayes=values["ayes"],
        noes=values["noes"],
        abstentions=values["abstentions"],
        absent=values["absent"],
        outcome=values["outcome"],
        hansard_url=values["hansard_url"],
    )
