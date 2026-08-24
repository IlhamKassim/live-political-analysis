"""MP Profiles, and the shipped pilot slice (issue #78).

Split the way `test_postcode_index.py` is: the loader against synthetic
fixtures, so a malformed file fails loudly, and the shipped record against
what its real sources say.

The shipped-record tests are deliberately structural rather than a copy of
the expected figures. Asserting "majority == 69701" would pass just as
happily if the number had been invented, which is the one failure #78 exists
to prevent; asserting that every unset field explains itself, that no field
holds a placeholder, and that every figure reconciles with the others in its
own record is a check an invented value can actually fail.
"""

import json
import re
from datetime import date

import pytest
from build_mp_profiles import MAX_UNACCOUNTED

from lpa.config import load_mp_profiles
from lpa.mp_profile import (
    TOTAL_SEATS,
    VOTES,
    Contact,
    Division,
    GE15Result,
    MPProfile,
    missing_fields,
    unexplained_fields,
)

GE15 = {
    "votes": 141568,
    "majority": 69701,
    "vote_share": 0.5795055896451363,
    "valid_votes": 244291,
    "runner_up_votes": 71867,
    "runner_up_coalition": "PN",
    "electors": 303430,
    "turnout": 0.8133506904393105,
    "source_url": "https://raw.githubusercontent.com/Thevesh/analysis-election-msia/main/data/results_parlimen_ge15.csv",
}

DIVISION = {
    "sitting_date": "2026-03-02",
    "subject": "RANG UNDANG-UNDANG PERLEMBAGAAN (PINDAAN) 2026 Bacaan Kali Yang Kedua",
    "vote": "aye",
    "ayes": 146,
    "noes": 0,
    "abstentions": 44,
    "absent": 32,
    "outcome": "Kurang daripada dua pertiga majoriti; tidak diluluskan",
    "hansard_url": "https://hansard.parlimen.gov.my/hansard/dewan-rakyat/2026-03-02",
}

# Everything a profile must carry, with nothing optional left out — so a test
# below can drop exactly one field and know that is the only thing wrong.
COMPLETE = {
    "name": "YB Tuan Test Member",
    "coalition": "PH",
    "term_start": "2022-12-19",
    "ge15": GE15,
    "contact": {
        "address": "1 Jalan Test, 43650 Bandar Baru Bangi, Selangor",
        "phone": "03-87401108",
        "email": "member@example.test",
        "opening_hours": "Isnin-Jumaat, 9 pagi-5 petang",
        "profile_url": "https://www.parlimen.gov.my/profile-ahli.html?uweb=dr&id=1",
    },
    "divisions": [DIVISION],
    "bills_sponsored": ["Rang Undang-Undang Ujian 2026"],
    "party": "DAP",
    "attendance": 0.86,
    "unverified": {},
}


def write_profiles(tmp_path, profiles):
    path = tmp_path / "mp_profiles.json"
    path.write_text(json.dumps({"profiles": profiles}))
    return path


def test_the_loader_reads_a_complete_profile(tmp_path):
    profiles = load_mp_profiles(write_profiles(tmp_path, {"P.102": COMPLETE}))

    profile = profiles["P.102"]
    assert profile.seat_code == "P.102"
    assert profile.term_start == date(2022, 12, 19)
    assert profile.divisions[0].sitting_date == date(2026, 3, 2)
    assert missing_fields(profile) == ()


@pytest.mark.parametrize(
    ("drop", "expected"),
    [
        ("party", "party"),
        ("attendance", "attendance"),
        ("bills_sponsored", "bills_sponsored"),
    ],
)
def test_the_loader_rejects_a_field_left_unset_with_no_reason(tmp_path, drop, expected):
    entry = {**COMPLETE, drop: None if drop != "bills_sponsored" else []}

    with pytest.raises(ValueError, match=expected):
        load_mp_profiles(write_profiles(tmp_path, {"P.102": entry}))


def test_the_loader_rejects_a_contact_field_left_unset_with_no_reason(tmp_path):
    entry = {**COMPLETE, "contact": {**COMPLETE["contact"], "phone": None}}

    with pytest.raises(ValueError, match="contact.phone"):
        load_mp_profiles(write_profiles(tmp_path, {"P.102": entry}))


def test_the_loader_accepts_an_unset_field_that_says_why(tmp_path):
    entry = {
        **COMPLETE,
        "attendance": None,
        "unverified": {"attendance": "Parliament publishes no per-Member attendance figure."},
    }

    profile = load_mp_profiles(write_profiles(tmp_path, {"P.102": entry}))["P.102"]

    assert profile.attendance is None
    assert missing_fields(profile) == ("attendance",)
    assert unexplained_fields(profile) == ()


def test_an_empty_voting_record_needs_no_excuse(tmp_path):
    # Divisions are rare, and a Member who has sat through none is making no
    # claim about themselves — unlike an empty `bills_sponsored`, which does.
    entry = {**COMPLETE, "divisions": []}

    assert load_mp_profiles(write_profiles(tmp_path, {"P.102": entry}))["P.102"].divisions == ()


@pytest.mark.parametrize("bad", ["yes", "AYE", "", "for", "tidak"])
def test_a_division_rejects_a_position_hansard_does_not_record(bad):
    with pytest.raises(ValueError):
        Division(**{**DIVISION, "sitting_date": date(2026, 3, 2), "vote": bad})


def test_a_division_rejects_more_members_than_the_house_has():
    with pytest.raises(ValueError, match="more than"):
        Division(**{**DIVISION, "sitting_date": date(2026, 3, 2), "absent": 200})


def test_a_division_rejects_a_negative_tally():
    with pytest.raises(ValueError, match="negative"):
        Division(**{**DIVISION, "sitting_date": date(2026, 3, 2), "noes": -1})


def test_a_division_may_account_for_fewer_members_than_the_house_has():
    # A Seat can be vacant, and a Member under suspension is barred from
    # voting and named in none of Hansard's four lists — so 221 is a real
    # result, not a mis-transcribed one.
    division = Division(
        **{
            **DIVISION,
            "sitting_date": date(2024, 10, 17),
            "ayes": 206,
            "noes": 1,
            "abstentions": 0,
            "absent": 14,
        }
    )

    assert division.members_accounted == TOTAL_SEATS - 1


def test_unexplained_fields_names_every_silent_blank():
    profile = MPProfile(
        seat_code="P.102",
        name="YB Tuan Test Member",
        coalition="PH",
        term_start=date(2022, 12, 19),
        ge15=GE15Result(**GE15),
        contact=Contact(),
        unverified={"party": "Parliament publishes the Coalition, not the component party."},
    )

    assert "party" not in unexplained_fields(profile)
    assert set(unexplained_fields(profile)) == set(missing_fields(profile)) - {"party"}


SHIPPED_PROFILES = load_mp_profiles()

# Anything that reads like a value someone meant to replace. The design mock
# this data replaces used "03-8925 xxxx"; the rest are the usual suspects.
PLACEHOLDER = re.compile(
    r"\b(tbd|tba|todo|fixme|lorem|ipsum|xxxx?|placeholder|example|sample|dummy|n/?a)\b",
    re.IGNORECASE,
)


def test_every_shipped_profile_explains_every_field_it_leaves_unset():
    for seat_code, profile in SHIPPED_PROFILES.items():
        assert unexplained_fields(profile) == (), seat_code


def test_no_shipped_field_holds_a_placeholder_rather_than_a_value():
    for seat_code, profile in SHIPPED_PROFILES.items():
        strings = [
            profile.name,
            profile.coalition,
            profile.party,
            profile.contact.address,
            profile.contact.phone,
            profile.contact.email,
            profile.contact.opening_hours,
            profile.contact.profile_url,
            *profile.bills_sponsored,
            *(d.subject for d in profile.divisions),
            *(d.outcome for d in profile.divisions),
        ]
        for value in strings:
            if value is None:
                continue
            assert value.strip(), seat_code
            assert not PLACEHOLDER.search(value), f"{seat_code}: {value!r}"


def test_every_shipped_reason_says_what_was_checked():
    # A reason that is a word or two is a shrug, and a shrug is how a blank
    # gets filled in later by someone who assumes nobody looked.
    for seat_code, profile in SHIPPED_PROFILES.items():
        for field, reason in profile.unverified.items():
            assert len(reason.split()) >= 10, f"{seat_code}.{field}"


def test_every_shipped_ge15_result_reconciles_with_itself():
    for seat_code, profile in SHIPPED_PROFILES.items():
        ge15 = profile.ge15
        assert 0 < ge15.votes <= ge15.valid_votes, seat_code
        assert 0 < ge15.runner_up_votes < ge15.votes, seat_code
        # The one figure a reader is most likely to quote, checked against
        # the two it is derived from rather than taken on trust.
        assert ge15.majority == ge15.votes - ge15.runner_up_votes, seat_code
        assert ge15.votes + ge15.runner_up_votes <= ge15.valid_votes, seat_code
        assert ge15.runner_up_coalition.strip(), seat_code
        assert ge15.valid_votes <= ge15.electors, seat_code
        assert 0 < ge15.turnout <= 1, seat_code
        assert ge15.vote_share == pytest.approx(ge15.votes / ge15.valid_votes), seat_code
        # Every ballot counted was issued to an elector who turned out.
        assert ge15.valid_votes <= ge15.electors * ge15.turnout, seat_code


def test_every_shipped_division_is_a_recorded_position_with_a_source():
    for seat_code, profile in SHIPPED_PROFILES.items():
        for division in profile.divisions:
            assert division.vote in VOTES, seat_code
            # Close to the whole House, and never more than it — see
            # `Division.members_accounted` for why "exactly" is wrong.
            assert TOTAL_SEATS - MAX_UNACCOUNTED <= division.members_accounted <= TOTAL_SEATS, (
                seat_code
            )
            assert division.hansard_url.endswith(division.sitting_date.isoformat()), seat_code
            assert division.hansard_url.startswith("https://hansard.parlimen.gov.my/"), seat_code
            assert division.sitting_date >= profile.term_start, seat_code


def test_the_shipped_voting_record_runs_newest_first():
    for seat_code, profile in SHIPPED_PROFILES.items():
        dates = [d.sitting_date for d in profile.divisions]
        assert dates == sorted(dates, reverse=True), seat_code


def test_the_shipped_pilot_covers_the_seat_its_postcode_index_pilots():
    # #76 and #78 pilot the same Seat on purpose: the lookup result page
    # (#79) needs both halves for the same P.102 to render at all.
    from lpa.config import load_postcode_seat_index

    indexed = {
        match.seat_code for matches in load_postcode_seat_index().values() for match in matches
    }

    assert set(SHIPPED_PROFILES) <= indexed
