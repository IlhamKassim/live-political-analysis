"""MP Profile: who represents a Seat, and what the record actually says (issue #78).

The payoff for PolitikKu's constituency lookup, and the part of it where being
wrong costs the most: every figure here is attached to a named, identifiable
person, so a misattributed vote or a wrong service-centre number is a
different class of mistake from a wrong number on an aggregate chart.

## Absent is a value, and it has to say why

Most of what a profile page wants to show, the Malaysian Parliament does not
publish. Rather than let that surface as a plausible-looking blank, every
optional field that is unset must be named in `MPProfile.unverified` with the
reason — and `lpa.config.load_mp_profiles` refuses to load a profile that
leaves one unexplained. The rule this enforces is the one the ticket exists
for: a partial, honest profile is correct; a complete one with invented
values is not. See ADR 0009 for what was checked and what was found missing.

## A Division is rarer than a page design assumes

A Division (*belah bahagian*) is a counted vote under Standing Order 46(4),
and it is not how most Malaysian legislation passes — the ordinary case is a
voice vote that records no individual position at all. The 15th Parliament
held ten across three and a half years. So `divisions` is the MP's
*complete* recorded voting record for the term, not a recent slice, and a
short list means the Dewan Rakyat rarely divides, never that the ingestion
missed something.

What makes the record usable at all is that Hansard prints the four name
lists in full (*Ahli-Ahli Yang Bersetuju / Tidak Bersetuju / Tidak Mengundi /
Tidak Hadir*), so a Member's position is a matter of record rather than
inference — see `scripts/build_mp_profiles.py` for how they are read.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date

from lpa.domain import Coalition

AYE = "aye"
NO = "no"
ABSTAIN = "abstain"
ABSENT = "absent"

VOTES = (AYE, NO, ABSTAIN, ABSENT)
"""How a Member is recorded in a Division, matching Hansard's four lists.

`ABSENT` is a recorded position rather than missing data: Hansard names every
Member who did not attend the Division, and a page that showed it as unknown
would be hiding something the record actually states.
"""


TOTAL_SEATS = 222
"""Seats in the Dewan Rakyat.

A constant here rather than `coalitions.json`'s `total_seats`, which is
current configuration: a Division is a historical fact about the House as it
stood that day, and must not start failing to load because a future
delimitation changed the count.
"""


@dataclass(frozen=True)
class Division:
    """One recorded Division, and how this Member was listed in it.

    The tallies are the Chair's declared result, recorded exactly as
    announced rather than recomputed from the name lists. They are what the
    House was told, and Hansard's own lists occasionally disagree with them
    by a name or two — a transcription artefact that must not silently
    rewrite a result.
    """

    sitting_date: date
    subject: str
    """The question before the House, as Hansard's own heading gives it."""
    vote: str
    """This Member's position — one of `VOTES`."""
    ayes: int
    noes: int
    abstentions: int
    absent: int
    outcome: str
    """What the Chair declared the vote to have decided."""
    hansard_url: str
    """The sitting's Hansard, so a reader can find the lists themselves."""

    def __post_init__(self) -> None:
        if self.vote not in VOTES:
            raise ValueError(f"{self.vote!r} is not one of {VOTES}")
        if min(self.ayes, self.noes, self.abstentions, self.absent) < 0:
            raise ValueError(f"Division on {self.sitting_date} has a negative tally")
        if self.members_accounted > TOTAL_SEATS:
            raise ValueError(
                f"the Division on {self.sitting_date} accounts for "
                f"{self.members_accounted} Members, more than the {TOTAL_SEATS} Seats "
                "in the Dewan Rakyat"
            )

    @property
    def members_accounted(self) -> int:
        """Members the declared result accounts for, across all four positions.

        Usually `TOTAL_SEATS`, but legitimately short of it: a Seat can be
        vacant, and a Member serving a suspension is barred from voting and
        so is counted in no list — on 17 October 2024 the Chair said as much
        while declaring the result. A shortfall is therefore not a reason to
        reject a record, and this is deliberately a figure to read rather
        than an invariant to assert.
        """
        return self.ayes + self.noes + self.abstentions + self.absent


@dataclass(frozen=True)
class Contact:
    """How to reach the Member, exactly as Parliament publishes it.

    Every field is optional because the official record is uneven: it carries
    a correspondence address for some Members and not others, and publishes
    no opening hours for any of them. An absent field here is Parliament
    saying nothing, never this pipeline failing to look.
    """

    address: str | None = None
    """The Member's correspondence address (*alamat surat-menyurat*).

    Not necessarily a service centre, and not labelled as one by the source —
    the two are often the same place, but Parliament does not say so, and a
    page must not upgrade one into the other.
    """
    phone: str | None = None
    email: str | None = None
    """The contact address Parliament publishes, which is frequently a
    personal or staff mailbox rather than one at `parlimen.gov.my`."""
    opening_hours: str | None = None
    profile_url: str | None = None
    """The Member's page in Parliament's own directory."""


@dataclass(frozen=True)
class GE15Result:
    """The Member's win at GE15, with the Seat-level figures that scale it.

    Held here rather than on `SeatBaseline` because these are candidate-level
    facts about a person's election, where a Baseline is a Coalition-level
    input to the Swing Model. The two come from the same Election Commission
    dataset and must agree: this record's `vote_share` is the winning
    candidate's share of the valid vote, and the Baseline's share for the
    Coalition that candidate stood for is the same quantity rolled up.
    """

    votes: int
    """Votes cast for this candidate."""
    majority: int
    """The lead over the runner-up, in votes — *majoriti* on the official
    result, and the number a Malaysian reader expects to see first."""
    vote_share: float
    """`votes` as a fraction of the valid vote."""
    valid_votes: int
    runner_up_votes: int
    """Votes for the candidate who came second.

    Carried so `majority` can be checked rather than believed: it must equal
    `votes - runner_up_votes`, which makes an edited figure fail a test
    instead of quietly standing next to a named person's name.
    """
    runner_up_coalition: Coalition
    """The Coalition the runner-up stood for, so a margin can say who over.

    The ballot line's short code, the same convention `SeatBaseline` uses —
    a Malaysian ballot names a Coalition, not a component party.
    """
    electors: int
    """Registered electors at GE15, not the current roll — the denominator
    `turnout` is taken against, and it moves between elections."""
    turnout: float
    """Ballots issued as a fraction of `electors`."""
    source_url: str
    """Where these figures were read, so a reader can check them directly."""

    def __post_init__(self) -> None:
        if self.majority != self.votes - self.runner_up_votes:
            raise ValueError(
                f"majority {self.majority} does not equal votes {self.votes} minus "
                f"runner_up_votes {self.runner_up_votes} — this is exactly the check "
                "runner_up_votes exists to make possible, see its docstring"
            )
        expected_share = self.votes / self.valid_votes
        if abs(self.vote_share - expected_share) > 1e-9:
            raise ValueError(
                f"vote_share {self.vote_share} does not equal votes {self.votes} / "
                f"valid_votes {self.valid_votes} ({expected_share})"
            )
        if not 0 <= self.turnout <= 1:
            raise ValueError(f"turnout {self.turnout} is not a fraction between 0 and 1")


@dataclass(frozen=True)
class MPProfile:
    """One Seat's sitting Member, and their record this term.

    Identified by `seat_code` alone, the way `SeatCall` and `SeatMatch` are:
    `SeatBaseline` already holds the Seat's name, state, GE15 vote share and
    census profile for all 222 Seats, and a caller rendering a profile wants
    those anyway. Copying them here would make a Seat's identity two facts
    that can disagree.
    """

    seat_code: str
    """The Seat's official code, e.g. "P.102", matching its `SeatBaseline`."""
    name: str
    """The Member's name as Parliament's own directory writes it."""
    coalition: Coalition
    """The Coalition the Member sits for, as Parliament records it."""
    term_start: date
    """When the Member took their seat — for a Member returned at a general
    election, the day that Parliament first sat."""
    ge15: GE15Result
    contact: Contact
    divisions: Sequence[Division] = ()
    """Every Division of the term in which the Member was recorded, newest
    first. Complete rather than recent — see the module docstring."""
    bills_sponsored: Sequence[str] = ()
    """Bills the Member tabled, by title.

    Empty is the expected value for a backbencher and is a finding, not a
    gap: every Bill in Parliament's own register for this term was tabled by
    a Minister or Deputy Minister. `unverified` records what that check
    could not cover.
    """
    party: str | None = None
    """The Member's component party within `coalition`, where a source says so.

    Distinct from `coalition` because Parliament's directory publishes only
    the Coalition, and the Election Commission records the ballot line, which
    is also the Coalition: a component party is not in either record.
    """
    attendance: float | None = None
    """Share of the term's sitting days attended, where anyone publishes it."""
    unverified: Mapping[str, str] = field(default_factory=dict)
    """Field name -> why it has no value, for every optional field left unset.

    Checked rather than decorative: `lpa.config.load_mp_profiles` rejects a
    profile that leaves an unset field unexplained, so "we did not find one"
    can never be quietly indistinguishable from "there is nothing to find".
    """


OPTIONAL_FIELDS = (
    "party",
    "attendance",
    "contact.address",
    "contact.phone",
    "contact.email",
    "contact.opening_hours",
    "contact.profile_url",
    "bills_sponsored",
)
"""Every field a profile may leave unset, and so must explain if it does.

`bills_sponsored` is in the list even though it is a sequence: an empty one
is a claim about a named person's record, and needs the same justification as
a missing figure.
"""


def missing_fields(profile: MPProfile) -> tuple[str, ...]:
    """The optional fields this profile leaves unset, in `OPTIONAL_FIELDS` order.

    Each one must have an entry in `profile.unverified`; `unexplained_fields`
    is what checks that, and the loader is what enforces it.
    """
    absent = {
        "party": profile.party is None,
        "attendance": profile.attendance is None,
        "contact.address": profile.contact.address is None,
        "contact.phone": profile.contact.phone is None,
        "contact.email": profile.contact.email is None,
        "contact.opening_hours": profile.contact.opening_hours is None,
        "contact.profile_url": profile.contact.profile_url is None,
        "bills_sponsored": not profile.bills_sponsored,
    }
    return tuple(name for name in OPTIONAL_FIELDS if absent[name])


def unexplained_fields(profile: MPProfile) -> tuple[str, ...]:
    """Fields left unset with no reason given — the failure this module exists to catch.

    Non-empty means a profile is claiming nothing about a field without
    saying why, which is exactly how an invented value gets in later: a blank
    with no reason attached looks like something waiting to be filled.
    """
    return tuple(name for name in missing_fields(profile) if name not in profile.unverified)
