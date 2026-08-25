"""The PolitikKu landing page (#75): model arithmetic and rendered markup.

Same discipline as `test_public_page.py` and the closest sibling
`test_politikku_homepage.py`: structural assertions, never a hardcoded copy
of a real number that would keep passing if the underlying arithmetic
broke. `politikku_landing.py` literally reuses `politikku_homepage.py`'s
`hemicycle_counts`/`sentiment_rows` and its `_page_model()`/`NAMES`
fixtures rather than reinventing them, so this file imports those directly
instead of building a second 222-Seat baseline.
"""

from __future__ import annotations

from datetime import date

import pytest
from test_politikku_homepage import NAMES, _page_model

from lpa.aggregate import AggregatedSentiment
from lpa.bill_tracker import Bill, DivisionResult
from lpa.mp_profile import Contact, GE15Result, MPProfile
from lpa.politikku_homepage import hemicycle_counts
from lpa.politikku_landing import (
    RECENT_ARTICLE_WINDOW_DAYS,
    CardKind,
    _recent_articles,
    _sentiment_mover_card,
    landing_model,
    render_landing,
    render_landing_body,
)
from lpa.politikku_shell import Language
from lpa.storage import SentimentSnapshot

PH = "PH"
PN = "PN"

# Bangi/Syahredzan Johan's real GE15 figures (data/mp_profiles.json, ADR
# 0009) — the FACT card's source, checked against the repo's real data the
# same way the module's own docstring already did before shipping it.
BANGI = MPProfile(
    seat_code="P000",  # one of `_page_model()`'s own P000..P221 codes
    name="YB Tuan Syahredzan bin Johan",
    coalition="PH",
    term_start=date(2022, 12, 19),
    ge15=GE15Result(
        votes=141568,
        majority=69701,
        vote_share=0.5795055896451363,
        valid_votes=244291,
        runner_up_votes=71867,
        runner_up_coalition="PN",
        electors=303430,
        turnout=0.8133506904393105,
        source_url=(
            "https://raw.githubusercontent.com/Thevesh/analysis-election-msia/"
            "main/data/results_parlimen_ge15.csv"
        ),
    ),
    contact=Contact(),
)

BANGI_NO_MATCHING_SEAT = MPProfile(
    seat_code="P.999",  # not a code any `_page_model()` Seat carries
    name="Nobody",
    coalition="PH",
    term_start=date(2022, 12, 19),
    ge15=BANGI.ge15,
    contact=Contact(),
)

# D.R.28/2025's real Division (data/bills.json, ADR 0010) — the second FACT
# card's source.
FEATURED_BILL = Bill(
    code="D.R.28/2025",
    title="RUU Perolehan Kerajaan 2025",
    year=2025,
    stage="Lulus",
    stage_date=date(2025, 8, 28),
    summary="Ringkasan.",
    summary_source_url="https://www.parlimen.gov.my/example.pdf",
    division=DivisionResult(
        sitting_date=date(2025, 8, 28),
        ayes=125,
        noes=63,
        abstentions=1,
        absent=32,
        outcome="Dibacakan kali kedua",
        hansard_url="https://hansard.parlimen.gov.my/hansard/dewan-rakyat/2025-08-28",
    ),
    unverified={},
)

BILL_WITH_NO_DIVISION = Bill(
    code="D.R.1/2025",
    title="A Bill with no Division",
    year=2025,
    stage="Dirujuk ke JKPK",
    stage_date=date(2025, 1, 1),
    summary="Ringkasan.",
    summary_source_url="https://www.parlimen.gov.my/example.pdf",
    division=None,
    unverified={"division": "no vote taken at this stage"},
)


def _snapshot(day: date, scores: dict[str, float], counts: dict[str, int]) -> SentimentSnapshot:
    """Same shape as `test_politikku_homepage.py`'s own `_snapshot` — real
    `SentimentSnapshot`/`AggregatedSentiment`, not an invented one, so a
    delta test here actually exercises `sentiment_rows`' real arithmetic."""
    return SentimentSnapshot(
        computed_at=day,
        sentiment=AggregatedSentiment(
            scores=scores,
            article_counts=counts,
            total_articles=sum(counts.values()),
            sources=["Free Malaysia Today"],
        ),
    )


LATEST_DAY = date(2026, 8, 23)
SEVEN_DAYS_BACK = date(2026, 8, 16)
NOT_SEVEN_DAYS_BACK = date(2026, 8, 10)


def test_recent_articles_on_an_empty_history_is_zero_and_zero():
    assert _recent_articles([]) == (0, 0)


def test_recent_articles_sums_a_short_history_and_reports_the_real_day_count():
    history = [
        _snapshot(date(2026, 8, 21), {PH: 0.1}, {PH: 10}),
        _snapshot(date(2026, 8, 22), {PH: 0.1}, {PH: 20}),
        _snapshot(LATEST_DAY, {PH: 0.1}, {PH: 30}),
    ]
    assert _recent_articles(history) == (60, 3)


def test_recent_articles_only_sums_the_window_not_the_whole_history():
    old_and_huge = _snapshot(date(2026, 8, 1), {PH: 0.1}, {PH: 100_000})
    window = [
        _snapshot(date(2026, 8, 23 - n), {PH: 0.1}, {PH: 10})
        for n in range(RECENT_ARTICLE_WINDOW_DAYS)
    ]
    articles, days = _recent_articles([old_and_huge, *window])
    assert days == RECENT_ARTICLE_WINDOW_DAYS
    assert articles == 10 * RECENT_ARTICLE_WINDOW_DAYS  # the huge old count never leaks in


def _history() -> list[SentimentSnapshot]:
    return [_snapshot(LATEST_DAY, {PH: 0.1}, {PH: 5})]


def test_landing_model_cards_are_fact_fact_model_model_in_order():
    model = landing_model(_page_model(), _history(), NAMES, BANGI, FEATURED_BILL)
    assert [c.kind for c in model.cards] == [
        CardKind.FACT,
        CardKind.FACT,
        CardKind.MODEL,
        CardKind.MODEL,
    ]


def test_the_first_card_states_the_real_bangi_majority_and_seat_name():
    page = _page_model()
    model = landing_model(page, _history(), NAMES, BANGI, FEATURED_BILL)
    seat = next(s for s in page.seats if s.code == BANGI.seat_code)

    card = model.cards[0]
    assert BANGI.name in card.claim_en
    assert seat.name in card.claim_en
    assert f"{BANGI.ge15.majority:,}" in card.claim_en


def test_the_second_card_states_the_real_bill_division_and_title():
    model = landing_model(_page_model(), _history(), NAMES, BANGI, FEATURED_BILL)
    d = FEATURED_BILL.division

    card = model.cards[1]
    assert FEATURED_BILL.title in card.claim_en
    assert f"{d.ayes}" in card.claim_en
    assert f"{d.noes}" in card.claim_en


def test_the_third_card_states_the_same_seat_counts_the_homepage_would():
    page = _page_model()
    model = landing_model(page, _history(), NAMES, BANGI, FEATURED_BILL)

    card = model.cards[2]
    assert f"{page.government_seats} of {page.total_seats}" in card.claim_en


def test_the_hemicycle_matches_politikku_homepages_own_tally_not_a_second_copy():
    page = _page_model()
    model = landing_model(page, _history(), NAMES, BANGI, FEATURED_BILL)

    assert model.hemicycle == hemicycle_counts(page)


def test_landing_model_raises_when_the_mp_profiles_seat_has_no_baseline_match():
    with pytest.raises(ValueError, match="P.999"):
        landing_model(_page_model(), _history(), NAMES, BANGI_NO_MATCHING_SEAT, FEATURED_BILL)


def test_landing_model_raises_when_the_featured_bill_has_no_division():
    with pytest.raises(ValueError, match="D.R.1/2025"):
        landing_model(_page_model(), _history(), NAMES, BANGI, BILL_WITH_NO_DIVISION)


def test_the_mover_card_names_whichever_coalition_moved_most_not_a_hardcoded_one():
    history = [
        _snapshot(NOT_SEVEN_DAYS_BACK, {PH: 0.50, PN: -0.50}, {PH: 9, PN: 9}),  # decoy
        _snapshot(SEVEN_DAYS_BACK, {PH: 0.02, PN: 0.10}, {PH: 4, PN: 2}),
        _snapshot(LATEST_DAY, {PH: 0.10, PN: -0.05}, {PH: 8, PN: 3}),
    ]
    model = landing_model(_page_model(), history, NAMES, BANGI, FEATURED_BILL)

    # PN's real delta (-0.05 - 0.10 = -0.15) is larger in magnitude than
    # PH's (0.10 - 0.02 = 0.08), so PN is the real mover, not PH — the
    # mockup this replaces hardcoded "Coverage of PH rose...".
    card = model.cards[3]
    assert NAMES[PN] in card.claim_en
    assert "fell" in card.claim_en
    assert "15.0 points" in card.claim_en


def test_the_mover_card_states_no_movement_when_history_is_empty():
    card = _sentiment_mover_card([], NAMES)
    assert card.claim_en == "Not enough Sentiment history yet to state a week-over-week move"


def test_every_card_stating_a_modelled_number_is_flagged_for_the_trust_tag():
    """Trust rule 1 (non-negotiable): NOT CALIBRATED travels beside every
    modelled number, never on factual data. Both FACT cards state real,
    sourced facts; the Seat-projection MODEL card and a real mover both
    state a modelled number and must be flagged."""
    history = [
        _snapshot(SEVEN_DAYS_BACK, {PH: 0.02}, {PH: 4}),
        _snapshot(LATEST_DAY, {PH: 0.10}, {PH: 8}),
    ]
    model = landing_model(_page_model(), history, NAMES, BANGI, FEATURED_BILL)

    fact_1, fact_2, model_seats, model_mover = model.cards
    assert fact_1.modelled_number is False
    assert fact_2.modelled_number is False
    assert model_seats.modelled_number is True
    assert model_mover.modelled_number is True


def test_the_no_movement_fallback_card_states_no_number_so_carries_no_tag():
    # Nothing for the tag to travel beside — see TrustCard.modelled_number's
    # own docstring.
    card = _sentiment_mover_card([], NAMES)
    assert card.modelled_number is False


def test_the_tag_renders_inline_beside_modelled_claims_and_never_on_fact_claims():
    # A real 7-days-apart pair, so the mover card states an actual delta
    # (not the no-history fallback, which carries no tag — see above).
    history = [
        _snapshot(SEVEN_DAYS_BACK, {PH: 0.02}, {PH: 4}),
        _snapshot(LATEST_DAY, {PH: 0.10}, {PH: 8}),
    ]
    model = landing_model(_page_model(), history, NAMES, BANGI, FEATURED_BILL)
    body = render_landing_body(model)

    tag = '<span class="pk-tag-modelled">NOT CALIBRATED</span>'
    assert body.count(tag) == 2  # exactly the two number-stating MODEL cards


def test_landing_model_with_no_sentiment_history_reports_no_movement_too():
    model = landing_model(_page_model(), [], NAMES, BANGI, FEATURED_BILL)
    assert (
        model.cards[3].claim_en == "Not enough Sentiment history yet to state a week-over-week move"
    )


def test_the_body_carries_every_section():
    model = landing_model(_page_model(), _history(), NAMES, BANGI, FEATURED_BILL)
    body = render_landing_body(model)

    for css_class in (
        "pk-landing-hero",
        "pk-landing-stats",
        "pk-landing-inside",
        "pk-landing-trust",
        "pk-landing-search-cta",
    ):
        assert f'"{css_class}' in body or f" {css_class}" in body


def test_the_full_page_wraps_the_body_in_the_persistent_shell():
    model = landing_model(_page_model(), _history(), NAMES, BANGI, FEATURED_BILL)
    page = render_landing(model)

    assert 'class="pk-footer"' in page  # the persistent methodology footer
    assert 'class="pk-landing-hero"' in page  # the landing page's own body


# ── #81: bilingual copy ──────────────────────────────────────────────────


def test_bm_rendering_differs_from_english_and_carries_the_settled_pairs():
    model = landing_model(_page_model(), _history(), NAMES, BANGI, FEATURED_BILL)
    en = render_landing_body(model)
    ms = render_landing_body(model, Language.MS)

    assert en != ms
    for pair in (
        "Cari Ahli Parlimen anda",  # Find your MP
        "Poskod atau nama kawasan",  # Postcode or constituency name
        "Unjuran kerusi PRU16",  # GE16 Seat Projection
    ):
        assert pair in ms
        assert pair not in en


def test_bm_trust_cards_keep_the_same_sourced_numbers_as_english():
    model = landing_model(_page_model(), _history(), NAMES, BANGI, FEATURED_BILL)
    ms = render_landing_body(model, Language.MS)

    assert BANGI.name in ms
    assert f"{BANGI.ge15.majority:,}" in ms
    assert FEATURED_BILL.title in ms
    assert f"{FEATURED_BILL.division.ayes}" in ms  # type: ignore[union-attr]


def test_the_not_calibrated_tag_translates_and_stays_inline_in_bm():
    history = [
        _snapshot(SEVEN_DAYS_BACK, {PH: 0.02}, {PH: 4}),
        _snapshot(LATEST_DAY, {PH: 0.10}, {PH: 8}),
    ]
    model = landing_model(_page_model(), history, NAMES, BANGI, FEATURED_BILL)
    ms = render_landing_body(model, Language.MS)

    tag = '<span class="pk-tag-modelled">BELUM DITENTUKUR</span>'
    assert ms.count(tag) == 2  # the two number-stating MODEL cards, same as the English count
    assert "NOT CALIBRATED" not in ms


def test_the_full_bm_page_wraps_in_the_shell_with_the_bm_lang_attribute():
    model = landing_model(_page_model(), _history(), NAMES, BANGI, FEATURED_BILL)
    page = render_landing(model, language=Language.MS)
    assert '<html lang="ms">' in page
    assert "Cari Ahli Parlimen anda" in page


def test_a_bill_title_carrying_markup_cannot_break_out_of_the_card():
    hostile = Bill(
        code="D.R.9/2026",
        title='</h3><script>alert(1)</script><h3 x="',
        year=2026,
        stage="Lulus",
        stage_date=date(2026, 8, 1),
        summary="Ringkasan.",
        summary_source_url="https://www.parlimen.gov.my/example.pdf",
        division=DivisionResult(
            sitting_date=date(2026, 8, 1),
            ayes=1,
            noes=0,
            abstentions=0,
            absent=0,
            outcome="Diluluskan",
            hansard_url="https://hansard.parlimen.gov.my/hansard/dewan-rakyat/2026-08-01",
        ),
        unverified={},
    )
    model = landing_model(_page_model(), _history(), NAMES, BANGI, hostile)

    body = render_landing_body(model)

    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;" in body
