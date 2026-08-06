"""Reading the Coalition configuration that lives in `data/coalitions.json`.

Government Coalition membership and the party rollup are data, not code, so a
realignment is a config edit (issue #1, story 20).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Collection, Mapping

from lpa.domain import Coalition, Outlet, StateElectionSignal, SwingModelConfig
from lpa.poll_calibration import LeaderRating, PollCalibration

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
    return json.loads((path or DEFAULT_CONFIG_PATH).read_text())


def party_to_coalition(config: Mapping[str, Any]) -> Mapping[str, Coalition]:
    return config["party_to_coalition"]


def coalition_aliases(config: Mapping[str, Any]) -> Mapping[Coalition, list[str]]:
    """How each Coalition is named in coverage, for the Sentiment Scorer."""
    return config["coalition_aliases"]


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
                LeaderRating.from_mapping(rating)
                for rating in entry["leader_ratings"]
            ),
        )
        for entry in config["reports"]
    ]

    if known_coalitions is not None:
        for report in reports:
            for rating in report.leader_ratings:
                if rating.coalition is not None and (
                    rating.coalition not in known_coalitions
                ):
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
