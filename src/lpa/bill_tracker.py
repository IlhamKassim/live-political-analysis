"""Bill Tracker: what Parliament is doing with a Bill, and what it says about itself (issue #80).

The homepage's bill tracker (#74) is built against a static fixture — this
module and `data/bills.json` are the real data behind it. The same risk
profile as `lpa.mp_profile`: a Bill's stage or its division result is a
factual, checkable claim about Parliament, not a cosmetic number.

## Stage is Parliament's own word, not an invented category

`Bill.stage` carries the exact status Parliament's own Bills register uses —
*Lulus* (passed), *Dirujuk ke JKPK* (referred to a Special Select
Committee), *Bacaan Kali Pertama* (first reading only) and so on — rather
than a translated or invented English taxonomy. Translating it is a
presentation concern, the same call ADR 0009 made for a Division's subject:
solve it at the page layer with the original kept alongside, not by editing
the record.

## The plain-language summary is Parliament's own text, not this pipeline's paraphrase

Every Bill's own PDF carries a "HURAIAN" (Explanation) section opening with
one or two sentences stating what the Bill does, before the clause-by-clause
detail. `Bill.summary` is a verbatim excerpt of that opening — not a
paraphrase this pipeline wrote. Writing an original plain-language gloss
would be an editorial judgement call on a bill's own text (this repo's
`docs/agents/model-effort.md` trigger 2) and risks a paraphrase that is
wrong in a way Parliament's own words cannot be; quoting instead makes the
summary exactly as authoritative as its source. See ADR 0010.

## A Division result is the exception, not the rule

Most Bills pass on a voice vote that records no tally at all — of the 15th
Parliament's roughly 30 Bills a year, `lpa.mp_profile`'s ADR 0009 found only
ten recorded Divisions across three and a half years. `Bill.division` is
`None` for the ordinary case, and that is not a gap: `unverified["division"]`
says why for every Bill that has none, the same discipline `MPProfile`
applies to attendance. Where a Division did happen, its tally is the same
Chair-declared figures already shipped in `data/mp_profiles.json` for
whichever Seat's profile that Division also appears in — `Bill.division` is
derived from there at build time, not re-transcribed, so the same fact is
never typed twice where it could drift.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date

from lpa.mp_profile import TOTAL_SEATS


@dataclass(frozen=True)
class DivisionResult:
    """The chamber's recorded vote on a Bill, where one was taken.

    Aggregate only — no per-Member position, unlike `lpa.mp_profile.Division`,
    which is one Member's own record of the same event. The two describe the
    same Division from different angles and must not disagree; see the
    module docstring for how that is kept true by derivation rather than
    duplication.
    """

    sitting_date: date
    ayes: int
    noes: int
    abstentions: int
    absent: int
    outcome: str
    """What the Chair declared the vote to have decided."""
    hansard_url: str

    def __post_init__(self) -> None:
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
        return self.ayes + self.noes + self.abstentions + self.absent


@dataclass(frozen=True)
class Bill:
    """One Bill tracked on the homepage's bill tracker.

    Identified by `code` alone — the Dewan Rakyat's own reference (e.g.
    "D.R.28/2025"), never a separate id this pipeline invented.
    """

    code: str
    """Parliament's own reference for the Bill, e.g. "D.R.28/2025"."""
    title: str
    """The Bill's official title, as the Bills register gives it."""
    year: int
    stage: str
    """Parliament's own status label for the Bill — see the module docstring."""
    stage_date: date
    """When the Bill last reached `stage`."""
    summary: str
    """A verbatim excerpt of the Bill's own "HURAIAN" explanatory statement."""
    summary_source_url: str
    """The Bill's PDF, with a page anchor to the excerpted passage."""
    division: DivisionResult | None = None
    unverified: Mapping[str, str] = field(default_factory=dict)
    """Field name -> why it has no value, for every optional field left unset.

    Only `division` is optional today — see `OPTIONAL_FIELDS`. Checked by
    `lpa.config.load_bills` the same way `lpa.mp_profile` checks a profile:
    an unset field with no reason is rejected rather than shipped.
    """


OPTIONAL_FIELDS = ("division",)


def missing_fields(bill: Bill) -> tuple[str, ...]:
    """The optional fields this Bill leaves unset, in `OPTIONAL_FIELDS` order."""
    absent = {"division": bill.division is None}
    return tuple(name for name in OPTIONAL_FIELDS if absent[name])


def unexplained_fields(bill: Bill) -> tuple[str, ...]:
    """Fields left unset with no reason given — the failure this module exists to catch."""
    return tuple(name for name in missing_fields(bill) if name not in bill.unverified)
