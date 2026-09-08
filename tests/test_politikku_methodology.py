"""Tests for PolitikKu's methodology page (/methodology.html and /ms/methodology.html)."""

import re
from datetime import date

import pytest
from fixtures import PH, PN, government_config
from fixtures import seat as _seat

from lpa.domain import ElectionStatus
from lpa.politikku_methodology import (
    build_all_methodology_languages,
    render_methodology,
)
from lpa.politikku_shell import (
    Language,
    methodology_url,
    projection_url,
)
from lpa.public_page import PageModel, page_model
from lpa.swing_model import swing_model

NOT_CALLED = ElectionStatus(constitutional_deadline=date(2028, 2, 17), source="x")
TODAY = date(2026, 8, 23)
NAMES = {"PH": "Pakatan Harapan", "PN": "Perikatan Nasional", "BN": "Barisan Nasional"}

_MARGIN_PATTERN = (
    {PH: 0.60, PN: 0.40},
    {PH: 0.55, PN: 0.45},
    {PH: 0.53, PN: 0.47},
    {PH: 0.52, PN: 0.48},
    {PH: 0.45, PN: 0.55},
    {PH: 0.35, PN: 0.65},
)


def _baseline_222() -> list:
    return [_seat(f"P{i:03d}", "Selangor", **_MARGIN_PATTERN[i % 6]) for i in range(222)]


def _projection_model(*, history=(), majority_threshold=112) -> PageModel:
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


def _markup(page: str) -> str:
    return re.sub(r"<(style|script)\b.*?</\1>", "", page, flags=re.DOTALL)


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
    markup = _markup(page)
    assert "pk-proj-seats" not in markup
    assert "pk-proj-ledger" not in markup


def test_the_methodology_page_is_what_every_politikku_footer_already_links():
    page = render_methodology(_projection_model(), language=Language.MS)
    assert f'href="{methodology_url(Language.MS)}" aria-current="page"' in page


def test_build_all_methodology_languages():
    model = _projection_model()
    pages = build_all_methodology_languages(model)
    assert len(pages) == len(Language)
    assert "Methodology" in pages[Language.EN]
    assert "Metodologi" in pages[Language.MS]
