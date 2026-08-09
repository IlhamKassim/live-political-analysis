"""What the public page states, tested away from how it looks.

`page_model` does every piece of arithmetic the page claims, so this file is
about numbers and ordering. The markup is covered only where a rendering bug
would put a wrong claim on the page — an unescaped Seat name, or a figure that
disagrees with the model it came from.
"""

import re
from datetime import date

from pytest import approx, raises

from fixtures import (
    BN,
    GPS,
    PH,
    PN,
    government_config,
    three_coalition_seats,
    two_coalition_seats,
)
from lpa.aggregate import AggregatedSentiment
from lpa.domain import ElectionStatus, Projection, SeatCall, StateElectionSignal
from lpa.public_page import (
    TIER_LABEL,
    Tier,
    _slots,
    lede,
    page_model,
    render_html,
    status_sentence,
    tier_for,
)
from lpa.swing_model import swing_model

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
    projection = swing_model(
        baseline, scores or {}, [], config, date(2026, 8, 6)
    )
    settings = dict(
        projection=projection,
        baseline=baseline,
        status=NOT_CALLED,
        config=config,
        names={PH: "Pakatan Harapan", PN: "Perikatan Nasional"},
        sentiment=AggregatedSentiment(
            scores={}, article_counts={}, total_articles=12,
            sources=["Free Malaysia Today"],
        ),
        state_election_signals=[],
        total_seats=len(baseline),
    )
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
        "P001", "P002", "P003", "P004",  # PH, 20 → 4 points
        "P005", "P006",                  # PN, 10 → 30 points
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
        config=government_config(
            government_coalitions=frozenset({PH, BN}), majority_threshold=6
        ),
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
    cells = re.findall(r"<td[^>]*>(.*?)</td>", total_row, re.S)
    assert "Government total" in cells[0]
    assert cells[1] == "4"                        # projected
    assert cells[2] == "—" and cells[3] == "—"    # GE15 and Swing: not applicable
    assert cells[4] == "1"                        # too close
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
            scores={}, article_counts={}, total_articles=91,
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

    narrow = page.split('<div class="ledger-narrow">')[1].split(
        '<dl class="stress">'
    )[0]
    by_code = {}
    for block in narrow.split('<div class="ledger-stack-row')[1:]:
        code = re.search(r"<small>([^<]+)</small>", block)
        by_code[code.group(1) if code else "__government__"] = block

    for row in model.ledger:
        dds = re.findall(r"<dd[^>]*>(.*?)</dd>", by_code[row.coalition], re.S)
        assert dds[0] == str(row.baseline)
        assert dds[2] == str(row.too_close)

    gov = by_code["__government__"]
    assert f'<span class="seats-cell">{model.government_seats}</span>' in gov
    assert re.findall(r"<dd[^>]*>(.*?)</dd>", gov, re.S)[2] == str(
        model.government_too_close
    )


def test_the_hidden_seat_table_lists_every_seat():
    # The dots' detail lives in a hover title only, which keyboard and touch
    # users cannot reach (HANDOFF defect 5) — and once the chamber becomes a
    # bar below 600px, this table is the only place a Seat's own call is
    # reachable at all.
    model = model_for()
    page = render_html(model)

    table = page.split('<table class="visually-hidden seat-table">')[1].split(
        "</table>"
    )[0]
    body = table.split("<tbody>")[1]
    rows = re.findall(r"<tr>(.*?)</tr>", body, re.S)
    assert len(rows) == len(model.seats)
    first = model.seats[0]
    assert first.name in rows[0]
    assert first.coalition in rows[0]
    # The prose, not the CSS-facing enum value — a reader leaning on this
    # table because they cannot see the `.key` legend needs "Too close", not
    # the internal token "tight" (HANDOFF defect 5; code review 9 Aug 2026).
    assert TIER_LABEL[first.tier] in rows[0]


def test_a_seat_name_carrying_markup_cannot_break_out_of_the_hidden_table():
    baseline = two_coalition_seats()
    baseline[0] = type(baseline[0])(
        code=baseline[0].code,
        name='Bagan <script>alert("x")</script>',
        state=baseline[0].state,
        vote_share=baseline[0].vote_share,
    )
    page = render_html(model_for(baseline=baseline))

    table = page.split('<table class="visually-hidden seat-table">')[1].split(
        "</table>"
    )[0]
    assert "<script>alert" not in table
    assert "&lt;script&gt;" in table


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
    assert "<div class=\"eyebrow\">Seat ledger" in page


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
            StateElectionSignal(
                state="Johor", held_on=date(2026, 7, 11), vote_share={PH: 0.4}
            )
        ],
    )

    assert model.state_signals == (("Johor", 6),)
    assert model.state_signal_seats == 6
    assert "Johor (6)" in render_html(model)
