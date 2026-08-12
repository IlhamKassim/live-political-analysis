"""Poll Calibration: Merdeka Center's published surveys, per Coalition.

CONTEXT.md defines Poll Calibration as the periodic, survey-based component of
Sentiment, ingested "whenever a new report drops to sanity-check News
Sentiment against real survey data". Merdeka Center publishes PDFs on no
schedule and offers no API, so ingestion is a person transcribing a report
into `data/poll_calibration.json` and running this module — the semi-manual
process issue #10 asks for, written down in `docs/poll-calibration.md`.

What Merdeka publishes is approval ratings for named leaders, not a Coalition
score. Turning the first into the second is this module's whole job, and it is
an interpretation rather than a fact — ADR 0004 records why leader approval is
the signal used and what it does and does not license. Two rules follow from
it and are enforced here:

A leader counts towards the Coalition their party belonged to *while the
survey was in the field*, which the transcription records per report. A leader
who belonged to none is carried through as unattributed and named, never
silently dropped and never guessed at.

Coalitions are averaged unweighted across their leaders, exactly as
`aggregate_sentiment` averages a Coalition's Articles. Both are means over
whatever evidence named the Coalition, and both travel with the count behind
them so a Coalition scored from one leader cannot pass for one scored from
three.

The transform is pure — reports in, scores out. Reading the file and writing
to Storage are separate steps, as in the Baseline Loader.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date

from lpa.domain import Coalition


@dataclass(frozen=True)
class LeaderRating:
    """One leader's published approval rating, exactly as the report gives it.

    `satisfied` and `dissatisfied` are percentages of all respondents and are
    not expected to sum to 100: reports also carry neutral and unsure/refused
    answers, and dropping them would silently rescale a published number.
    """

    leader: str
    satisfied: float
    dissatisfied: float
    party: str | None = None
    """The leader's party as at the fieldwork window, where the report or the
    public record names one."""
    coalition: Coalition | None = None
    """The Coalition that party sat in as at the fieldwork window.

    `None` means the leader belonged to no Coalition while the survey ran, and
    that their rating is reported but attributed to nobody.
    """
    note: str | None = None
    """Why the attribution above is what it is, where it took a judgement."""

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> LeaderRating:
        """Build a rating from a JSON object, from the data file or Storage.

        Paired with `as_mapping` and kept on the type rather than written out
        at each end, so a new field is added in one place instead of three —
        and so a field the transcription carries can never be silently
        dropped on its way through Storage.
        """
        return cls(
            leader=values["leader"],  # type: ignore[arg-type]
            satisfied=values["satisfied"],  # type: ignore[arg-type]
            dissatisfied=values["dissatisfied"],  # type: ignore[arg-type]
            party=values.get("party"),  # type: ignore[arg-type]
            coalition=values.get("coalition"),  # type: ignore[arg-type]
            note=values.get("note"),  # type: ignore[arg-type]
        )

    def as_mapping(self) -> dict[str, object]:
        """The rating as a JSON object, for the Storage column."""
        return {
            "leader": self.leader,
            "satisfied": self.satisfied,
            "dissatisfied": self.dissatisfied,
            "party": self.party,
            "coalition": self.coalition,
            "note": self.note,
        }

    @property
    def net_approval(self) -> float:
        """Approval minus disapproval, as a fraction from -1.0 to +1.0.

        Net rather than raw approval because News Sentiment is signed and
        centred on zero, and a bare approval percentage is neither: 30%
        approval is a bad number, but 0.30 on a -1..+1 scale reads as mild
        warmth. Net approval is the published pair reduced to the same shape
        the Sentiment trend already plots.
        """
        return (self.satisfied - self.dissatisfied) / 100.0


@dataclass(frozen=True)
class PollCalibration:
    """One published survey report, with the provenance to go and check it.

    The provenance is not decoration. A Poll Calibration point is hand-copied
    from a PDF, so the reader of a chart needs to be able to find the report it
    came from and see the sample behind it.
    """

    publisher: str
    title: str
    report_url: str
    published_on: date
    fieldwork_start: date
    fieldwork_end: date
    """The last day of fieldwork — the day the poll is plotted at.

    The earliest date at which the finding was complete, and a date the report
    actually states. A fieldwork midpoint would be a better estimate of when
    the opinion was held, but it is a date the publisher never printed, and
    an invented date is worse than a coarse one.
    """
    sample_size: int
    margin_of_error: float | None = None
    """The published margin of error in percentage points, where given."""
    leader_ratings: Sequence[LeaderRating] = field(default_factory=tuple)


@dataclass(frozen=True)
class CalibrationScores:
    """A report reduced to one net approval per Coalition, with its evidence.

    Shaped like `AggregatedSentiment` on purpose: the dashboard plots the two
    against each other, and a score that arrives without the count behind it
    invites a Coalition read off one leader being trusted like one read off
    three.
    """

    scores: Mapping[Coalition, float] = field(default_factory=dict)
    leader_counts: Mapping[Coalition, int] = field(default_factory=dict)
    unattributed: Sequence[LeaderRating] = field(default_factory=tuple)
    """Leaders the report rated who belonged to no Coalition at fieldwork.

    Carried whole rather than as names, because the reason a leader is here is
    always particular: the dashboard prints their published percentages and
    the note explaining the attribution, and a list of names would send it
    back to the report to find them again.
    """


def coalition_net_approval(ratings: Iterable[LeaderRating]) -> CalibrationScores:
    """Average each Coalition's leaders' net approval into one score.

    A Coalition the report rated no leader of is absent from the result rather
    than scored zero — the report is silent about it, and silence is not a
    neutral rating.
    """
    totals: dict[Coalition, float] = {}
    counts: dict[Coalition, int] = {}
    unattributed: list[LeaderRating] = []

    for rating in ratings:
        if rating.coalition is None:
            unattributed.append(rating)
            continue
        totals[rating.coalition] = totals.get(rating.coalition, 0.0) + rating.net_approval
        counts[rating.coalition] = counts.get(rating.coalition, 0) + 1

    return CalibrationScores(
        scores={c: totals[c] / counts[c] for c in totals},
        leader_counts=counts,
        unattributed=tuple(unattributed),
    )


def main() -> None:
    """Ingest every transcribed report into Storage as a Poll Calibration point.

    Run when a new report has been transcribed, not on a schedule: reports
    appear every few months and this writes only what the data file holds.
    Ingesting the same report again corrects it rather than duplicating it,
    the same rule the daily snapshot follows.
    """
    # Imported here rather than at module level, and not only for the reason
    # the other `main`s do it: `lpa.config` imports the record types above, so
    # a top-level import of it here would be a cycle. The types have to sit on
    # this side of that edge — they are the domain of Poll Calibration, and
    # `config` is the module that reads the file into them.
    from lpa.config import load_coalition_config, load_transcribed_polls
    from lpa.storage import connect, save_poll_calibrations

    config = load_coalition_config()
    reports = load_transcribed_polls(known_coalitions=set(config["coalition_aliases"]))
    if not reports:
        raise SystemExit(
            "No reports in data/poll_calibration.json. See "
            "docs/poll-calibration.md for how to transcribe one."
        )

    written = save_poll_calibrations(connect(), reports)
    print(f"Ingested {written} Poll Calibration report(s).")
    for report in reports:
        derived = coalition_net_approval(report.leader_ratings)
        print(
            f"\n{report.publisher} — {report.title}\n"
            f"  fieldwork {report.fieldwork_start} to {report.fieldwork_end}, "
            f"n={report.sample_size}"
        )
        for coalition, score in sorted(derived.scores.items(), key=lambda kv: -kv[1]):
            leaders = derived.leader_counts[coalition]
            print(f"  {coalition:5s} {score:+.3f}  ({leaders} leader(s) rated)")
        if derived.unattributed:
            names = ", ".join(rating.leader for rating in derived.unattributed)
            print(f"  unattributed: {names}")


if __name__ == "__main__":
    main()
