"""Whether GE16 has been called — the record, its loader, and the shipped file.

The Dashboard states this in its own voice near the headline Projection, so a
bad edit to `data/election_status.json` becomes a false claim on a public page
rather than a stack trace. The loader checks the file for that reason, and
these tests pin what it rejects.

The phrasing itself lives in `dashboard.py` and is verified by running the
page, per issue #1's decision that the Dashboard has no automated tests —
importing that module renders it.
"""

import json
from datetime import date

import pytest

from lpa.config import load_election_status
from lpa.domain import ElectionStatus

DEADLINE = date(2028, 2, 17)


def write_status(tmp_path, **fields):
    """A status file with the shipped shape, overridden field by field."""
    status = {
        "dissolved_on": None,
        "nomination_date": None,
        "polling_date": None,
        "constitutional_deadline": DEADLINE.isoformat(),
        "source": "https://www.parlimen.gov.my/",
    }
    status.update(fields)
    path = tmp_path / "election_status.json"
    path.write_text(json.dumps(status))
    return path


def test_an_election_is_called_by_the_dissolution_not_by_the_polling_date():
    # The Election Commission announces polling after the Dewan Rakyat is
    # dissolved, so this interval is a real state, not a half-filled record.
    called = ElectionStatus(
        constitutional_deadline=DEADLINE, source="", dissolved_on=date(2026, 10, 1)
    )

    assert called.called is True
    assert called.polling_date is None


def test_an_election_nobody_has_called_carries_neither_date():
    assert ElectionStatus(constitutional_deadline=DEADLINE, source="").called is False


def test_the_loader_reads_a_dissolution_and_its_polling_date(tmp_path):
    status = load_election_status(
        write_status(tmp_path, dissolved_on="2026-10-01", polling_date="2026-10-25")
    )

    assert status.called is True
    assert status.dissolved_on == date(2026, 10, 1)
    assert status.polling_date == date(2026, 10, 25)
    assert status.constitutional_deadline == DEADLINE


def test_a_polling_date_with_no_dissolution_behind_it_is_rejected(tmp_path):
    # The likeliest bad edit: filling in the polling date announced in the
    # news and forgetting the dissolution. It would have the page announce an
    # election that constitutionally cannot have been called.
    with pytest.raises(ValueError, match="no dissolution date"):
        load_election_status(write_status(tmp_path, polling_date="2026-10-25"))


def test_polling_before_the_dissolution_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="before the dissolution"):
        load_election_status(
            write_status(tmp_path, dissolved_on="2026-10-01", polling_date="2026-09-25")
        )


def test_the_loader_reads_a_nomination_date_gazetted_alongside_polling(tmp_path):
    # #40, code review 20 Aug 2026: nomination day and polling day are
    # gazetted together, not on separate schedules — added for the
    # aggregate Telegram post's timeline, which needs a real third stop.
    status = load_election_status(
        write_status(
            tmp_path,
            dissolved_on="2026-10-01",
            nomination_date="2026-10-20",
            polling_date="2026-11-08",
        )
    )

    assert status.nomination_date == date(2026, 10, 20)


def test_a_nomination_date_with_no_dissolution_behind_it_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="no dissolution date"):
        load_election_status(write_status(tmp_path, nomination_date="2026-10-20"))


def test_nomination_before_the_dissolution_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="before the dissolution"):
        load_election_status(
            write_status(tmp_path, dissolved_on="2026-10-01", nomination_date="2026-09-25")
        )


def test_polling_before_nomination_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="before nomination"):
        load_election_status(
            write_status(
                tmp_path,
                dissolved_on="2026-10-01",
                nomination_date="2026-10-20",
                polling_date="2026-10-15",
            )
        )


def test_the_shipped_file_says_ge16_has_not_been_called():
    # True as of August 2026 and the reason this issue exists. If a
    # dissolution has happened, this test is the reminder that the data file
    # is the thing to update — not this assertion.
    status = load_election_status()

    assert status.called is False
    assert status.nomination_date is None
    assert status.polling_date is None
    assert status.constitutional_deadline == DEADLINE
    assert status.source
