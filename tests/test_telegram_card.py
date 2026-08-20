"""The Seat Call card's PNG render (#40) — checked for real image output,
not just that it doesn't crash. `card_model`'s own arithmetic is already
covered in test_seat_call_card.py; this file only tests the raster step.
"""

from io import BytesIO

from PIL import Image
from pytest import raises

from lpa.domain import SeatBaseline, SeatCall
from lpa.seat_call_card import CardModel, card_model
from lpa.telegram_card import CARD_SIZE, render_seat_card_png

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
