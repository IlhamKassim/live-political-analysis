"""The dissolution watch: what counts as the event, and what is only talk."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from lpa.dissolution_watch import (
    Signal,
    SignalKind,
    compose_alert,
    scan,
    send_alert,
)
from lpa.domain import Article, ElectionStatus

DEADLINE = date(2028, 2, 17)
SOURCE = "https://www.parlimen.gov.my/"
NOT_CALLED = ElectionStatus(constitutional_deadline=DEADLINE, source=SOURCE)
CALLED = ElectionStatus(
    constitutional_deadline=DEADLINE, source=SOURCE, dissolved_on=date(2026, 10, 1)
)
SETTLED = ElectionStatus(
    constitutional_deadline=DEADLINE,
    source=SOURCE,
    dissolved_on=date(2026, 10, 1),
    nomination_date=date(2026, 10, 20),
    polling_date=date(2026, 11, 3),
)


def _article(text: str, *, title: str = "Headline", source: str = "Bernama") -> Article:
    return Article(
        source=source,
        url=f"https://example.test/{abs(hash(text))}",
        published_at=datetime(2026, 10, 1, tzinfo=UTC),
        title=title,
        text=text,
    )


@pytest.mark.parametrize(
    "text",
    [
        "The Dewan Rakyat has been dissolved, paving the way for GE16.",
        "The King consented to the dissolution of Parliament this morning.",
        "Dewan Rakyat dibubarkan pagi ini.",
        "Perkenan pembubaran Parlimen telah diberikan.",
        "The Prime Minister dissolved Parliament after an audience with the Agong.",
    ],
)
def test_a_dissolution_that_happened_is_reported(text: str) -> None:
    (signal,) = scan([_article(text)], NOT_CALLED)
    assert signal.kind is SignalKind.DISSOLUTION
    assert signal.sentence


@pytest.mark.parametrize(
    "text",
    [
        "Analysts expect Parliament to be dissolved before the end of the year.",
        "Parliament could be dissolved as early as November, sources say.",
        "The opposition urges the dissolution of Parliament.",
        "Parlimen dijangka dibubarkan pada hujung tahun.",
        "Spekulasi pembubaran Parlimen semakin meningkat.",
        "If Parliament is dissolved this year, the campaign would be short.",
        "Parlimen mungkin dibubarkan selepas bajet.",
        # Advocacy, not news. Both inflections, because the headline and the
        # body of the same story routinely use different ones.
        "The opposition leader called for the dissolution of Parliament.",
        "Civil society groups are calling for the dissolution of Parliament.",
        "The opposition urges the immediate dissolution of Parliament.",
    ],
)
def test_speculation_is_not_reported(text: str) -> None:
    """The whole risk of this module is here. Malaysian coverage speculates
    about early polls constantly; a watch that fires on it is a watch nobody
    reads by the time it matters."""
    assert scan([_article(text)], NOT_CALLED) == ()


def test_a_real_report_survives_a_quoted_prediction() -> None:
    """A report of a real dissolution usually also quotes someone who called
    it. Hedges are checked per sentence, so the report is still reported."""
    text = (
        "The Dewan Rakyat was dissolved this morning. "
        "Analysts had expected the move since the budget passed."
    )
    (signal,) = scan([_article(text)], NOT_CALLED)
    assert signal.kind is SignalKind.DISSOLUTION
    assert "dissolved this morning" in signal.sentence


def test_the_headline_alone_can_carry_the_signal() -> None:
    article = _article("Full coverage inside.", title="Dewan Rakyat dissolved")
    (signal,) = scan([article], NOT_CALLED)
    assert signal.kind is SignalKind.DISSOLUTION


def test_it_silences_itself_once_the_fact_is_recorded() -> None:
    """The point of passing the status in: there is nothing to tell anyone
    about a dissolution we have already written down."""
    text = "The Dewan Rakyat has been dissolved."
    assert scan([_article(text)], NOT_CALLED) != ()
    assert scan([_article(text)], CALLED) == ()


def test_polling_dates_are_watched_until_they_are_set() -> None:
    text = "The Election Commission said polling day is 3 November."
    (signal,) = scan([_article(text)], CALLED)
    assert signal.kind is SignalKind.POLLING_DATE
    assert scan([_article(text)], SETTLED) == ()


def test_nothing_is_watched_once_every_date_is_known() -> None:
    article = _article("The Dewan Rakyat has been dissolved. Polling day is 3 November.")
    assert scan([article], SETTLED) == ()


def test_ordinary_coverage_is_ignored() -> None:
    articles = [
        _article("The Dewan Rakyat passed the supply bill at its second reading."),
        _article("Sidang Dewan Rakyat bersambung minggu depan."),
    ]
    assert scan(articles, NOT_CALLED) == ()


@pytest.mark.parametrize(
    "text",
    [
        "The state assembly was dissolved ahead of the state election.",
        "Dewan Undangan Negeri Johor dibubarkan hari ini.",
        "The Selangor state assembly has been dissolved.",
    ],
)
def test_a_state_assembly_dissolving_is_a_different_event(text: str) -> None:
    """State assemblies dissolve for state elections regularly and it says
    nothing about GE16. Every pattern is anchored on the national chamber by
    name so this cannot fire."""
    assert scan([_article(text)], NOT_CALLED) == ()


def test_the_quoted_sentence_keeps_its_original_case() -> None:
    """The sentence is what a human reads to judge the story in two seconds,
    so it must not arrive flattened to lowercase."""
    article = _article("The Dewan Rakyat was dissolved this morning.", title="GE16 latest")
    (signal,) = scan([article], NOT_CALLED)
    assert "The Dewan Rakyat was dissolved this morning." in signal.sentence


def test_signals_survive_the_round_trip_through_the_file(tmp_path) -> None:
    """The pipeline writes what it found and a separate step sends it, so the
    file between them has to carry every field the message needs."""
    from lpa.dissolution_watch import read_signals, write_signals

    signals = scan([_article("Parliament has been dissolved.")], NOT_CALLED)
    path = tmp_path / "signals.json"
    write_signals(signals, path)
    assert read_signals(path) == signals


def test_a_quiet_day_still_writes_a_file(tmp_path) -> None:
    """A missing file and an empty one mean different things: no signals
    today, versus a pipeline that fell over before it got here."""
    from lpa.dissolution_watch import read_signals, write_signals

    path = tmp_path / "signals.json"
    write_signals((), path)
    assert path.exists()
    assert read_signals(path) == ()
    assert read_signals(tmp_path / "never-written.json") == ()


def test_the_alert_says_what_happened_what_to_do_and_that_nothing_was_published() -> None:
    signals = (
        Signal(
            kind=SignalKind.DISSOLUTION,
            source="Bernama",
            title="Dewan Rakyat dissolved",
            url="https://example.test/a",
            sentence="the dewan rakyat has been dissolved.",
        ),
    )
    message = compose_alert(signals)
    assert "dissolved" in message
    assert "dissolved_on" in message
    assert "data/election_status.json" in message
    assert "https://example.test/a" in message
    assert "Nothing has been published." in message


def test_the_alert_lists_each_story_once() -> None:
    """One story matching on both its headline and its body is still one story."""
    signals = tuple(
        Signal(
            kind=SignalKind.DISSOLUTION,
            source="Bernama",
            title="Dewan Rakyat dissolved",
            url="https://example.test/a",
            sentence=sentence,
        )
        for sentence in ("dewan rakyat dissolved.", "parliament has been dissolved.")
    )
    assert compose_alert(signals).count("https://example.test/a") == 1


def test_the_alert_escapes_a_hostile_headline() -> None:
    """Headlines are scraped from outlets we do not control and the message is
    sent as HTML, so a stray tag must not become markup."""
    signals = (
        Signal(
            kind=SignalKind.DISSOLUTION,
            source="Outlet",
            title="<b>Dissolved</b> & gone",
            url="https://example.test/a?x=1&y=2",
            sentence="parliament dissolved.",
        ),
    )
    message = compose_alert(signals)
    assert "<b>Dissolved</b> & gone" not in message
    assert "&lt;b&gt;Dissolved&lt;/b&gt; &amp; gone" in message
    assert "x=1&amp;y=2" in message


def test_send_alert_posts_to_the_bot_api() -> None:
    sent: dict[str, object] = {}

    class _Response:
        def raise_for_status(self) -> None:
            return None

    class _Client:
        def post(self, url: str, data: dict[str, str]) -> _Response:
            sent["url"] = url
            sent["data"] = data
            return _Response()

    send_alert(_Client(), "TOKEN", "-100123", "hello")
    assert sent["url"] == "https://api.telegram.org/botTOKEN/sendMessage"
    assert sent["data"] == {
        "chat_id": "-100123",
        "text": "hello",
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }
