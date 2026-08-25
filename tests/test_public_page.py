"""What the public page states, tested away from how it looks.

`page_model` does every piece of arithmetic the page claims, so this file is
about numbers and ordering. The markup is covered only where a rendering bug
would put a wrong claim on the page — an unescaped Seat name, or a figure that
disagrees with the model it came from.
"""

import re
from datetime import date, timedelta

from fixtures import (
    BN,
    GPS,
    PH,
    PN,
    government_config,
    one_seat_with_a_small_third_coalition,
    three_coalition_seats,
    two_coalition_seats,
    two_state_seats,
)
from pytest import approx, raises

from lpa.aggregate import AggregatedSentiment
from lpa.domain import ElectionStatus, Projection, SeatBaseline, SeatCall, StateElectionSignal
from lpa.public_page import (
    MIN_TREND_READINGS,
    SITE_URL,
    TIER_LABEL,
    TREND_MIN_SPAN,
    TREND_PAD_Y,
    TREND_VIEW_H,
    TREND_WINDOW_DAYS,
    ChamberSeat,
    Tier,
    _permalink_path,
    _search_blob,
    _slots,
    _trend_marks,
    lede,
    page_model,
    render_html,
    status_sentence,
    tier_for,
)
from lpa.swing_model import state_swing, swing_model

NOT_CALLED = ElectionStatus(
    constitutional_deadline=date(2028, 2, 17),
    source="https://www.parlimen.gov.my/",
)


def model_for(baseline=None, scores=None, config=None, **overrides):
    """A PageModel over the fixture Baseline, via the real Swing Model.

    `scores` is the per-Coalition Sentiment the Swing Model consumes; the
    `sentiment` the page takes is the stored `AggregatedSentiment`, and the two
    are different things, so they are not both called sentiment here.
    """
    baseline = baseline if baseline is not None else two_coalition_seats()
    config = config or government_config()
    projection = swing_model(baseline, scores or {}, [], config, date(2026, 8, 6))
    settings = {
        "projection": projection,
        "baseline": baseline,
        "status": NOT_CALLED,
        "config": config,
        "names": {PH: "Pakatan Harapan", PN: "Perikatan Nasional"},
        "sentiment": AggregatedSentiment(
            scores={},
            article_counts={},
            total_articles=12,
            sources=["Free Malaysia Today"],
        ),
        "state_election_signals": [],
        "total_seats": len(baseline),
        "state_swing": {},
    }
    settings.update(overrides)
    return page_model(**settings)


def test_a_margin_lands_in_the_band_its_size_puts_it_in():
    # The boundaries are the interesting part: six and twelve points belong to
    # the safer band, so a Seat is only "too close" if it is genuinely under.
    assert tier_for(0.0) == Tier.TIGHT
    assert tier_for(0.0599) == Tier.TIGHT
    assert tier_for(0.06) == Tier.LIKELY
    assert tier_for(0.1199) == Tier.LIKELY
    assert tier_for(0.12) == Tier.SAFE


def test_the_chamber_runs_safest_government_to_safest_opposition():
    # PH holds four at 20, 10, 6 and 4 points; PN holds two at 10 and 30. The
    # Government block therefore descends to its marginals at the centre, and
    # the Opposition climbs away from the centre — so the two most marginal
    # Seats on the page sit next to each other, which is the contest.
    model = model_for()

    assert [s.code for s in model.seats] == [
        "P001",
        "P002",
        "P003",
        "P004",  # PH, 20 → 4 points
        "P005",
        "P006",  # PN, 10 → 30 points
    ]
    assert [s.government for s in model.seats] == [True] * 4 + [False] * 2
    assert model.seats[0].margin == approx(0.20)
    assert model.seats[-1].margin == approx(0.30)


def test_a_government_seat_is_never_placed_after_an_opposition_one():
    # The Majority line is drawn at the threshold-th seat, so the block only
    # overruns it if the whole Government side comes first. A safe Opposition
    # Seat must not sort ahead of a marginal Government one.
    model = model_for(
        baseline=three_coalition_seats(),
        scores={PH: -0.6, PN: 0.6},
        config=government_config(government_coalitions=frozenset({PH, BN}), majority_threshold=6),
    )

    sides = [s.government for s in model.seats]
    assert sides == sorted(sides, reverse=True)
    assert sum(sides) == model.government_seats


def test_the_ledger_puts_the_government_first_and_drops_the_empty_rows():
    model = model_for()

    assert [(row.coalition, row.projected, row.baseline) for row in model.ledger] == [
        (PH, 4, 4),
        (PN, 2, 2),
    ]
    assert [row.government for row in model.ledger] == [True, False]
    assert [row.swing for row in model.ledger] == [0, 0]


def test_a_coalition_that_stood_and_holds_nothing_either_way_is_not_a_row():
    # The Swing Model tallies every Coalition that stood anywhere, so GPS is
    # in the totals on zero. A row of 0 against 0 is noise.
    model = model_for()

    assert GPS not in {row.coalition for row in model.ledger}


def test_the_stress_numbers_are_the_buffer_worked_both_ways():
    # PH holds four: 20, 10, 6 and 4 points, so one (P004, at 4) is inside six.
    # PN's two are at 10 and 30, so neither is. Threshold is 4.
    model = model_for()

    assert model.government_seats == 4
    assert model.buffer == 0
    assert model.government_majority is True
    assert model.government_too_close == 1
    assert model.opposition_too_close == 0
    assert model.if_every_marginal_fell == 3
    assert model.if_every_marginal_held == 4
    assert model.seats_that_must_move == 1


def test_a_government_short_of_a_majority_reports_a_negative_buffer():
    # Sensitivity 0.10 turns a -0.6/+0.6 Sentiment split into a 12pp gap, so
    # every PH seat but P001 (which led by 20) falls. One Seat against a bar
    # of four.
    model = model_for(scores={PH: -0.6, PN: 0.6})

    assert model.government_seats == 1
    assert model.buffer == -3
    assert model.government_majority is False
    # Nothing has to move for a Majority that is not held to be lost.
    assert model.seats_that_must_move == 0
    assert "<b>3 seats short</b>" in lede(model)


def test_the_lede_says_what_losing_every_marginal_would_do():
    # PH holds exactly the four it needs, and one of them is inside six
    # points — so the buffer sentence and the stress sentence disagree, which
    # is the case the lede exists to make plain rather than smooth over.
    model = model_for()

    text = lede(model)
    assert "<b>exactly to a Majority</b>" in text
    assert ">1</span> of the Seats it holds is inside six points" in text
    assert "losing every one would take it 1 below the line" in text


def test_the_lede_says_so_when_a_buffer_survives_its_marginals():
    # PH holds five of these ten against a bar of three, one of them by five
    # points. Losing that one still leaves four, a seat clear.
    model = model_for(
        baseline=three_coalition_seats(),
        config=government_config(majority_threshold=3),
    )

    assert (model.government_seats, model.government_too_close) == (5, 1)
    assert "would still hold a Majority, leaving it 1 clear" in lede(model)


def test_the_lede_notes_when_nothing_the_government_holds_is_marginal():
    # A 4pp swing towards PH leaves its four Seats on 24, 14, 10 and 8 points.
    model = model_for(scores={PH: 0.2, PN: -0.2})

    assert model.government_too_close == 0
    assert "Not one of the Seats it holds is inside six points" in lede(model)


def test_a_projection_with_no_seat_calls_is_refused_rather_than_drawn_empty():
    # Storage returns every day but the newest with no Seat Calls (ADR 0005).
    # Rendering that would put an empty chamber on the page, which reads as a
    # result rather than as a page built from the wrong row.
    empty = Projection(
        coalition_seat_totals={PH: 4, PN: 2},
        government_majority=True,
        computed_at=date(2026, 8, 6),
    )

    with raises(ValueError, match="no Seat Calls"):
        model_for(projection=empty)


def test_a_call_for_a_seat_the_baseline_does_not_have_is_an_error():
    # It cannot be placed in the chamber or named, and the Swing Model derives
    # its calls from the Baseline, so it means the two were read out of step.
    stray = Projection(
        coalition_seat_totals={PH: 1},
        government_majority=False,
        computed_at=date(2026, 8, 6),
        seat_calls=(SeatCall(code="P999", coalition=PH, margin=0.2),),
    )

    with raises(ValueError, match="P999"):
        model_for(projection=stray)


def test_every_seat_gets_a_place_in_the_chamber():
    # The rows are apportioned by arc length and the remainder pushed around
    # row by row, so the count is worth pinning at the real size as well as a
    # small one.
    assert len(_slots(222)) == 222
    assert len(_slots(6)) == 6
    assert all(count >= 1 for count in (len(_slots(n)) for n in (10, 99, 222)))


def test_the_three_election_statuses_each_get_their_own_sentence():
    assert "has not been called" in status_sentence(NOT_CALLED)

    called = ElectionStatus(
        constitutional_deadline=date(2028, 2, 17),
        source="x",
        dissolved_on=date(2026, 10, 1),
    )
    assert "has been called" in status_sentence(called)
    assert "not yet announced a polling day" in status_sentence(called)

    dated = ElectionStatus(
        constitutional_deadline=date(2028, 2, 17),
        source="x",
        dissolved_on=date(2026, 10, 1),
        polling_date=date(2026, 11, 8),
    )
    assert "polling is on 8 November 2026" in status_sentence(dated)


def test_the_page_states_the_same_totals_the_model_computed():
    model = model_for()
    page = render_html(model)

    assert f">{model.government_seats}</span>" in page
    assert f"of {model.total_seats} seats" in page
    # One dot per Seat and no more — the mockup invented its chamber from a
    # hardcoded bloc table, and the whole point of this renderer is that it
    # cannot draw a seat Storage did not give it.
    assert page.count('class="seat-dot"') == len(model.seats)


def test_the_page_carries_open_graph_and_twitter_card_tags():
    # #41: a link pasted into WhatsApp/X should preview as something, not a
    # bare URL — confirmed there were no og:*/twitter:* tags at all before.
    model = model_for()
    page = render_html(model)

    assert 'property="og:title" content="GE16 Projection' in page
    assert (
        'property="og:url" content="https://ilhamkassim.github.io/live-political-analysis/"' in page
    )
    assert (
        'property="og:image" content="https://ilhamkassim.github.io/live-political-analysis/og-image.png"'
        in page
    )
    assert 'name="twitter:card" content="summary_large_image"' in page
    assert (
        'name="twitter:image" content="https://ilhamkassim.github.io/live-political-analysis/og-image.png"'
        in page
    )
    # Reuses the existing description copy rather than inventing new prose.
    description_meta = re.search(r'name="description" content="([^"]+)"', page)
    og_description_meta = re.search(r'property="og:description" content="([^"]+)"', page)
    assert description_meta.group(1) == og_description_meta.group(1)


def test_the_stylesheet_carries_a_print_block_that_hides_the_theme_toggle():
    # #49: a real browser print should render the register-a page as a clean
    # one-pager, not whatever the screen layout produces (HANDOFF's "print,
    # not dashboard" register was a metaphor before this — no @media print
    # existed at all).
    page = render_html(model_for())

    assert "@media print" in page
    print_block = page[page.index("@media print") :]
    assert ".theme-btn { display: none; }" in print_block
    assert "print-color-adjust: exact" in print_block
    # Printed paper is light with dark ink regardless of which theme was on
    # screen — the print block must force the light palette even where the
    # dark theme was explicitly selected (`data-theme="dark"`), not only the
    # system-preference case.
    assert ':root[data-theme="dark"]' in print_block
    assert "--ground:    #E9EAE4;" in print_block


def test_a_seat_name_carrying_markup_cannot_break_out_of_its_tooltip():
    # Seat names come from an ingested dataset, not from this repo.
    baseline = two_coalition_seats()
    baseline[0] = type(baseline[0])(
        code=baseline[0].code,
        name='Bagan <script>alert("x")</script>',
        state=baseline[0].state,
        vote_share=baseline[0].vote_share,
    )

    page = render_html(model_for(baseline=baseline))

    assert "<script>alert" not in page
    assert "&lt;script&gt;" in page


def test_the_government_total_row_states_no_ge15_figure():
    # The Government Coalition did not contest GE15 — it formed by agreement
    # afterwards. The mockup's "Government total 141" was called out as
    # fabricated, but the objection was categorical, so recomputing it would
    # have missed the point. Each member Coalition's own GE15 result stays.
    page = render_html(model_for())

    total_row = page.split('<tr class="gov-row">')[1].split("</tr>")[0]
    cells = re.findall(r"<td[^>]*>(.*?)</td>", total_row, re.DOTALL)
    assert "Government total" in cells[0]
    assert cells[1] == "4"  # projected
    assert cells[2] == "—" and cells[3] == "—"  # GE15 and Swing: not applicable
    assert cells[4] == "1"  # too close
    # The member Coalitions keep their own GE15 results, which are real.
    assert ">Pakatan Harapan " in page


def test_the_page_does_not_claim_a_calibration_it_never_reads():
    # `page_model` takes no PollCalibration and Storage is never asked for
    # one, so prose saying the figures were checked against Merdeka Center
    # would be an unbacked claim sitting a column from the "Not calibrated"
    # caveat.
    page = render_html(model_for())

    assert "Merdeka" not in page
    assert "Not calibrated" in page


def test_the_sources_are_what_the_latest_run_actually_read():
    # Not the outlets the Scraper was pointed at: one refused by robots.txt or
    # answering 500 contributed nothing and must not be credited (#16).
    model = model_for(
        sentiment=AggregatedSentiment(
            scores={},
            article_counts={},
            total_articles=91,
            sources=["Free Malaysia Today", "Utusan Malaysia"],
        )
    )

    assert model.sources == ("Free Malaysia Today", "Utusan Malaysia")
    assert model.article_count == 91
    assert "Free Malaysia Today · Utusan Malaysia" in render_html(model)


def test_a_storage_with_no_sentiment_snapshot_still_renders():
    # A hand-seeded database can hold a Projection and no Sentiment.
    model = model_for(sentiment=None)

    assert model.sources == ()
    assert model.article_count == 0
    assert "No outlets read" in render_html(model)


def test_the_mobile_bar_segments_follow_the_ledger_order():
    # The bar is the sub-600px fallback for the hemicycle (HANDOFF defect 4)
    # and is deliberately bloc-ordered rather than margin-ordered, reusing the
    # ledger's own order — Government Coalitions first, each side strongest
    # first — so it reads the same as the ledger sitting beneath it.
    model = model_for()
    page = render_html(model)

    titles = re.findall(r'class="bar-seg"[^>]*title="([^"]+)"', page)
    names = [t.split(" — ")[0] for t in titles]
    assert names == [row.name for row in model.ledger if row.projected]


def test_the_mobile_bar_marks_the_majority_at_the_threshold_seat():
    # The whole point of the hero is the Government block overrunning the
    # Majority line as a visible distance; the bar has to carry that too.
    model = model_for()
    page = render_html(model)

    tick = re.search(r'class="seat-bar-tick" style="left:([\d.]+)%"', page)
    assert tick is not None
    assert float(tick.group(1)) == approx(
        100 * model.majority_threshold / model.total_seats, abs=1e-3
    )


def test_the_narrow_caption_does_not_repeat_the_wide_orderings_claim():
    # The desktop caption promises safest-Government to safest-Non-government,
    # which is false of a bloc-ordered bar. HANDOFF defect 4 is explicit that
    # the narrow layout needs its own caption and the desktop one must not
    # leak into it.
    page = render_html(model_for())

    assert 'class="chamber-caption-wide"' in page
    narrow = page.split('class="chamber-caption-narrow"')[1].split("</p>")[0]
    assert "safest" not in narrow.lower()


def test_the_narrow_ledger_states_the_same_figures_as_the_table():
    # At 375px the wide table is hidden entirely (HANDOFF defect 4 measured
    # 205px of its columns off-screen); the stacked layout is what a phone
    # reader actually sees, so it has to carry the same numbers, not just the
    # names. Each row is found by its own Coalition code, which is real
    # markup the page needs anyway rather than a hook added only for this.
    model = model_for(scores={PH: -0.6, PN: 0.6})
    page = render_html(model)

    narrow = page.split('<div class="ledger-narrow">')[1].split('<dl class="stress">')[0]
    by_code = {}
    for block in narrow.split('<div class="ledger-stack-row')[1:]:
        code = re.search(r"<small>([^<]+)</small>", block)
        by_code[code.group(1) if code else "__government__"] = block

    for row in model.ledger:
        dds = re.findall(r"<dd[^>]*>(.*?)</dd>", by_code[row.coalition], re.DOTALL)
        assert dds[0] == str(row.baseline)
        assert dds[2] == str(row.too_close)

    gov = by_code["__government__"]
    assert f'<span class="seats-cell">{model.government_seats}</span>' in gov
    assert re.findall(r"<dd[^>]*>(.*?)</dd>", gov, re.DOTALL)[2] == str(model.government_too_close)


def test_the_hidden_seat_table_lists_every_seat():
    # The dots' detail lives in a hover title only, which keyboard and touch
    # users cannot reach (HANDOFF defect 5) — and once the chamber becomes a
    # bar below 600px, this table is the only place a Seat's own call is
    # reachable at all.
    model = model_for()
    page = render_html(model)

    table = page.split('<table class="visually-hidden seat-table">')[1].split("</table>")[0]
    body = table.split("<tbody>")[1]
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.DOTALL)
    assert len(rows) == len(model.seats)
    first = model.seats[0]
    assert first.name in rows[0]
    assert first.coalition in rows[0]
    # The prose, not the CSS-facing enum value — a reader leaning on this
    # table because they cannot see the `.key` legend needs "Too close", not
    # the internal token "tight" (HANDOFF defect 5; code review 9 Aug 2026).
    assert TIER_LABEL[first.tier] in rows[0]


def test_every_seat_row_carries_a_stable_id_a_shared_card_can_link_to():
    # #42: a Seat Call card (#23) or Telegram post (#40) naming a Seat should
    # be able to link to index.html#seat-{code} and land somewhere a
    # keyboard/screen-reader user can actually use — the hidden table, not
    # just a visual dot in the chamber.
    model = model_for()
    page = render_html(model)

    for seat in model.seats:
        assert f'<tr id="seat-{seat.code}"' in page
    # One id per Seat, no collisions across the 222 rows.
    ids = re.findall(r'<tr id="(seat-[^"]+)"', page)
    assert len(ids) == len(set(ids)) == len(model.seats)


def test_the_chamber_dot_carries_a_data_seat_attribute_not_a_duplicate_id():
    # An `id` may only anchor one element per document, and the hidden table
    # row is the one a fragment link should resolve to (see above) — so the
    # chamber's own dot for the same Seat carries `data-seat` instead, never
    # a second `id="seat-{code}"`.
    model = model_for()
    page = render_html(model)

    for seat in model.seats:
        assert f'data-seat="{seat.code}"' in page
    assert page.count(f'id="seat-{model.seats[0].code}"') == 1


def test_the_search_blob_carries_every_field_47_asks_a_reader_search_by():
    # #47: "by Seat name, code, state, Coalition, or certainty tier" — both
    # the Coalition's short code and its full name, so "PH" and "Pakatan
    # Harapan" both find the same Seats.
    seat = ChamberSeat(
        code="P.048",
        name="Bagan",
        state="Penang",
        coalition=PH,
        margin=0.12,
        tier=Tier.SAFE,
        government=True,
    )
    blob = _search_blob(seat, {PH: "Pakatan Harapan"})

    assert blob == "bagan p.048 penang ph pakatan harapan safe"


def test_the_search_blob_falls_back_to_the_code_for_an_unknown_coalition():
    # Every Coalition a Seat can carry comes from the same ledger this blob
    # is built from, so this path should not be reachable in practice — but
    # falling back rather than raising keeps a bad lookup from taking the
    # whole page down.
    seat = ChamberSeat(
        code="P.001",
        name="X",
        state="Y",
        coalition="ZZ",
        margin=0.1,
        tier=Tier.LIKELY,
        government=False,
    )
    assert "zz" in _search_blob(seat, {})


def test_every_row_carries_a_data_search_attribute_the_script_can_read():
    model = model_for()
    page = render_html(model)

    first = model.seats[0]
    row = page[page.index(f'id="seat-{first.code}"') :].split("</tr>")[0]
    assert "data-search=" in row
    assert first.name.lower() in row.lower()
    assert first.state.lower() in row.lower()


def test_the_seat_filter_control_is_on_the_page_and_keyboard_operable():
    # #47: register-a styling, not a generic search-bar component — reuses
    # the page's existing input/label idiom rather than a new one — and it
    # must not regress the keyboard-only path #42/HANDOFF defect 5 rely on,
    # so a plain <input> with a real <label>, not a div-as-button widget.
    page = render_html(model_for())

    assert '<label for="seatFilter">' in page
    assert '<input type="search" id="seatFilter"' in page
    assert 'aria-live="polite"' in page
    assert "seatFilter" in page[page.index("<script>") :]


def test_a_seat_name_carrying_markup_cannot_break_out_of_the_hidden_table():
    baseline = two_coalition_seats()
    baseline[0] = type(baseline[0])(
        code=baseline[0].code,
        name='Bagan <script>alert("x")</script>',
        state=baseline[0].state,
        vote_share=baseline[0].vote_share,
    )
    page = render_html(model_for(baseline=baseline))

    table = page.split('<table class="visually-hidden seat-table">')[1].split("</table>")[0]
    assert "<script>alert" not in table
    assert "&lt;script&gt;" in table


def test_a_seat_name_carrying_a_quote_cannot_break_out_of_data_search():
    # #47's data-search is an attribute value, not element content — a
    # double quote in the source name needs escaping too, or it closes the
    # attribute early and the rest of the blob becomes bare markup.
    baseline = two_coalition_seats()
    baseline[0] = type(baseline[0])(
        code=baseline[0].code,
        name='Bagan" onmouseover="alert(1)',
        state=baseline[0].state,
        vote_share=baseline[0].vote_share,
    )
    page = render_html(model_for(baseline=baseline))

    table = page.split('<table class="visually-hidden seat-table">')[1].split("</table>")[0]
    assert 'onmouseover="alert' not in table
    assert "&quot;" in table


def test_the_chamber_eyebrow_carries_the_settled_bm_wording():
    # HANDOFF defect 6, settled 9 Aug 2026 with the user: BM alongside English
    # for the section eyebrows — but only the vocabulary the user actually
    # confirmed (Dewan Rakyat, unjuran). The masthead already had "Projeksi
    # Kerusi GE16" before this defect and stays as-is: "Kerusi" was never
    # confirmed, and half-swapping one word in it ("Unjuran Kerusi GE16")
    # would mix a vetted word with an unvetted one in the same phrase — the
    # exact half-right Malay this defect exists to avoid (code review 9 Aug
    # 2026). "Seat ledger — against the GE15 Baseline" has no confirmed BM
    # term either, so it stays English rather than getting an invented one.
    page = render_html(model_for())

    assert "Projeksi Kerusi GE16" in page
    assert "Unjuran Dewan Rakyat" in page.split('<div class="eyebrow">')[1]
    assert '<div class="eyebrow">Seat ledger' in page


def test_the_majority_line_carries_majoriti_in_both_the_chamber_and_the_bar():
    # "The Majority line" (HANDOFF defect 6) is the hemicycle's threshold
    # label and the narrow bar's tick label — the same claim in two places,
    # so both must say it, not just one.
    model = model_for()
    page = render_html(model)

    assert page.count(f"{model.majority_threshold} — Majority · Majoriti") == 2


def test_the_seat_key_pairs_each_tier_with_its_settled_bm_word():
    # The three confirmed words map 1:1 onto the three tiers in `.key`.
    page = render_html(model_for())

    key = page.split('<div class="key">')[1].split("</div>\n  </section>")[0]
    assert "Safe · Selamat" in key
    assert "Likely · Berkemungkinan" in key
    assert "Too close · Terlalu rapat" in key


def test_the_theme_choice_is_read_before_first_paint():
    # Read synchronously in <head>, ahead of <body>, so a returning reader
    # never sees a flash of the wrong theme while a deferred script catches up
    # (HANDOFF defect 7).
    page = render_html(model_for())

    head = page.split("<body>")[0]
    assert 'localStorage.getItem("theme")' in head


def test_choosing_a_theme_persists_it():
    page = render_html(model_for())

    assert 'localStorage.setItem("theme"' in page


def test_a_state_that_has_voted_is_counted_by_the_seats_it_moves():
    # The Swing Model applies a state result to that state's Seats only, so
    # the honest figure is how many Seats that is — not how many states voted.
    model = model_for(
        baseline=three_coalition_seats(),  # 4 Selangor, 6 Johor
        state_election_signals=[
            StateElectionSignal(state="Johor", held_on=date(2026, 7, 11), vote_share={PH: 0.4})
        ],
    )

    assert model.state_signals == (("Johor", 6),)
    assert model.state_signal_seats == 6
    assert "Johor (6)" in render_html(model)


def test_the_verdict_states_a_ge15_delta_line_per_named_coalition():
    # #44: the headline comparison a first-time visitor wants first, stated
    # plainly near the top rather than requiring the ledger table below to
    # be read and the arithmetic done by hand. "Seats" stated explicitly,
    # matching the unit the issue's own example line used.
    model = model_for()
    page = render_html(model)

    delta = page.split('<ul class="ge15-delta">')[1].split("</ul>")[0]
    assert "Pakatan Harapan: 4 seats at GE15 → 4 projected" in delta
    assert "Perikatan Nasional: 2 seats at GE15 → 2 projected" in delta


def test_the_ge15_delta_never_states_a_government_coalition_total():
    # The Government Coalition formed after GE15 by agreement — it has no
    # honest GE15 total (see _GOV_TOTAL_GE15_NOTE) — so #44's own example
    # line, which uses that aggregate, would either invent a number or state
    # the ledger's "—" a second time. Neither is "a short, plainly-worded
    # line," so the aggregate is left out of this callout's numbered lines
    # (a caveat sentence explaining the omission is allowed to name it —
    # see the note test below — just never with a number attached).
    page = render_html(model_for())

    delta = page.split('<ul class="ge15-delta">')[1].split("</ul>")[0]
    assert "Government Coalition: " not in delta


def test_the_ge15_delta_explains_the_omission_only_when_it_would_be_missed():
    # #44 code review, 20 Aug 2026: a reader following the issue's own
    # example line has real reason to expect (and miss) a Government
    # Coalition aggregate line only when that bloc actually has more than
    # one member — a single-Coalition government's own delta line already
    # is that number, so the caveat would be explaining an absence nobody
    # would have expected in the first place.
    two_party = model_for()  # government_config()'s PH + GPS
    assert len(two_party.government_coalitions) == 2
    delta = render_html(two_party).split('<ul class="ge15-delta">')[1].split("</ul>")[0]
    assert "no GE15 total to compare" in delta

    one_party = model_for(config=government_config(government_coalitions=frozenset({PH})))
    assert len(one_party.government_coalitions) == 1
    delta = render_html(one_party).split('<ul class="ge15-delta">')[1].split("</ul>")[0]
    assert "no GE15 total to compare" not in delta


def test_the_tipping_point_names_the_seat_at_the_majority_line():
    # #50: government_config()'s 4-seat bar over two_coalition_seats() puts
    # the threshold at model.seats[3] — P004, PH's 4-point marginal.
    model = model_for()
    page = render_html(model)

    assert model.threshold_seat.code == "P004"
    assert model.threshold_swing == approx(0.04)
    assert "Today, the count crosses 4 at <b>P004</b> (Selangor)" in page
    assert "A uniform swing of <b>4.0 points</b>" in page


def test_the_tipping_point_never_implies_the_seat_decides_the_election():
    # Framing decision settled on #50 itself (Phase 0, 20 Aug 2026): a
    # position in a sort, never bellwether language about one constituency
    # (ADR 0005). Pinning the forbidden phrases so a future edit cannot
    # silently reintroduce them.
    page = render_html(model_for())

    tipping = page[page.index('class="tipping-point"') :].split("</p>", 2)
    block = "".join(tipping[:2])
    assert "decides" not in block.lower()
    assert "bellwether" not in block.lower()
    assert "the one to watch" not in block.lower()
    assert "not a claim about" in block


def test_the_tipping_point_is_absent_when_the_threshold_falls_outside_the_chamber():
    # Mirrors _hemicycle's own guard: a threshold at or beyond the seat
    # count draws no line there, so this states nothing about one either.
    model = model_for(config=government_config(majority_threshold=99))

    assert model.threshold_seat is None
    assert model.threshold_swing is None
    assert '<p class="tipping-point">' not in render_html(model)


def test_the_tipping_point_is_absent_when_the_threshold_exactly_equals_the_seat_count():
    # Code review, 20 Aug 2026: threshold_seat originally guarded with
    # `<=`, disagreeing with _hemicycle's strict `<` at this exact boundary
    # — the tipping-point prose would have named a Seat on a page whose
    # chamber drew no line for it. Pinning the boundary so it cannot
    # silently drift back apart.
    model = model_for(config=government_config(majority_threshold=6))  # == len(seats)

    assert model.threshold_seat is None
    assert model.threshold_swing is None


def test_the_sensitivity_table_has_exactly_the_three_settled_rows():
    # Triage resolution on #51 (20 Aug 2026): exactly 0.05 / 0.10 / 0.20,
    # never a fourth column varying state_signal_weight too.
    model = model_for()

    assert [value for value, _ in model.sensitivity_table] == [0.05, 0.10, 0.20]


def test_the_sensitivity_table_recomputes_the_government_total_honestly():
    # Each row is a real re-run of the pure Swing Model at that sensitivity
    # (ADR 0002 — costs nothing), not a guess — the middle row (0.10, the
    # shipped value) must agree with the real Projection's own total. In
    # production (pipeline.py) both the real Projection and this table are
    # built from the same `sentiment.scores`, so the fixture wires the two
    # together the same way rather than leaving `model_for`'s default,
    # unrelated `sentiment` fixture in place.
    scores = {PH: -0.6, PN: 0.6}
    model = model_for(
        scores=scores,
        sentiment=AggregatedSentiment(
            scores=scores,
            article_counts={},
            total_articles=12,
            sources=["Free Malaysia Today"],
        ),
    )

    by_value = dict(model.sensitivity_table)
    assert by_value[0.10] == model.government_seats


def test_the_sensitivity_table_is_labelled_as_a_judgement_call_not_a_confidence_interval():
    # #51's framing risk: this must never read as sampling/statistical
    # uncertainty. Both guardrails settled in triage, reused verbatim.
    page = render_html(model_for())

    block = page[page.index('class="sensitivity"') :].split("</div>\n  </section>")[0]
    assert "Government Coalition total" in block
    assert "confidence" not in block.lower()
    assert "not a range of likely outcomes" in block


def test_the_colophon_states_article_counts_per_coalition_most_covered_first():
    # #52: counts only, next to the existing site-wide total.
    model = model_for(
        sentiment=AggregatedSentiment(
            scores={},
            article_counts={PH: 5, PN: 7},
            total_articles=12,
            sources=["Free Malaysia Today"],
        )
    )
    page = render_html(model)

    assert model.article_counts == (("Perikatan Nasional", 7), ("Pakatan Harapan", 5))
    assert "By Coalition: Perikatan Nasional 7 · Pakatan Harapan 5." in page


def test_the_colophon_omits_the_coalition_breakdown_with_no_sentiment_snapshot():
    # A hand-seeded database can have a Projection with no Sentiment
    # snapshot at all (page_model's own docstring) — nothing to break down.
    model = model_for(sentiment=None)
    page = render_html(model)

    assert model.article_counts == ()
    assert "By Coalition" not in page


def test_the_state_rollup_has_one_row_per_state_with_ge15_and_projected_totals():
    # #53: GE15 and projected Coalition totals per state, one row each,
    # alphabetical — two_state_seats()'s margins are wide enough that a 4pp
    # swing flips nothing, so GE15 and Projected should read the same.
    baseline = two_state_seats()
    scores = {PH: -0.4, PN: 0.4}
    swing_by_state = state_swing(baseline, scores, [], government_config())
    model = model_for(baseline=baseline, scores=scores, state_swing=swing_by_state)
    page = render_html(model)

    rollup = page[page.index('class="state-rollup"') :].split("</table>")[0]
    assert "Johor" in rollup
    assert "Selangor" in rollup
    # Selangor splits PH 2 / PN 2 at both GE15 and projected; Johor is PN 4,
    # 0 both — a Coalition absent from a state is omitted, not stated as 0.
    assert rollup.count("PH 2 · PN 2") == 2
    assert rollup.count("PN 4") == 2
    assert "PH 0" not in rollup


def test_the_state_rollup_states_the_swing_actually_applied():
    # #53: the real per-state Swing (#53a), not a value re-derived from the
    # Seat Calls sitting next to it on the page.
    baseline = two_state_seats()
    scores = {PH: -0.4, PN: 0.4}
    swing_by_state = state_swing(baseline, scores, [], government_config())
    model = model_for(baseline=baseline, scores=scores, state_swing=swing_by_state)
    page = render_html(model)

    rollup = page[page.index('class="state-rollup"') :].split("</table>")[0]
    assert rollup.count("PH −4.0 · PN +4.0") == 2


def test_the_state_rollup_states_an_em_dash_for_a_day_before_53a_existed():
    # A Projection stored before #53a's plumbing has no per-state Swing at
    # all — state_swing() defaults to {} rather than the render failing or
    # inventing a figure. GE15/Projected still show real totals; only the
    # Swing column is affected.
    model = model_for(state_swing={})
    page = render_html(model)

    rollup = page[page.index('class="state-rollup"') :].split("</table>")[0]
    assert "PH 4 · PN 2" in rollup  # GE15/Projected totals, unaffected
    assert "PH +" not in rollup and "PH −" not in rollup  # no swing invented
    assert "—" in rollup


def test_the_state_rollup_marks_which_state_had_a_state_election_signal():
    baseline = two_state_seats()
    signal = StateElectionSignal(
        state="Johor", held_on=date(2026, 3, 1), vote_share={PH: 0.30, PN: 0.70}
    )
    model = model_for(baseline=baseline, state_election_signals=[signal])
    page = render_html(model)

    rollup = page[page.index('class="state-rollup"') :].split("</table>")[0]
    johor_row = rollup[rollup.index("Johor") :].split("</tr>")[0]
    selangor_row = rollup[rollup.index("Selangor") :].split("</tr>")[0]
    assert "State result" in johor_row
    assert "State result" not in selangor_row


def test_a_signal_with_no_reported_vote_share_does_not_mark_a_state_active():
    # Code review, 20 Aug 2026: a StateElectionSignal with an empty
    # vote_share is legitimate per its own docstring ("may omit Coalitions
    # the result does not report," including all of them) — but it never
    # reaches _observed_state_swings' collected dict, so state_swing() falls
    # back to Sentiment alone for that state. Marking it "State result"
    # anyway would claim a state election moved a state whose Swing is, in
    # fact, pure Sentiment.
    baseline = two_state_seats()
    empty_signal = StateElectionSignal(state="Johor", held_on=date(2026, 3, 1), vote_share={})
    model = model_for(baseline=baseline, state_election_signals=[empty_signal])
    page = render_html(model)

    assert model.state_signals == ()
    rollup = page[page.index('class="state-rollup"') :].split("</table>")[0]
    johor_row = rollup[rollup.index("Johor") :].split("</tr>")[0]
    assert "State result" not in johor_row


def test_the_permalink_path_is_a_year_month_day_tree():
    # #55: e.g. public/2026/08/20.html — the daily Action publishes public/
    # wholesale, so this only needs to be a path under it.
    assert _permalink_path(date(2026, 8, 6)) == "2026/08/06.html"


def test_the_page_states_what_to_cite_and_against_which_constants():
    # #55: the model-run date, the two Swing Model constants actually in
    # force (not just that they're provisional — ADR 0003), and which
    # outlets fed News Sentiment, so a quoted figure can be checked later.
    model = model_for(config=government_config(sentiment_sensitivity=0.10, state_signal_weight=0.5))
    page = render_html(model)

    cite = page[page.index("<h3>Cite this</h3>") :].split("</div>")[0]
    assert "Model run 6 August 2026" in cite
    assert "sentiment sensitivity 0.10" in cite
    assert "state signal weight 0.50" in cite
    assert "Free Malaysia Today" in cite


def test_the_cite_this_block_links_to_the_dated_permalink():
    model = model_for()
    page = render_html(model)

    cite = page[page.index("<h3>Cite this</h3>") :].split("</div>")[0]
    assert f'href="{SITE_URL}2026/08/06.html"' in cite


def test_the_cite_this_link_shows_its_own_url_when_printed():
    # #55: a printed page can't be clicked, so the permalink it names has to
    # be legible as plain text on paper too.
    page = render_html(model_for())

    print_block = page[page.index("@media print") :]
    assert ".colophon a::after" in print_block
    assert "attr(href)" in print_block


# ── #48: the Seats already inside the tight band, listed ──────────────────


def staggered_marginals():
    """Four Selangor seats straddling the tight band's upper boundary.

    PH leads by 2, 4 and 6 points in the first three; PN leads by 10 in the
    last. Six points is `TIGHT_MARGIN` itself, which `tier_for` puts in the
    safer band — so P003 is the Seat that separates "reuses the tier" from
    "wrote its own comparison", and P001/P002 are the whole tight band.
    """
    return [
        SeatBaseline(code="P001", name="P001", state="Selangor", vote_share={PH: 0.51, PN: 0.49}),
        SeatBaseline(code="P002", name="P002", state="Selangor", vote_share={PH: 0.52, PN: 0.48}),
        SeatBaseline(code="P003", name="P003", state="Selangor", vote_share={PH: 0.53, PN: 0.47}),
        SeatBaseline(code="P004", name="P004", state="Selangor", vote_share={PN: 0.55, PH: 0.45}),
    ]


def too_close_block(page):
    """The #48 module's own markup, from its opening div to the next section."""
    return page.split('<div class="too-close">')[1].split('<div class="sensitivity">')[0]


def test_the_too_close_list_holds_the_tight_band_and_stops_at_its_boundary():
    # Hand-checked from staggered_marginals(): 2 and 4 points are inside the
    # band, 6 points is the boundary and belongs to the safer one (the same
    # boundary test_a_margin_lands_in_the_band_its_size_puts_it_in pins on
    # tier_for), 10 points is nowhere near it. Smallest margin first.
    model = model_for(baseline=staggered_marginals())

    assert [s.code for s in model.too_close_seats] == ["P001", "P002"]
    assert [s.margin for s in model.too_close_seats] == [approx(0.02), approx(0.04)]


def test_the_too_close_list_follows_tier_for_rather_than_a_bar_of_its_own(monkeypatch):
    # #48's framing risk: the module must surface the Seats the page already
    # tags at the tightest existing Tier, never define its own idea of close.
    # Moving TIGHT_MARGIN moves this list with it — a hard-coded 0.06 here
    # would leave it stuck at two Seats.
    monkeypatch.setattr("lpa.public_page.TIGHT_MARGIN", 0.11)
    model = model_for(baseline=staggered_marginals())

    assert [s.code for s in model.too_close_seats] == ["P001", "P002", "P003", "P004"]
    assert all(s.tier == Tier.TIGHT for s in model.too_close_seats)


def test_the_too_close_list_agrees_with_the_ledger_column_and_the_chamber():
    # One tier, three presentations. If this module ever counted its own
    # Seats, the page could state one number in the ledger's "Too close"
    # column and draw a different set of hollow rings above it.
    model = model_for(baseline=three_coalition_seats(), config=government_config())

    hollow = [s.code for s in model.seats if s.tier == Tier.TIGHT]
    assert sorted(s.code for s in model.too_close_seats) == sorted(hollow)
    assert sum(row.too_close for row in model.ledger) == len(model.too_close_seats)


def test_the_too_close_module_states_why_a_seat_is_listed_and_nothing_more():
    # The whole point of #48's framing-risk section: small margin is the only
    # claim on the page here. Editorial words are pinned as absent so a later
    # edit cannot reintroduce the "Seats to watch" register CONTEXT.md and
    # ADR 0005 rule out — and the arithmetic disclaimer is pinned as present,
    # in the same tone as _tipping_point's own caveat.
    block = too_close_block(render_html(model_for(baseline=staggered_marginals())))

    for word in (
        "watch",
        "key",
        "battleground",
        "important",
        "contested",
        "crucial",
        "decisive",
        "momentum",
        "bellwether",
        "race",
    ):
        assert word not in block.lower()
    assert "because of the size of its margin and nothing else" in block
    assert "not a claim about any of these Seats" in block
    assert "2 of 4 Seats are projected inside six points" in block


def test_the_count_line_inflects_the_verb_and_not_the_seats_it_counts():
    # "1 of 222 Seat is" would be the plural keyed to the numerator while
    # sitting after the denominator. One Seat inside the band is an ordinary
    # day, not an edge case: two_coalition_seats() has exactly one (P004, at
    # four points), the same count test_the_stress_numbers_are_the_buffer_
    # worked_both_ways hand-checks. lede() states it the same way.
    model = model_for()
    block = too_close_block(render_html(model))

    assert len(model.too_close_seats) == 1
    assert "1 of 6 Seats is projected inside six points" in block


def test_the_too_close_module_reuses_the_tiers_own_settled_label():
    # TIER_LABEL[Tier.TIGHT] and HANDOFF's confirmed BM word for it, not a
    # new name for the same band. Section eyebrows carry BM (HANDOFF defect
    # 6); "terlalu rapat" is one of the words settled 9 Aug 2026.
    block = too_close_block(render_html(model_for(baseline=staggered_marginals())))

    assert TIER_LABEL[Tier.TIGHT] == "Too close"
    assert "Too close · Terlalu rapat" in block


def test_each_listed_seat_is_identifiable_by_its_code():
    # #23's cards key off a Seat's code, so each row states one — as
    # data-seat, never an id: _seat_table's rows are the document's
    # fragment-link target and an id can only anchor one element.
    block = too_close_block(render_html(model_for(baseline=staggered_marginals())))

    assert 'data-seat="P001"' in block
    assert '<small class="seat-code">P001</small>' in block
    assert 'id="seat-' not in block


def test_a_listed_seat_name_carrying_markup_cannot_break_out_of_the_row():
    baseline = staggered_marginals()
    baseline[0] = type(baseline[0])(
        code=baseline[0].code,
        name='Bagan <script>alert("x")</script>',
        state=baseline[0].state,
        vote_share=baseline[0].vote_share,
    )
    block = too_close_block(render_html(model_for(baseline=baseline)))

    assert "<script>alert" not in block
    assert "&lt;script&gt;" in block


def test_the_too_close_module_says_so_plainly_when_the_band_is_empty():
    # A day on which nothing is inside six points is a real result, not a
    # reason for the section to vanish silently — the lede already states
    # the Government half of the same fact in prose.
    baseline = one_seat_with_a_small_third_coalition()
    block = too_close_block(render_html(model_for(baseline=baseline)))

    assert "No Seat is projected inside six points." in block
    assert "<table" not in block


# ── the Majority-margin trend (#45) ───────────────────────────────────────
#
# The pipeline is young, so the states worth testing are the thin ones: what
# the page does on one stored run, on a handful, and on enough to draw a line
# — and, at every count, that the picture claims no more than the readings
# support.

TREND_DAY = date(2026, 8, 6)
"""The same day `model_for`'s own Projection is computed on, so a history
ending here and the rest of the page agree about which day is today."""


def stored_runs(margins, last_day=TREND_DAY, step=1):
    """One stored Projection per margin, oldest first, `step` days apart.

    `margins` are Seats clear of `government_config`'s 4-seat Majority — PH
    is a Government Coalition there, so putting `4 + margin` Seats on it puts
    the Government Coalition exactly that far past the line.
    """
    last = len(margins) - 1
    return [
        Projection(
            coalition_seat_totals={PH: 4 + margin, PN: 2},
            government_majority=margin >= 0,
            computed_at=last_day - timedelta(days=(last - i) * step),
        )
        for i, margin in enumerate(margins)
    ]


def trend_block(page):
    """The #45 section's own markup, from its opening div to the next section."""
    return page.split('<div class="trend">')[1].split('<div class="too-close">')[0]


def test_one_stored_run_is_a_reading_and_not_a_trend():
    # A single mark alone on an axis invites the eye to read a flat line
    # through it, and there is nothing to compare it against in any case. The
    # day is stated in prose instead, with its count, and no plot is drawn.
    model = model_for()
    block = trend_block(render_html(model))

    assert len(model.trend) == 1
    assert not model.trend_is_plotted
    assert "One run is stored, 6 August 2026" in block
    assert "<svg" not in block
    assert "trend-mark" not in block


def test_a_days_reading_is_the_same_margin_the_rest_of_the_page_states():
    # The right-hand end of the plot and the buffer in the lede are the same
    # quantity, so they must be the same number — two paths to one figure is
    # how a chart comes to disagree with the prose above it.
    model = model_for()

    assert model.trend[-1].margin == model.buffer
    assert model.trend[-1].government_seats == model.government_seats
    assert model.trend[-1].day == model.computed_at


def test_a_few_runs_are_plotted_as_marks_and_never_joined_up():
    # Five runs is #45's own worry made concrete: enough to draw something,
    # nowhere near enough for the distance between two marks to mean more
    # than the model's noise. They are plotted — hiding them would be its own
    # dishonesty — but nothing is drawn between them.
    model = model_for(history=stored_runs([0, 2, 1, 3, 2]))
    block = trend_block(render_html(model))

    assert len(model.trend) == 5
    assert model.trend_is_plotted
    assert not model.trend_is_joined
    assert block.count('class="trend-mark"') == 5
    assert "trend-step" not in block
    assert "deliberately not joined up" in block
    assert f"draws a line between them at {MIN_TREND_READINGS} runs" in block


def test_enough_runs_are_joined_but_only_between_consecutive_days():
    # At MIN_TREND_READINGS the marks are joined. Straight segments between
    # adjacent days, one fewer than there are readings — no curve, no spline,
    # and nothing that would put a value on a day between two runs.
    margins = [i % 4 for i in range(MIN_TREND_READINGS)]
    model = model_for(history=stored_runs(margins))
    block = trend_block(render_html(model))

    assert len(model.trend) == MIN_TREND_READINGS
    assert model.trend_is_joined
    assert block.count('class="trend-mark"') == MIN_TREND_READINGS
    assert block.count('class="trend-step"') == MIN_TREND_READINGS - 1
    assert "consecutive days" in block
    # The one drawing primitive that would imply a value the model never
    # produced. Segments are <line>s; a path with curve commands is not.
    assert "<path" not in block


def test_a_day_the_pipeline_missed_is_left_as_a_gap_in_the_line():
    # The honesty rule the joined state turns on: a segment across a missing
    # day would state a margin for a day that has no reading. Seven runs are
    # daily, then a four-day hole, then eight more — so exactly one join is
    # missing from the run of them.
    daily = stored_runs([1] * 7, last_day=TREND_DAY - timedelta(days=11))
    later = stored_runs([2] * 8)
    model = model_for(history=daily + later)
    block = trend_block(render_html(model))

    assert len(model.trend) == 15
    assert model.trend_is_joined
    assert block.count('class="trend-step"') == 13  # 14 adjacencies, one a gap
    assert "a gap in the line is a day the pipeline did not run" in block


def test_the_marks_sit_where_the_dates_are_and_not_where_the_readings_are():
    # Evenly spacing readings by index would close up the same missing week
    # the segment rule leaves open — an eight-day gap drawn as one day apart.
    # The middle run here is one day after the first and eight days before
    # the last, so its mark belongs near the left, not at the halfway point.
    model = model_for(
        history=stored_runs([0, 1], last_day=TREND_DAY - timedelta(days=8)) + stored_runs([2])
    )
    marks = _trend_marks(model)

    assert [reading.day.day for reading in model.trend] == [28, 29, 6]
    across = (marks[1][0] - marks[0][0]) / (marks[2][0] - marks[0][0])
    assert across == approx(1 / 9)


def test_a_quiet_run_of_days_is_drawn_as_a_quiet_run_of_days():
    # Scaled to its own data a fortnight sitting between +8 and +9 would fill
    # the box top to bottom and read as a dramatic swing. The scale never
    # covers fewer than TREND_MIN_SPAN Seats, so one Seat of movement is
    # drawn as one Seat of movement.
    model = model_for(history=stored_runs([8, 9] * 7))
    low, high = model.trend_span
    marks = _trend_marks(model)

    assert high - low >= TREND_MIN_SPAN
    # One Seat of movement over a scale that wide is a small fraction of the
    # plot's height, not most of it.
    height = max(y for _, y in marks) - min(y for _, y in marks)
    assert height < 0.12 * (TREND_VIEW_H - 2 * TREND_PAD_Y)


def test_a_scale_always_contains_the_majority_line_it_is_measured_from():
    # A margin is a distance from the Majority line, so a plot of margins
    # that cropped the line out would be a picture of a quantity with its
    # own zero off-screen.
    for margins in ([20, 22, 21], [-15, -14, -16], [0, 1, -1]):
        low, high = model_for(history=stored_runs(margins)).trend_span
        assert low <= 0 <= high


def test_every_reading_on_one_margin_renders_flat_rather_than_failing():
    # The likeliest shape a young pipeline actually produces: nothing moved.
    # The value span goes to zero, and it may not divide.
    model = model_for(history=stored_runs([3] * 5))
    marks = _trend_marks(model)
    block = trend_block(render_html(model))

    assert len({round(y, 6) for _, y in marks}) == 1
    assert block.count('class="trend-mark"') == 5


def test_how_thin_the_history_is_can_never_be_read_off_the_plot_alone():
    # #45's framing risk in one line: the count is in the copy in every
    # state, so nobody reads the picture without knowing how many runs made
    # it.
    for margins, stated in (
        ([0], "One run is stored"),
        ([0, 1], "2 runs"),
        ([0, 1] * 7, "14 runs"),
    ):
        block = trend_block(render_html(model_for(history=stored_runs(margins))))
        assert stated in block


def test_the_plot_never_claims_the_move_is_a_measurement_of_opinion():
    # ADR 0003's caveat, stated on the section itself rather than left to the
    # colophon: a trend line is exactly the visual that reads as more
    # confident than two unfitted constants can support.
    block = trend_block(render_html(model_for(history=stored_runs([0, 1] * 7))))

    assert "not a measurement of opinion changing" in block
    assert "ADR 0003" in block


def test_readings_older_than_the_window_are_not_plotted():
    # Not lost — Storage keeps them and the dated permalinks state them. A
    # plot that grew without bound would eventually squash a year of runs
    # into six hundred pixels.
    inside = stored_runs([1, 2, 3])
    outside = stored_runs([9], last_day=TREND_DAY - timedelta(days=TREND_WINDOW_DAYS + 1))
    model = model_for(history=outside + inside)

    assert [reading.margin for reading in model.trend] == [1, 2, 3]


def test_a_day_stored_twice_is_one_mark_and_not_a_vertical_jump():
    # A re-run writes a second row for a day already written. Two marks on
    # one date would draw a jump that never happened.
    runs = stored_runs([1, 2])
    again = Projection(
        coalition_seat_totals={PH: 7, PN: 2},
        government_majority=True,
        computed_at=runs[-1].computed_at,
    )
    model = model_for(history=[*runs, again])

    assert [(r.day.day, r.margin) for r in model.trend] == [(5, 1), (6, 3)]


def test_the_margin_counts_todays_government_coalitions_on_every_stored_day():
    # Which Coalitions form the government is config that can change under a
    # stored day (domain.government_seat_total's own reason for existing).
    # Re-deriving is what keeps every mark counting the same Coalitions as
    # the figure in the lede.
    history = stored_runs([1, 2])
    model = model_for(
        history=history,
        config=government_config(government_coalitions=frozenset({PH, PN})),
    )

    # PH 5 + PN 2, then PH 6 + PN 2, against the same 4-seat line.
    assert [reading.margin for reading in model.trend] == [3, 4]


def test_the_readings_are_reachable_without_a_mouse():
    # The marks carry their date and value in a hover <title> only — the same
    # keyboard-and-touch dead end HANDOFF defect 5 found on the chamber's
    # dots. visually-hidden, never display: none.
    model = model_for(history=stored_runs([0, 5]))
    block = trend_block(render_html(model))

    assert '<table class="visually-hidden trend-table">' in block
    assert block.count("<tr>") == 3  # a header row and one per reading
    assert "6 August 2026" in block
    assert "+5" in block
