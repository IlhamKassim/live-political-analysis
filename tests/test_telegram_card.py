"""The Telegram post cards' PNG render (#40) — checked for real image
output, not just that it doesn't crash. `card_model`'s own arithmetic is
already covered in test_seat_call_card.py; this file only tests the raster
step (and, for the aggregate card, `election_status_aggregate_model`'s own
copy-selection logic, which has no other test coverage).
"""

from datetime import date
from io import BytesIO

from PIL import Image
from pytest import raises

from lpa.domain import ElectionStatus, SeatBaseline, SeatCall
from lpa.return_trigger import ElectionStatusTriggerKind
from lpa.seat_call_card import CardModel, card_model
from lpa.telegram_card import (
    AGGREGATE_CARD_H,
    CARD_SIZE,
    AggregateCardModel,
    election_status_aggregate_model,
    render_aggregate_card_png,
    render_seat_card_png,
)

PH = "PH"
PN = "PN"
NAMES = {PH: "Pakatan Harapan", PN: "Perikatan Nasional"}


def seat(code: str, name: str, state: str, **votes: float) -> SeatBaseline:
    return SeatBaseline(code=code, name=name, state=state, vote_share=votes)


def holding_model(*, margin: float = 0.034) -> CardModel:
    s = seat("P.100", "Bandar", "Selangor", PH=0.53, PN=0.47)
    return card_model(SeatCall(code="P.100", coalition=PH, margin=margin), s, NAMES)


def flip_model(*, margin: float = 0.05, name: str = "Luar") -> CardModel:
    s = seat("P.101", name, "Selangor", PH=0.56, PN=0.44)
    return card_model(SeatCall(code="P.101", coalition=PN, margin=margin), s, NAMES)


def test_the_render_is_a_real_png_at_the_cards_real_size():
    png = render_seat_card_png(holding_model())

    img = Image.open(BytesIO(png))
    assert img.format == "PNG"
    assert img.size == (CARD_SIZE, CARD_SIZE)


def test_every_tier_renders_without_crashing():
    for margin in (0.034, 0.09, 0.15):  # TIGHT, LIKELY, SAFE
        png = render_seat_card_png(holding_model(margin=margin))
        assert Image.open(BytesIO(png)).size == (CARD_SIZE, CARD_SIZE)


def test_a_flipped_seat_renders_without_crashing():
    png = render_seat_card_png(flip_model())
    assert Image.open(BytesIO(png)).size == (CARD_SIZE, CARD_SIZE)


def test_a_long_seat_name_that_forces_note_wrapping_still_renders():
    # wrap_text breaks the note/footnote across lines — a name long enough
    # to push the note past one line must not throw off the layout.
    model = flip_model(name="Tanjung Bunga Selatan Timur")
    png = render_seat_card_png(model)

    assert Image.open(BytesIO(png)).size == (CARD_SIZE, CARD_SIZE)


def test_the_font_dir_raises_a_clear_error_when_dejavu_is_missing(monkeypatch):
    from lpa import telegram_card

    monkeypatch.setattr(telegram_card, "_DEJAVU_CANDIDATES", ())

    with raises(SystemExit, match="fonts-dejavu-core"):
        telegram_card._font_dir()


# ── the aggregate card (Sample C) ────────────────────────────────────────

DEADLINE = date(2028, 2, 17)


def status(**overrides) -> ElectionStatus:
    defaults = {"constitutional_deadline": DEADLINE, "source": "x"}
    defaults.update(overrides)
    return ElectionStatus(**defaults)


def test_election_status_aggregate_model_uses_the_approved_called_copy():
    called = status(dissolved_on=date(2026, 8, 14))
    model = election_status_aggregate_model(
        ElectionStatusTriggerKind.CALLED,
        called,
        government_seats=118,
        total_seats=222,
        majority_threshold=112,
    )

    assert model.headline == "GE16 has been called."
    assert "not been set yet" in model.gloss
    assert model.dissolved_on == date(2026, 8, 14)
    assert model.nomination_date is None
    assert model.polling_date is None


def test_election_status_aggregate_model_states_the_polling_date():
    dated = status(
        dissolved_on=date(2026, 8, 14),
        nomination_date=date(2026, 9, 5),
        polling_date=date(2026, 9, 20),
    )
    model = election_status_aggregate_model(
        ElectionStatusTriggerKind.POLLING_DATE_SET,
        dated,
        government_seats=118,
        total_seats=222,
        majority_threshold=112,
    )

    assert model.headline == "Polling day is 20 September 2026."
    assert model.nomination_date == date(2026, 9, 5)
    assert model.polling_date == date(2026, 9, 20)


def test_the_aggregate_render_is_a_real_png_at_the_cards_real_size():
    called = status(dissolved_on=date(2026, 8, 14))
    model = election_status_aggregate_model(
        ElectionStatusTriggerKind.CALLED,
        called,
        government_seats=118,
        total_seats=222,
        majority_threshold=112,
    )
    png = render_aggregate_card_png(model)

    img = Image.open(BytesIO(png))
    assert img.format == "PNG"
    assert img.size == (CARD_SIZE, AGGREGATE_CARD_H)


def test_the_aggregate_card_renders_with_all_three_timeline_stops_unknown():
    # Defensive: election_status_aggregate_model only ever calls with a real
    # dissolution (the trigger cannot fire otherwise), but the renderer
    # itself must not crash if reused with no date known at all.
    model = AggregateCardModel(
        eyebrow="Election Status · GE16",
        headline="Testing a headline",
        gloss="Testing a gloss",
        caption="Testing a caption.",
        dissolved_on=None,
        nomination_date=None,
        polling_date=None,
        government_seats=1,
        total_seats=222,
        majority_threshold=112,
    )
    png = render_aggregate_card_png(model)

    assert Image.open(BytesIO(png)).size == (CARD_SIZE, AGGREGATE_CARD_H)


def test_the_aggregate_card_renders_with_all_three_timeline_stops_known():
    model = AggregateCardModel(
        eyebrow="Election Status · GE16",
        headline="Polling day is 20 September 2026.",
        gloss="the Election Commission has set the date",
        caption="Testing a caption.",
        dissolved_on=date(2026, 8, 14),
        nomination_date=date(2026, 9, 5),
        polling_date=date(2026, 9, 20),
        government_seats=118,
        total_seats=222,
        majority_threshold=112,
    )
    png = render_aggregate_card_png(model)

    assert Image.open(BytesIO(png)).size == (CARD_SIZE, AGGREGATE_CARD_H)


def test_a_long_headline_gloss_and_caption_that_force_wrapping_still_render():
    model = AggregateCardModel(
        eyebrow="Election Status · GE16",
        headline="Testing a much longer headline that should wrap across two lines",
        gloss="a longer gloss sentence to check wrapping behaves reasonably across the available width",
        caption=(
            "A caption sentence long enough to wrap across two full lines to "
            "check the footer spacing still holds up cleanly without overlap."
        ),
        dissolved_on=None,
        nomination_date=None,
        polling_date=None,
        government_seats=1,
        total_seats=222,
        majority_threshold=112,
    )
    png = render_aggregate_card_png(model)

    assert Image.open(BytesIO(png)).size == (CARD_SIZE, AGGREGATE_CARD_H)
