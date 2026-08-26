"""The PolitikKu homepage (#74): model arithmetic and rendered markup.

Same discipline as `test_public_page.py` and `test_bill_tracker.py`:
structural assertions, never a hardcoded copy of a real number that would
keep passing if the underlying arithmetic broke. Where a concrete figure is
needed (the fixture `PageModel`), it is worked out by hand once and read
back from the same variable the assertion checks, the same way
`test_public_page.py`'s own margin/tier tests do — and over the same
`fixtures.two_coalition_seats()` baseline that file already uses, so its
worked-out margins/tiers are reusable rather than re-derived from scratch.
"""

from __future__ import annotations

from datetime import date

from fixtures import PH, PN, government_config
from pytest import approx

from lpa.aggregate import AggregatedSentiment
from lpa.bill_tracker import Bill, DivisionResult
from lpa.domain import ElectionStatus
from lpa.politikku_homepage import (
    BILLS_SHOWN,
    STAGE_LABELS_EN,
    HomepageModel,
    _stage_label,
    _top_bills,
    homepage_model,
    render_homepage,
    render_homepage_body,
)
from lpa.politikku_shell import Language, render_header
from lpa.public_page import PageModel, Tier, page_model
from lpa.storage import SentimentSnapshot
from lpa.swing_model import swing_model

NOT_CALLED = ElectionStatus(constitutional_deadline=date(2028, 2, 17), source="x")

NAMES = {"PH": "Pakatan Harapan", "PN": "Perikatan Nasional", "BN": "Barisan Nasional"}

_MARGIN_PATTERN = (
    {PH: 0.60, PN: 0.40},
    {PH: 0.55, PN: 0.45},
    {PH: 0.53, PN: 0.47},
    {PH: 0.52, PN: 0.48},
    {PH: 0.45, PN: 0.55},
    {PH: 0.35, PN: 0.65},
)
"""`fixtures.two_coalition_seats()`'s own six margins verbatim (+20pp,
+10pp, +6pp, +4pp PH; +10pp, +30pp PN) — reused rather than re-derived so
this fixture's tiers are exactly the ones that file's own tests already
hand-check."""


def _baseline_222() -> list:
    """222 Seats, `_MARGIN_PATTERN` tiled 37 times (222 / 6 is exact).

    `lpa.politikku_hemicycle.HemicycleCounts` fixes the chamber at exactly
    222 real Seats (`__post_init__` rejects any other total), so any
    `PageModel` this module's hemicycle tally runs against needs that many
    — a small hand-sized baseline like `two_coalition_seats()` on its own
    cannot reach `homepage_model()`'s hemicycle-tallying path at all. Tiling
    keeps every Seat's tier hand-checkable: each block of 6 repeats
    `_MARGIN_PATTERN` exactly, so 37 blocks give exactly 111
    Government-clear (PH, not Tight), 37 Tight (the one +4pp Seat in every
    block), and 74 Non-government-clear (PN, not Tight) Seats — 111 + 37 +
    74 = 222.
    """
    from fixtures import seat as _seat

    return [_seat(f"P{i:03d}", "Selangor", **_MARGIN_PATTERN[i % 6]) for i in range(222)]


def _page_model() -> PageModel:
    """A `PageModel` over `_baseline_222()`, no Sentiment/State Election
    Signal swing — so every Seat Call reproduces its own Baseline winner and
    margin exactly. Government Coalition is PH + GPS
    (`fixtures.government_config`); GPS contests nothing in this fixture,
    so the Government side is every PH Seat — 4 of every 6-block, 148 of
    222 — against a real 112-Seat Majority threshold.
    """
    baseline = _baseline_222()
    config = government_config(majority_threshold=112)
    projection = swing_model(baseline, {}, [], config, date(2026, 8, 23))
    return page_model(
        projection=projection,
        baseline=baseline,
        status=NOT_CALLED,
        config=config,
        names=NAMES,
        sentiment=None,
        state_election_signals=[],
        total_seats=len(baseline),
        state_swing={},
    )


def test_the_hemicycle_split_sorts_every_seat_by_tier_and_government_flag():
    model = homepage_model(_page_model(), [], NAMES, {})

    assert model.hemicycle.government_clear == 111  # the 3-of-6 PH pattern, x37
    assert model.hemicycle.noise == 37  # the +4pp Tight Seat, once per block
    assert model.hemicycle.nongovernment_clear == 74  # the 2-of-6 PN pattern, x37
    assert (
        model.hemicycle.government_clear
        + model.hemicycle.noise
        + model.hemicycle.nongovernment_clear
        == model.total_seats
        == 222
    )


def test_clear_seat_calls_excludes_only_the_tight_seats():
    model = homepage_model(_page_model(), [], NAMES, {})

    # 185 of 222 Seats are not Tier.TIGHT (37 are, one per 6-block).
    assert model.clear_seat_calls == 185
    assert model.clear_seat_calls == sum(
        1 for seat in _page_model().seats if seat.tier != Tier.TIGHT
    )


def _minimal_model(**overrides: object) -> HomepageModel:
    """A `HomepageModel` built by hand, for testing `margin_over_majority`
    in isolation from the Swing Model — the property is pure arithmetic on
    two already-tested `PageModel` fields, so it does not need a real
    Projection behind it, only a structurally valid one."""
    from lpa.politikku_hemicycle import HemicycleCounts

    settings: dict[str, object] = {
        "updated_at": date(2026, 8, 23),
        "sources_count": 3,
        "status": NOT_CALLED,
        "hemicycle": HemicycleCounts(government_clear=111, noise=37, nongovernment_clear=74),
        "government_seats": 148,
        "total_seats": 222,
        "majority_threshold": 112,
        "government_majority": True,
        "clear_seat_calls": 185,
        "sentiment_rows": (),
        "sentiment_total_articles": 0,
        "bills": (),
    }
    settings.update(overrides)
    return HomepageModel(**settings)  # type: ignore[arg-type]


def test_margin_over_majority_is_positive_when_the_government_clears_the_line():
    model = _minimal_model(government_seats=6, majority_threshold=4)
    assert model.margin_over_majority == 2


def test_margin_over_majority_is_negative_when_the_government_falls_short():
    model = _minimal_model(government_seats=3, majority_threshold=4, government_majority=False)
    assert model.margin_over_majority == -1


# ── sentiment digest ────────────────────────────────────────────────────

LATEST_DAY = date(2026, 8, 23)
SEVEN_DAYS_BACK = date(2026, 8, 16)  # exactly LATEST_DAY - DELTA_WINDOW
NOT_SEVEN_DAYS_BACK = date(2026, 8, 10)  # a decoy, closer but not exact


def _snapshot(day: date, scores: dict[str, float], counts: dict[str, int]) -> SentimentSnapshot:
    return SentimentSnapshot(
        computed_at=day,
        sentiment=AggregatedSentiment(
            scores=scores,
            article_counts=counts,
            total_articles=sum(counts.values()),
            sources=["Free Malaysia Today"],
        ),
    )


def test_a_coalition_in_both_snapshots_exactly_seven_days_apart_gets_a_real_delta():
    history = [
        _snapshot(NOT_SEVEN_DAYS_BACK, {PH: 0.50, PN: -0.50}, {PH: 9, PN: 9}),  # a decoy
        _snapshot(SEVEN_DAYS_BACK, {PH: 0.02, PN: 0.10}, {PH: 4, PN: 2}),
        _snapshot(LATEST_DAY, {PH: 0.10, PN: -0.05, "BN": 0.0}, {PH: 8, "BN": 5, PN: 3}),
    ]
    model = homepage_model(_page_model(), history, NAMES, {})

    by_coalition = {row.coalition: row for row in model.sentiment_rows}
    assert by_coalition[PH].delta == approx(0.10 - 0.02)
    assert by_coalition[PN].delta == approx(-0.05 - 0.10)
    # The decoy 10-days-back snapshot must never be used for the delta —
    # if it were, PH's delta would be nowhere near +0.08.


def test_a_coalition_absent_from_the_seven_day_snapshot_gets_no_delta_not_a_guess():
    history = [
        _snapshot(SEVEN_DAYS_BACK, {PH: 0.02}, {PH: 4}),
        _snapshot(LATEST_DAY, {PH: 0.10, "BN": 0.0}, {PH: 8, "BN": 5}),
    ]
    model = homepage_model(_page_model(), history, NAMES, {})

    by_coalition = {row.coalition: row for row in model.sentiment_rows}
    assert by_coalition["BN"].delta is None


def test_sentiment_rows_are_ordered_most_covered_coalition_first():
    history = [_snapshot(LATEST_DAY, {PH: 0.1, PN: 0.1, "BN": 0.1}, {PH: 8, "BN": 5, PN: 3})]
    model = homepage_model(_page_model(), history, NAMES, {})

    assert [row.coalition for row in model.sentiment_rows] == [PH, "BN", PN]


def test_an_empty_sentiment_history_produces_no_rows_and_no_article_count():
    model = homepage_model(_page_model(), [], NAMES, {})

    assert model.sentiment_rows == ()
    assert model.sentiment_total_articles == 0


def test_the_sentiment_row_names_a_coalition_absent_from_the_names_map_by_its_own_code():
    history = [_snapshot(LATEST_DAY, {"WARISAN": 0.2}, {"WARISAN": 2})]
    model = homepage_model(_page_model(), history, {}, {})

    assert model.sentiment_rows[0].name == "WARISAN"


# ── bill tracker ────────────────────────────────────────────────────────


def _bill(
    code: str, year: int, stage: str, stage_date: date, division: DivisionResult | None = None
) -> Bill:
    unverified = {} if division else {"division": "no vote taken at this stage"}
    return Bill(
        code=code,
        title=f"Title for {code}",
        year=year,
        stage=stage,
        stage_date=stage_date,
        summary="Ringkasan.",
        summary_source_url="https://www.parlimen.gov.my/example.pdf",
        division=division,
        unverified=unverified,
    )


DIVISION = DivisionResult(
    sitting_date=date(2026, 8, 15),
    ayes=125,
    noes=63,
    abstentions=1,
    absent=32,
    outcome="Dibacakan kali kedua",
    hansard_url="https://hansard.parlimen.gov.my/hansard/dewan-rakyat/2026-08-15",
)


def test_top_bills_caps_at_bills_shown_and_keeps_the_most_recent_first():
    bills = {
        "D.R.1/2026": _bill("D.R.1/2026", 2026, "Lulus", date(2026, 8, 1)),
        "D.R.2/2026": _bill("D.R.2/2026", 2026, "Dirujuk ke JKPK", date(2026, 7, 1)),
        "D.R.3/2026": _bill("D.R.3/2026", 2026, "Lulus", date(2026, 8, 15), DIVISION),
        "D.R.4/2026": _bill("D.R.4/2026", 2026, "Lulus", date(2026, 6, 1)),
    }
    top = _top_bills(bills)

    assert len(top) == BILLS_SHOWN == 3
    assert [b.code for b in top] == ["D.R.3/2026", "D.R.1/2026", "D.R.2/2026"]
    # The oldest of the four (D.R.4/2026) is the one left out.
    assert "D.R.4/2026" not in [b.code for b in top]


def test_a_mapped_stage_translates_and_an_unmapped_one_falls_back_to_the_original():
    for malay, english in STAGE_LABELS_EN.items():
        assert _stage_label(malay) == english
    assert _stage_label("Bacaan Kali Pertama") == "Bacaan Kali Pertama"


# ── rendering ─────────────────────────────────────────────────────────────


def _rendered_model() -> HomepageModel:
    bills = {
        "D.R.1/2026": _bill(
            "D.R.1/2026",
            2026,
            "Lulus",
            date(2026, 8, 1),
        ),
    }
    return homepage_model(_page_model(), [], NAMES, bills)


def test_the_body_carries_all_three_new_sections():
    from lpa.politikku_homepage import render_homepage_body

    body = render_homepage_body(_rendered_model())

    assert 'class="pk-hero"' in body
    assert 'class="pk-bills"' in body
    assert 'class="pk-sentiment"' in body


def test_the_full_page_wraps_the_body_in_the_shell_with_home_active():
    from lpa.politikku_homepage import render_homepage

    page = render_homepage(_rendered_model(), language=Language.EN)

    # NavLink.href for a localized link (home included) is a page-path
    # fragment routed through the current language, not the literal
    # rendered href — see politikku_shell.NavLink's own docstring (#81).
    header = render_header(active_nav="home", language=Language.EN, page_path="")
    # The site root since #104's cutover, not `/politikku/`.
    assert 'href="/" aria-current="page"' in header
    assert 'href="/" aria-current="page"' in page
    assert 'class="pk-footer"' in page  # the persistent methodology footer
    assert 'class="pk-hero"' in page  # the homepage's own body content


# ── #81: bilingual copy ──────────────────────────────────────────────────


def test_bm_headline_number_translates_the_of_separator_too():
    # A real gap the first cut of #81 shipped: only the surrounding copy was
    # translated, leaving the headline's own "146 of 222" in English.
    model = _rendered_model()
    ms = render_homepage_body(model, Language.MS)
    assert f"{model.government_seats} daripada {model.total_seats}" in ms
    assert f"{model.government_seats} of {model.total_seats}" not in ms
    assert f"{model.clear_seat_calls} daripada {model.total_seats}" in ms


def test_bm_rendering_differs_from_english_and_carries_the_settled_pairs():
    model = _rendered_model()
    en = render_homepage_body(model)
    ms = render_homepage_body(model, Language.MS)

    assert en != ms
    for pair in (
        "Cari Ahli Parlimen anda",  # Find your MP
        "Poskod atau nama kawasan",  # Postcode or constituency
        "Guna lokasi saya",  # Use my location
        "CARIAN KAWASAN",  # Constituency lookup (eyebrow, uppercased)
        "UNJURAN KERUSI PRU16",  # GE16 Seat Projection (eyebrow, uppercased)
        "Kerajaan jelas",  # Government clear
        "Dalam ralat model",  # Within model noise
        "Bukan kerajaan jelas",  # Non-government clear
        "Dewan Rakyat minggu ini",  # Dewan Rakyat this week
    ):
        assert pair in ms
        assert pair not in en


def test_the_not_calibrated_tag_stays_inline_beside_the_number_in_bm_not_a_banner():
    model = _rendered_model()
    ms = render_homepage_body(model, Language.MS)

    assert "BELUM DITENTUKUR" in ms
    assert '<span class="pk-tag-modelled">NOT CALIBRATED</span>' not in ms
    # Inline beside the headline number, not hoisted to a page-level banner:
    # the tag sits inside the same projection headline block as the number.
    headline_start = ms.index('class="pk-projection-headline"')
    headline_end = ms.index("</div>", ms.index("BELUM DITENTUKUR"))
    assert headline_start < ms.index("BELUM DITENTUKUR") < headline_end


def test_bm_bill_stage_shows_parliaments_own_word_not_an_invented_translation():
    bills = {
        "D.R.1/2026": _bill("D.R.1/2026", 2026, "Lulus", date(2026, 8, 1)),
        "D.R.2/2026": _bill("D.R.2/2026", 2026, "Dirujuk ke JKPK", date(2026, 7, 1)),
    }
    model = homepage_model(_page_model(), [], NAMES, bills)
    ms = render_homepage_body(model, Language.MS)
    en = render_homepage_body(model, Language.EN)

    assert "Lulus" in ms
    assert "Dirujuk ke JKPK" in ms
    assert "Passed" in en
    assert "Referred to Special Select Committee" in en


def test_the_full_bm_page_wraps_in_the_shell_with_the_bm_lang_attribute():
    page = render_homepage(_rendered_model(), language=Language.MS)
    assert '<html lang="ms">' in page
    assert "Cari Ahli Parlimen anda" in page


def test_a_bill_title_carrying_markup_cannot_break_out_of_the_card():
    from lpa.politikku_homepage import render_homepage_body

    hostile = Bill(
        code="D.R.9/2026",
        title='</h3><script>alert(1)</script><h3 x="',
        year=2026,
        stage="Lulus",
        stage_date=date(2026, 8, 1),
        summary='Ringkasan dengan "petikan" & <tanda>.',
        summary_source_url="https://www.parlimen.gov.my/example.pdf",
        division=None,
        unverified={"division": "no vote taken at this stage"},
    )
    model = homepage_model(_page_model(), [], NAMES, {"D.R.9/2026": hostile})

    body = render_homepage_body(model)

    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;" in body
    assert '"petikan"' not in body
    assert "&quot;petikan&quot;" in body
