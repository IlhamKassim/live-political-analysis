"""PolitikKu's `/projection/` detail page and its methodology page (#102).

Same discipline as `test_politikku_landing.py`/`test_politikku_mp_profile.py`:
structural assertions against the real `PageModel`, never a hardcoded copy of
a number that would keep passing if the arithmetic behind it broke. Every
figure asserted here is read back off the same model the renderer was handed.

`politikku_projection` states no numbers of its own — `public_page.page_model`
computes all of them, and `test_public_page.py` already hand-checks that
arithmetic. So what is tested here is the port: that each section #102 lists
is actually on the page, that it states the model's own figures rather than a
second derivation of them, that the BM route carries BM copy including the
caveats ADR 0005 makes load-bearing, and that the routing/permalink paths the
page prints match the files `main` writes.

The 222-Seat fixture is `test_politikku_homepage`'s own: `politikku_hemicycle
.HemicycleCounts` rejects any chamber that is not exactly 222 real Seats, so a
hand-sized baseline cannot reach `render_projection` at all.
"""

from __future__ import annotations

import re
import sys
from datetime import date, timedelta

import pytest
from fixtures import PH, PN, government_config
from test_politikku_homepage import NAMES, _baseline_222

from lpa.domain import ElectionStatus, Projection
from lpa.politikku_projection import (
    PROJECTION_PAGE,
    _permalink_url,
    build_all_methodology_languages,
    build_all_projection_languages,
    main,
    render_methodology,
    render_methodology_body,
    render_projection,
    render_projection_body,
)
from lpa.politikku_shell import (
    METHODOLOGY_PAGE,
    PROJECTION_PREFIX,
    Language,
    methodology_url,
    projection_url,
)
from lpa.public_page import (
    MIN_TREND_READINGS,
    SITE_URL,
    PageModel,
    _permalink_path,
    _points,
    _tier_label,
    page_model,
)
from lpa.swing_model import swing_model

NOT_CALLED = ElectionStatus(constitutional_deadline=date(2028, 2, 17), source="x")

TODAY = date(2026, 8, 23)
"""The day `_projection_model`'s own Projection is computed on — a history
ending here and the rest of the page agree about which day is today."""


def _projection_model(*, history=(), majority_threshold=112) -> PageModel:
    """`test_politikku_homepage._page_model()`, with a `history` seam.

    That fixture passes no `history`, which leaves `PageModel.trend` holding
    today's run alone — the one state the Majority-margin section (#45) is
    *not* mainly about. This page is the trend's home, so its tests need to
    reach all three of that section's branches.
    """
    baseline = _baseline_222()
    config = government_config(majority_threshold=majority_threshold)
    projection = swing_model(baseline, {}, [], config, TODAY)
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
        history=history,
    )


def _stored_runs(margins, last_day=TODAY, step=1, majority_threshold=112):
    """One stored Projection per margin, oldest first, `step` days apart.

    `margins` are Seats clear of the Majority line, so putting
    `majority_threshold + margin` Seats on PH (a Government Coalition in
    `government_config`) puts the Government Coalition exactly that far past
    it — the same shape `test_public_page.stored_runs` uses.
    """
    last = len(margins) - 1
    return [
        Projection(
            coalition_seat_totals={
                PH: majority_threshold + margin,
                PN: 222 - majority_threshold - margin,
            },
            government_majority=margin >= 0,
            computed_at=last_day - timedelta(days=(last - i) * step),
        )
        for i, margin in enumerate(margins)
    ]


def _markup(page: str) -> str:
    """The page without its `<style>`/`<script>` blocks.

    Every section's own class name appears in the CSS as well as in the
    markup, so a "this section is not on this page" assertion has to look at
    the markup alone or it can never fail.
    """
    return re.sub(r"<(style|script)\b.*?</\1>", "", page, flags=re.DOTALL)


def _band(page: str, css_class: str) -> str:
    """One `_band` section's own markup, from its opening tag to the next."""
    opening = re.search(rf'<section class="pk-proj-band[^"]*\b{css_class}">', page)
    assert opening is not None, f"no {css_class} band on the page"
    return page[opening.end() :].split("<section ")[0]


def _rows(section: str) -> list[str]:
    """A table's body rows — never its `<thead>` row, which is markup about
    the table rather than a row of it."""
    bodies = re.findall(r"<tbody>(.*?)</tbody>", section, re.DOTALL)
    return re.findall(r"<tr\b[^>]*>", "".join(bodies))


# ── every section #102 asked for is actually on the page ──────────────────


@pytest.mark.parametrize("language", list(Language))
def test_every_section_the_ticket_lists_is_on_the_page(language):
    # #102's own scope list, one band each. A section quietly missing is the
    # failure mode a port has that a rewrite does not.
    body = render_projection_body(_projection_model(history=_stored_runs([0, 1] * 7)), language)

    for section in (
        "pk-proj-hero",  # chamber + headline tally
        "pk-proj-tipping-band",  # tipping point (#50)
        "pk-proj-ledger",  # seat ledger
        "pk-proj-stress",  # sensitivity-to-marginals what-ifs
        "pk-proj-trend",  # Majority-margin trend (#45)
        "pk-proj-too-close",  # "Too close" module (#48)
        "pk-proj-sensitivity",  # unfitted-constant table (#51)
        "pk-proj-rollup",  # per-state rollup (#53)
        "pk-proj-seats",  # full seat table + filter (#42/#47)
        "pk-proj-provenance",  # dated permalink (#55)
    ):
        assert f"pk-proj-band {section}" in body or f"pk-proj-band-alt {section}" in body


# ── the full seat table and its filter (#42/#47) ──────────────────────────


@pytest.mark.parametrize("language", list(Language))
def test_the_seat_table_carries_every_seat_visibly_with_its_own_anchor(language):
    model = _projection_model()
    seats = _band(render_projection_body(model, language), "pk-proj-seats")

    # Visible, unlike `public_page._seat_table`'s `visually-hidden` copy —
    # on a page whose reason for existing is per-Seat depth it is the main
    # event, not the chamber's keyboard-reachable shadow.
    assert "visually-hidden" not in seats
    assert seats.count("<tr id=") == len(model.seats) == 222
    for seat in model.seats:
        assert f'<tr id="seat-{seat.code}" data-seat="{seat.code}"' in seats
        assert _points(seat.margin) in seats


def test_the_seat_tables_search_index_is_in_the_pages_own_language():
    # #43: a BM reader typing "selamat" must find the rows the column
    # labelled "Selamat", not fall through to an EN word silently indexed
    # underneath a BM-labelled column.
    model = _projection_model()
    seat = model.seats[0]
    ms = _band(render_projection_body(model, Language.MS), "pk-proj-seats")
    en = _band(render_projection_body(model, Language.EN), "pk-proj-seats")

    assert _tier_label(seat.tier, Language.MS).lower() in ms
    assert _tier_label(seat.tier, Language.EN).lower() in en
    assert _tier_label(seat.tier, Language.EN).lower() not in ms


@pytest.mark.parametrize("language", list(Language))
def test_the_filter_is_progressive_and_announces_its_count_in_language(language):
    body = render_projection_body(_projection_model(), language)

    # The input and its live region exist, and the script is additive — a
    # script-disabled reader keeps a fully populated, unfiltered table.
    assert 'id="pk-proj-seat-filter"' in body
    assert 'aria-live="polite"' in body
    assert 'type="search"' in body
    expected = " of " if language is Language.EN else " daripada "
    assert f'matched + "{expected}" + total' in body


# ── the seat ledger ───────────────────────────────────────────────────────


@pytest.mark.parametrize("language", list(Language))
def test_the_ledger_states_every_coalition_in_both_layouts(language):
    # Both layouts are rendered and exactly one is shown per breakpoint (a
    # Coalition row read sideways is one a phone reader does not read), so a
    # Coalition missing from either is a Coalition missing on some screen.
    model = _projection_model()
    ledger = _band(render_projection_body(model, language), "pk-proj-ledger")
    wide = ledger.split('<div class="pk-proj-ledger-narrow">')[0]
    narrow = ledger.split('<div class="pk-proj-ledger-narrow">')[1]

    for row in model.ledger:
        assert row.name in wide
        assert row.name in narrow
    # One row per Coalition plus the Government-total row, in each layout.
    assert len(_rows(wide)) == len(model.ledger) + 1
    assert narrow.count('class="pk-proj-stack-row') == len(model.ledger) + 1


@pytest.mark.parametrize("language", list(Language))
def test_the_government_total_row_states_no_ge15_figure_and_says_why(language):
    # `public_page`'s own category point, ported: the Government Coalition
    # formed after GE15 by agreement, so it had no GE15 total — an em-dash
    # with a reason, not a missing number.
    model = _projection_model()
    ledger = _band(render_projection_body(model, language), "pk-proj-ledger")

    assert f'class="pk-proj-figure">{model.government_seats}<' in ledger
    # Two em-dashed cells per layout (GE15 and the Swing against it), and the
    # first of each pair carries the reason as its tooltip.
    assert ledger.count('class="pk-proj-na"') == 4
    assert ledger.count('class="pk-proj-na" title=') == 2
    reason = (
        "Gabungan Kerajaan terbentuk selepas PRU15"
        if language is Language.MS
        else "The Government Coalition formed after GE15"
    )
    assert reason in ledger


# ── the sensitivity table (#51) ───────────────────────────────────────────


@pytest.mark.parametrize("language", list(Language))
def test_the_sensitivity_table_is_one_row_per_constant_and_never_a_range(language):
    model = _projection_model()
    section = _band(render_projection_body(model, language), "pk-proj-sensitivity")

    assert len(_rows(section)) == len(model.sensitivity_table)
    for value, total in model.sensitivity_table:
        assert f">{value:.2f}<" in section
        assert f">{total}<" in section
    # The caveat is the point of the section, in both languages — a BM copy
    # that dropped it would let the table read as the confidence interval
    # the EN one is built not to imply.
    denial = (
        "bukan julat kemungkinan hasil"
        if language is Language.MS
        else "not a range of likely outcomes"
    )
    assert denial in section
    assert "confidence" not in section.lower()


# ── the Majority-margin trend (#45) ───────────────────────────────────────


def test_one_stored_run_is_a_reading_and_not_a_trend():
    model = _projection_model()
    trend = _band(render_projection_body(model, Language.EN), "pk-proj-trend")

    assert len(model.trend) == 1
    assert not model.trend_is_plotted
    assert "One run is stored" in trend
    assert "<svg" not in trend
    # The reading is still stated, in the table, rather than withheld.
    assert len(_rows(trend)) == 1


def test_below_the_join_threshold_the_marks_are_drawn_but_never_joined():
    model = _projection_model(history=_stored_runs([0, 2, 1, 3, 2]))
    trend = _band(render_projection_body(model, Language.EN), "pk-proj-trend")

    assert model.trend_is_plotted and not model.trend_is_joined
    assert trend.count('class="pk-proj-trend-mark"') == len(model.trend) == 5
    assert 'class="pk-proj-trend-step"' not in trend
    assert f"draws a line between them at {MIN_TREND_READINGS} runs" in trend


def test_at_the_join_threshold_consecutive_days_are_joined_and_gaps_are_not():
    daily = _stored_runs([i % 4 for i in range(MIN_TREND_READINGS)])
    model = _projection_model(history=daily)
    trend = _band(render_projection_body(model, Language.EN), "pk-proj-trend")

    assert model.trend_is_joined
    assert trend.count('class="pk-proj-trend-mark"') == MIN_TREND_READINGS
    assert trend.count('class="pk-proj-trend-step"') == MIN_TREND_READINGS - 1

    # A day the pipeline did not run stays a gap: a segment across it would
    # state a value for a day that has none.
    gapped = _projection_model(
        history=_stored_runs([i % 4 for i in range(MIN_TREND_READINGS)], step=2)
    )
    gapped_trend = _band(render_projection_body(gapped, Language.EN), "pk-proj-trend")
    assert 'class="pk-proj-trend-step"' not in gapped_trend


@pytest.mark.parametrize("language", list(Language))
def test_the_trend_table_lists_every_reading_the_plot_marks(language):
    # The plot's numbers rather than a summary of them — a reader who cannot
    # use the picture is not handed a shorter, vaguer version of it.
    model = _projection_model(history=_stored_runs([0, 1] * 7))
    trend = _band(render_projection_body(model, language), "pk-proj-trend")

    assert len(_rows(trend)) == len(model.trend)
    for reading in model.trend:
        assert f'class="pk-proj-figure">{reading.government_seats}<' in trend


def test_the_dashed_majority_rule_is_drawn_inside_the_plots_own_scale():
    model = _projection_model(history=_stored_runs([0, 1] * 7))
    trend = _band(render_projection_body(model, Language.EN), "pk-proj-trend")

    y = float(re.search(r'pk-proj-trend-majority" x1="0" y1="([\d.]+)"', trend).group(1))
    marks = [float(m) for m in re.findall(r'pk-proj-trend-mark" cx="[\d.]+" cy="([\d.]+)"', trend)]
    # The Majority line is a margin of zero, and `trend_span` always contains
    # it — so the rule lands inside the same box as the marks, not off it.
    assert min(marks) - 20 <= y <= max(marks) + 20


# ── the tipping point (#50) ───────────────────────────────────────────────


@pytest.mark.parametrize("language", list(Language))
def test_the_tipping_point_names_the_seat_and_refuses_the_bellwether_reading(language):
    model = _projection_model()
    tipping = _band(render_projection_body(model, language), "pk-proj-tipping-band")

    assert model.threshold_seat is not None
    assert model.threshold_seat.name in tipping
    assert str(model.majority_threshold) in tipping
    # ADR 0005 makes this caveat load-bearing rather than decorative: without
    # it the line reads as a claim about a named constituency.
    caveat = (
        "kedudukan dalam satu susunan, bukan dakwaan"
        if language is Language.MS
        else "a position in a sort, not a claim about"
    )
    assert caveat in tipping


def test_no_empty_band_is_emitted_where_the_majority_line_falls_off_the_chamber():
    # `threshold_seat` is `None` only where the line falls outside the
    # chamber — reachable here only by putting the threshold at the chamber's
    # own size, since `0 < 112 < 222` never fails. A bordered section with
    # nothing in it would read as one that failed to load.
    model = _projection_model(majority_threshold=222)
    markup = _markup(render_projection_body(model, Language.EN))

    assert model.threshold_seat is None
    assert "pk-proj-tipping-band" not in markup
    # And no band anywhere whose whole content is empty.
    assert re.search(r'<section class="pk-proj-band[^"]*"></section>', markup) is None


# ── "Too close" (#48) and the per-state rollup (#53) ──────────────────────


@pytest.mark.parametrize("language", list(Language))
def test_too_close_lists_exactly_the_tight_seats_smallest_margin_first(language):
    model = _projection_model()
    section = _band(render_projection_body(model, language), "pk-proj-too-close")

    codes = re.findall(r'<tr data-seat="([^"]+)"', section)
    assert codes == [seat.code for seat in model.too_close_seats]
    assert len(codes) == model.government_too_close + model.opposition_too_close
    # It introduces no threshold and no cutoff of its own: every TIGHT Seat
    # is here, none of them by a judgement this section made.
    assert str(len(codes)) in section and str(model.total_seats) in section


@pytest.mark.parametrize("language", list(Language))
def test_the_state_rollup_is_one_row_per_state_and_never_a_map(language):
    model = _projection_model()
    section = _band(render_projection_body(model, language), "pk-proj-rollup")

    assert len(_rows(section)) == len(model.state_rollup)
    for row in model.state_rollup:
        assert row.state in section
    # A rollup, never a choropleth — a state's land area would dominate its
    # actual seat weight (HANDOFF's settled decision, unchanged by the change
    # of register). So: a table, and no drawing of any kind.
    assert "<svg" not in section and "<path" not in section


# ── the stress test ───────────────────────────────────────────────────────


@pytest.mark.parametrize("language", list(Language))
def test_the_stress_cells_state_the_models_own_what_if_totals(language):
    model = _projection_model()
    section = _band(render_projection_body(model, language), "pk-proj-stress")

    assert section.count("pk-proj-stress-cell") == 4
    for value in (
        model.if_every_marginal_fell,
        model.if_every_marginal_held,
        model.seats_that_must_move,
        model.state_signal_seats,
    ):
        assert f"<dd>{value}</dd>" in section


# ── the citation archive (#55) ────────────────────────────────────────────


@pytest.mark.parametrize("language", list(Language))
def test_the_permalink_the_page_prints_is_under_this_pages_own_route(language):
    # `public_page._cite_this` builds `SITE_URL + permalink` because its own
    # dated copies sit beside `public/index.html`; this page's sit beside
    # `public/projection/index.html`, and a citation link that 404s is worse
    # than no citation link at all.
    model = _projection_model()
    ms = "" if language is Language.EN else "ms/"
    expected = f"{SITE_URL}projection/{ms}{_permalink_path(model.computed_at)}"

    assert _permalink_url(model, language) == expected
    assert f'href="{expected}"' in render_projection_body(model, language)
    # Both pages state figures from this run, so both carry the provenance.
    assert f'href="{expected}"' in render_methodology_body(model, language)


@pytest.mark.parametrize("language", list(Language))
def test_cite_this_states_the_two_unfitted_constants_actually_in_force(language):
    model = _projection_model()
    body = render_projection_body(model, language)

    assert f"{model.sentiment_sensitivity:.2f}" in body
    assert f"{model.state_signal_weight:.2f}" in body


def test_main_writes_both_pages_in_both_languages_with_dated_copies(tmp_path, monkeypatch):
    # The whole #55 deliverable in one place: the link the page prints and
    # the file that answers it are built from the same `_permalink_path`, so
    # this asserts the files actually land where `_permalink_url` says.
    model = _projection_model()
    reads = []
    monkeypatch.setattr("lpa.storage.connect", lambda *a, **k: object())
    monkeypatch.setattr(
        "lpa.politikku_projection._projection_page_model",
        lambda engine: (reads.append(engine), model)[1],
    )
    projection_out = tmp_path / "projection" / PROJECTION_PAGE
    methodology_out = tmp_path / "politikku" / METHODOLOGY_PAGE
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "politikku_projection",
            "--output",
            str(projection_out),
            "--methodology-output",
            str(methodology_out),
        ],
    )

    main()

    permalink = _permalink_path(model.computed_at)
    assert projection_out.is_file()
    assert (projection_out.parent / "ms" / PROJECTION_PAGE).is_file()
    assert (projection_out.parent / permalink).is_file()
    assert (projection_out.parent / "ms" / permalink).is_file()
    assert methodology_out.is_file()
    assert (methodology_out.parent / "ms" / METHODOLOGY_PAGE).is_file()
    # The dated copy is the same run, not a second render of a later one.
    assert (projection_out.parent / permalink).read_text(encoding="utf-8") == (
        projection_out.read_text(encoding="utf-8")
    )
    # And all four pages come from one Storage read. A second read that
    # picked up a day written in between would leave the methodology page
    # citing a dated permalink whose file this run never wrote.
    assert len(reads) == 1
    assert permalink in methodology_out.read_text(encoding="utf-8")


def test_one_storage_read_stands_behind_both_languages(monkeypatch):
    # Two reads could straddle a pipeline write and publish an EN and a BM
    # page stating different days' figures under one "updated" date.
    calls = []
    model = _projection_model()

    def _read(engine):
        calls.append(engine)
        return model

    monkeypatch.setattr("lpa.politikku_projection._projection_page_model", _read)
    assert len(build_all_projection_languages(object())) == len(Language)
    assert len(build_all_methodology_languages(object())) == len(Language)
    assert len(calls) == 2  # one per page, not one per page per language


# ── the methodology page (the dead link target since #72) ─────────────────


@pytest.mark.parametrize("language", list(Language))
def test_the_methodology_page_carries_the_whole_colophon(language):
    model = _projection_model()
    page = render_methodology(model, language=language)

    for heading_en, heading_ms in (
        ("Method", "Kaedah"),
        ("Read from", "Dibaca daripada"),
        ("Election status", "Status pilihan raya"),
        ("Not calibrated", "Belum ditentukur"),
    ):
        assert (heading_ms if language is Language.MS else heading_en) in page
    assert f'href="{projection_url(language)}"' in page
    # The colophon is its own page, not a section halfway down 222 rows —
    # landing an Audience reader who clicked "how this works" there would be
    # against the reader split ADR 0011 rests on.
    markup = _markup(page)
    assert "pk-proj-seats" not in markup
    assert "pk-proj-ledger" not in markup


def test_the_methodology_page_is_what_every_politikku_footer_already_links():
    page = render_methodology(_projection_model(), language=Language.MS)

    # The BM page is served from the BM methodology route, and its own nav
    # item is the current one.
    assert f'href="{methodology_url(Language.MS)}" aria-current="page"' in page


# ── routing and register ──────────────────────────────────────────────────


@pytest.mark.parametrize("language", list(Language))
def test_the_projection_page_is_served_from_its_own_route_family(language):
    page = render_projection(_projection_model(), language=language)

    # The EN/BM toggle and the language-persistence script must both compare
    # `/projection/`, or a stored BM preference silently no-ops here.
    assert f'href="{PROJECTION_PREFIX}"' in page
    assert f'href="{PROJECTION_PREFIX}ms/"' in page
    assert "'/projection/ms/'" in page
    # Not the root family's own comparison (`POLITIKKU_PREFIX`, `/` since
    # #104) — that would silently no-op a stored BM preference here.
    assert "'/ms/'" not in page
    # One canonical URL, not two: the toggle never names `index.html`.
    assert f"{PROJECTION_PREFIX}{PROJECTION_PAGE}" not in page


def test_the_page_reads_in_politikkus_register_not_the_old_dashboards():
    # ADR 0011's whole point is that this content is redrawn, not reskinned.
    # The three things the old print register carried that PolitikKu does not.
    page = render_projection(_projection_model(), language=Language.EN)

    assert "prefers-color-scheme" not in page  # no dark mode in the shell
    assert "data-theme" not in page  # so no theme toggle either
    assert "--ph" not in page and "--bn" not in page  # no party inks
    # The seat table is the main event here, not the chamber's hidden shadow
    # (`public_page._seat_table` renders it `visually-hidden`).
    assert "visually-hidden" not in _markup(page)
    # And the things it does carry: the shell's own tokens, the band rhythm.
    assert "var(--paper-alt)" in page
    assert "var(--radius-lg)" in page


def test_the_bm_page_leaks_no_english_copy():
    model = _projection_model(history=_stored_runs([0, 1] * 7))
    en = render_projection(model, language=Language.EN)
    ms = render_projection(model, language=Language.MS)

    for sentinel in (
        "Government Coalition total",
        "Seats inside six points",
        "runs are stored",
        "A dated copy of this exact run",
        "Safest Government",
        "Model run",
    ):
        # Each sentinel is checked against the EN page first, so this cannot
        # pass by naming a sentence neither page states.
        assert sentinel in en
        assert sentinel not in ms


def test_seat_table_and_too_close_link_to_mp_profile_when_available(monkeypatch):
    from test_politikku_mp_profile import _profile

    fake_profile = _profile(seat_code="P000")
    monkeypatch.setattr("lpa.config.load_mp_profiles", lambda: {"P000": fake_profile})

    model = _projection_model()
    en_body = render_projection_body(model, Language.EN)
    ms_body = render_projection_body(model, Language.MS)

    assert '<a href="/mp/P000.html">' in en_body
    assert '<a href="/ms/mp/P000.html">' in ms_body


def test_cite_section_renders_download_buttons_in_both_languages():
    model = _projection_model()
    en_body = render_projection_body(model, Language.EN)
    ms_body = render_projection_body(model, Language.MS)

    assert '<div class="pk-proj-downloads"' in en_body
    assert (
        '<a href="/projection.csv" class="pk-button pk-button-outline">Download CSV</a>' in en_body
    )
    assert (
        '<a href="/projection.json" class="pk-button pk-button-outline">Download JSON</a>'
        in en_body
    )

    assert '<div class="pk-proj-downloads"' in ms_body
    assert (
        '<a href="/projection.csv" class="pk-button pk-button-outline">Muat turun CSV</a>'
        in ms_body
    )
    assert (
        '<a href="/projection.json" class="pk-button pk-button-outline">Muat turun JSON</a>'
        in ms_body
    )
