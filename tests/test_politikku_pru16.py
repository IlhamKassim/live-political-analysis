"""The GE16 page: three Election Status states, both languages, no file reads."""

from __future__ import annotations

import re
from datetime import date

from lpa.domain import ElectionStatus
from lpa.politikku_landing import CoalitionRow
from lpa.politikku_pru16 import (
    Pru16Model,
    days_until,
    render_pru16_body,
    render_pru16_page,
)
from lpa.politikku_shell import Language

TODAY = date(2026, 9, 12)
DEADLINE = date(2028, 2, 17)
SOURCE = "https://www.parlimen.gov.my/"

NOT_CALLED = ElectionStatus(constitutional_deadline=DEADLINE, source=SOURCE)
CALLED = ElectionStatus(
    constitutional_deadline=DEADLINE, source=SOURCE, dissolved_on=date(2026, 10, 1)
)
POLLING = ElectionStatus(
    constitutional_deadline=DEADLINE,
    source=SOURCE,
    dissolved_on=date(2026, 10, 1),
    nomination_date=date(2026, 10, 20),
    polling_date=date(2026, 11, 3),
)

ROWS = (
    CoalitionRow("PH", 75, "#e31b23", True),
    CoalitionRow("BN", 41, "#0b3d91", True),
    CoalitionRow("PN", 69, "#00a651", False),
)


def _model(status: ElectionStatus, coalitions: tuple[CoalitionRow, ...] = ROWS) -> Pru16Model:
    return Pru16Model(
        status=status,
        today=TODAY,
        coalitions=coalitions,
        computed_at=date(2026, 8, 23),
        majority_threshold=112,
        total_seats=222,
        sources_count=5,
    )


def _count(body: str) -> str | None:
    match = re.search(r"data-pk-count-n>(\d+)<", body)
    return match.group(1) if match else None


def test_days_until() -> None:
    assert days_until(DEADLINE, TODAY) == 523
    assert days_until(TODAY, TODAY) == 0
    assert days_until(date(2026, 9, 11), TODAY) == -1


def test_not_called_counts_to_the_deadline() -> None:
    body = render_pru16_body(_model(NOT_CALLED))
    assert "GE16 has not been called." in body
    assert _count(body) == "523"
    assert 'data-target="2028-02-17"' in body
    assert "latest possible polling date" in body
    assert "17 February 2028" in body


def test_called_without_polling_day_shows_no_number() -> None:
    body = render_pru16_body(_model(CALLED))
    assert "GE16 has been called." in body
    assert "Polling day not yet announced" in body
    assert "1 October 2026" in body
    assert "data-pk-countdown data-target" not in body
    assert _count(body) is None


def test_polling_day_set_counts_to_polling() -> None:
    body = render_pru16_body(_model(POLLING))
    assert "GE16 polling day is set." in body
    assert _count(body) == "52"
    assert 'data-target="2026-11-03"' in body
    assert "3 November 2026" in body
    assert "20 October 2026" in body


def test_polling_day_past_never_shows_a_negative_number() -> None:
    status = ElectionStatus(
        constitutional_deadline=DEADLINE,
        source=SOURCE,
        dissolved_on=date(2026, 8, 1),
        polling_date=date(2026, 9, 1),
    )
    body = render_pru16_body(_model(status))
    assert "GE16 polling has taken place." in body
    assert _count(body) == "0"


def test_dates_are_never_guessed() -> None:
    body = render_pru16_body(_model(NOT_CALLED))
    assert body.count(">Not yet<") == 3


def test_projection_summary_against_the_majority() -> None:
    body = render_pru16_body(_model(NOT_CALLED))
    assert "<b>116 Seats</b>, 4 more than the 112 needed for a Majority" in body
    assert "not calibrated against survey data" in body


def test_projection_unavailable_still_renders_the_page() -> None:
    body = render_pru16_body(_model(NOT_CALLED, coalitions=()))
    assert "The Projection is not available right now." in body
    assert "GE16 has not been called." in body
    assert "data-pk-lookup-form" in body


def test_bm_page_is_in_malay() -> None:
    body = render_pru16_body(_model(NOT_CALLED), Language.MS)
    assert "PRU16 belum diisytiharkan." in body
    assert "17 Februari 2028" in body
    assert "Belum" in body
    assert "Cari kerusi anda" in body
    assert "GE16 has not been called" not in body
    assert "Not yet" not in body

    called = render_pru16_body(_model(CALLED), Language.MS)
    assert "Tarikh mengundi belum diumumkan" in called


def test_pages_have_their_own_urls_and_no_text_arrows() -> None:
    for language, url in ((Language.EN, "/pru16/"), (Language.MS, "/ms/pru16/")):
        page = render_pru16_page(_model(NOT_CALLED), language)
        assert f'<link rel="canonical" href="https://politikku.my{url}">' in page
        assert "↗" not in page
        assert "→" not in render_pru16_body(_model(NOT_CALLED), language)


def test_telegram_link_is_a_placeholder_not_a_guess() -> None:
    body = render_pru16_body(_model(NOT_CALLED))
    assert 'href="https://t.me/REPLACE_ME"' in body
