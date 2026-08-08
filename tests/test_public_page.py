"""What the public page states, tested away from how it looks.

`page_model` does every piece of arithmetic the page claims, so this file is
about numbers and ordering. The markup is covered only where a rendering bug
would put a wrong claim on the page — an unescaped Seat name, or a figure that
disagrees with the model it came from.
"""

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
from lpa.domain import ElectionStatus, Projection, SeatCall
from lpa.public_page import (
    LIKELY,
    SAFE,
    TIGHT,
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


def model_for(baseline=None, sentiment=None, config=None, **overrides):
    """A PageModel over the fixture Baseline, via the real Swing Model."""
    baseline = baseline if baseline is not None else two_coalition_seats()
    config = config or government_config()
    projection = swing_model(
        baseline, sentiment or {}, [], config, date(2026, 8, 6)
    )
    settings = dict(
        projection=projection,
        baseline=baseline,
        status=NOT_CALLED,
        config=config,
        names={PH: "Pakatan Harapan", PN: "Perikatan Nasional"},
        sources=["Free Malaysia Today"],
        article_count=12,
        state_signal_states=[],
        total_seats=len(baseline),
    )
    settings.update(overrides)
    return page_model(**settings)


def test_a_margin_lands_in_the_band_its_size_puts_it_in():
    # The boundaries are the interesting part: six and twelve points belong to
    # the safer band, so a Seat is only "too close" if it is genuinely under.
    assert tier_for(0.0) == TIGHT
    assert tier_for(0.0599) == TIGHT
    assert tier_for(0.06) == LIKELY
    assert tier_for(0.1199) == LIKELY
    assert tier_for(0.12) == SAFE


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
        sentiment={PH: -0.6, PN: 0.6},
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
    model = model_for(sentiment={PH: -0.6, PN: 0.6})

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
    model = model_for(sentiment={PH: 0.2, PN: -0.2})

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
