"""The PolitikKu MP profile page (#79): model arithmetic and rendered markup.

Same discipline as the closest siblings `test_politikku_homepage.py`/
`test_politikku_landing.py`: structural assertions, and this file reuses
`test_politikku_homepage.py`'s own `NAMES`/`_page_model` fixture for the
Government Coalition membership/status/sources this page also states,
rather than building a second 222-Seat baseline.
"""

from __future__ import annotations

from datetime import date

import pytest
from test_politikku_homepage import NAMES, _page_model

from lpa.domain import SeatBaseline, SeatCall
from lpa.mp_profile import ABSTAIN, AYE, Contact, Division, GE15Result, MPProfile
from lpa.politikku_mp_profile import (
    DIVISIONS_SHOWN,
    mp_profile_page_model,
    render_mp_profile,
    render_mp_profile_body,
)
from lpa.politikku_shell import Language

PH = "PH"
PN = "PN"

GE15 = GE15Result(
    votes=141568,
    majority=69701,
    vote_share=0.5795055896451363,
    valid_votes=244291,
    runner_up_votes=71867,
    runner_up_coalition=PN,
    electors=303430,
    turnout=0.8133506904393105,
    source_url="https://example.org/ge15",
)


def _division(sitting_date: date, vote: str = AYE) -> Division:
    return Division(
        sitting_date=sitting_date,
        subject="RUU Contoh",
        vote=vote,
        ayes=100,
        noes=50,
        abstentions=0,
        absent=72,
        outcome="Dibacakan kali kedua",
        hansard_url="https://hansard.parlimen.gov.my/example",
    )


def _profile(**overrides: object) -> MPProfile:
    """A complete, honestly-gapped `MPProfile` for "P000" — `_page_model()`'s
    own PH-safe Seat (Baseline PH 60% / PN 40%, Government-clear, no
    Tight)."""
    fields: dict[str, object] = {
        "seat_code": "P000",
        "name": "YB Tuan Contoh",
        "coalition": PH,
        "term_start": date(2022, 12, 19),
        "ge15": GE15,
        "contact": Contact(
            address="1 Jalan Contoh",
            phone="03-1234567",
            email="contoh@example.org",
            profile_url="https://www.parlimen.gov.my/profile-ahli.html?id=1",
        ),
        "divisions": (
            _division(date(2026, 3, 2)),
            _division(date(2025, 11, 4)),
            _division(date(2025, 8, 28)),
            _division(date(2025, 3, 4)),
            _division(date(2024, 12, 11)),
        ),
        "bills_sponsored": (),
        "party": None,
        "attendance": None,
        "unverified": {
            "party": "no source states the component party",
            "attendance": "Parliament's attendance page 500s",
            "contact.opening_hours": "not published for any Member",
            "bills_sponsored": "checked against the Bills register; nothing found",
        },
    }
    fields.update(overrides)
    return MPProfile(**fields)  # type: ignore[arg-type]


def _baseline() -> SeatBaseline:
    page = _page_model()
    seat = next(s for s in page.seats if s.code == "P000")
    return SeatBaseline(
        code=seat.code, name=seat.name, state=seat.state, vote_share={PH: 0.60, PN: 0.40}
    )


def _call(coalition: str = PH, margin: float = 0.20) -> SeatCall:
    return SeatCall(code="P000", coalition=coalition, margin=margin)


def _model(profile: MPProfile | None = None, call: SeatCall | None = None):
    return mp_profile_page_model(
        _page_model(), profile or _profile(), _baseline(), call or _call(), NAMES
    )


def test_a_profile_for_a_different_seat_than_the_baseline_is_rejected():
    with pytest.raises(ValueError, match="does not match"):
        mp_profile_page_model(
            _page_model(), _profile(seat_code="P999"), _baseline(), _call(), NAMES
        )


def test_a_profile_for_a_different_seat_than_the_call_is_rejected():
    with pytest.raises(ValueError, match="does not match"):
        mp_profile_page_model(
            _page_model(),
            _profile(),
            _baseline(),
            SeatCall(code="P999", coalition=PH, margin=0.1),
            NAMES,
        )


def test_a_seat_the_call_still_holds_reads_as_hold_not_gain():
    model = _model(call=_call(coalition=PH, margin=0.20))
    assert model.projection.winner_name == "Pakatan Harapan"
    assert model.projection.holds is True
    assert "Pakatan Harapan hold" in render_mp_profile_body(model)


def test_a_seat_the_call_flips_reads_as_gain():
    model = _model(call=_call(coalition=PN, margin=0.05))
    assert model.projection.winner_name == "Perikatan Nasional"
    assert model.projection.holds is False
    assert "Perikatan Nasional gain" in render_mp_profile_body(model)


def test_the_projection_bar_splits_to_one_hundred_percent():
    model = _model()
    p = model.projection
    assert p.left_pct + p.right_pct == pytest.approx(100.0, abs=0.1)


def test_the_projection_headline_always_carries_the_not_calibrated_tag():
    html = render_mp_profile_body(_model())
    assert html.count("This Seat in the GE16 projection") == 1
    headline_idx = html.index('class="pk-mp-projection-headline">')
    assert "NOT CALIBRATED" in html[headline_idx : headline_idx + 300]


def test_a_published_attendance_figure_shows_a_percentage_and_no_gap_note():
    model = _model(profile=_profile(attendance=0.72))
    assert model.attendance_pct == pytest.approx(72.0)
    assert model.attendance_note_en is None
    assert model.attendance_note_ms is None


def test_an_unpublished_attendance_figure_states_why_rather_than_a_blank():
    model = _model()
    assert model.attendance_pct is None
    assert model.attendance_note_en == "Parliament's attendance page 500s"
    # A per-profile reason has no BM translation this codebase produces —
    # left identical in both languages, an honest gap (see `_gap_note`).
    assert model.attendance_note_ms == "Parliament's attendance page 500s"


def test_interventions_is_not_a_field_anywhere_on_the_model():
    # No field named "interventions" exists — there is no source to compute
    # it from for any MP, so the card must not silently reappear.
    assert not any("intervention" in f.lower() for f in vars(_model()))


def test_empty_bills_sponsored_states_the_real_finding_not_a_blank():
    model = _model()
    assert model.bills_sponsored == ()
    assert "Bills register" in (model.bills_sponsored_note_en or "")


def test_sponsored_bills_are_listed_with_no_note():
    model = _model(profile=_profile(bills_sponsored=("RUU Contoh 2026",)))
    assert model.bills_sponsored == ("RUU Contoh 2026",)
    assert model.bills_sponsored_note_en is None
    assert model.bills_sponsored_note_ms is None


def test_only_the_first_four_divisions_are_shown_newest_first():
    model = _model()
    assert len(model.divisions) == DIVISIONS_SHOWN
    assert model.divisions[0].sitting_date_text == "2 Mar 2026"


def test_an_abstain_vote_gets_its_own_label_with_no_invented_colour():
    profile = _profile(divisions=(_division(date(2026, 3, 2), vote=ABSTAIN),))
    model = _model(profile=profile)
    html = render_mp_profile_body(model)
    assert "ABSTAIN" in html
    assert "pk-vote-absent" in html  # falls back to the neutral pill style


def test_vote_pill_colours_match_the_readme_table_exactly():
    # README "Vote pills" table — AYE/NO/ABSENT hex, none of which reuse the
    # NOT CALIBRATED tag's caution tokens (a real bug the first cut of this
    # module shipped: NO borrowed --caution-bg/--caution-border instead).
    html = render_mp_profile_body(_model())
    assert "background: #eef3f0; border: 1px solid #cfe0da; color: #1f5c58;" in html
    assert "background: #f6f0e4; border: 1px solid #e6dcc4; color: #8a6a2f;" in html
    assert "background: #f1efea; border: 1px solid #dcd8cf; color: #8a9099;" in html


def test_the_mobile_media_query_puts_the_projection_right_after_record():
    # README's mobile spec is a strict sequence ("record; then the Seat's
    # projection; then the source footer"), not the desktop column order
    # collapsed — this pins the `order` values `_CSS` assigns.
    html = render_mp_profile_body(_model())
    assert ".pk-mp-record { order: 1;" in html
    assert ".pk-mp-projection { order: 2;" in html


def test_who_lives_here_states_the_ingestion_gap_not_fabricated_figures():
    html = render_mp_profile_body(_model())
    assert "Census profile not yet ingested" in html
    assert "DOSM" in html


def test_no_photo_field_exists_the_page_always_renders_the_fallback():
    html = render_mp_profile_body(_model())
    assert "No portrait available" in html


def test_contact_actions_are_built_only_from_fields_actually_present():
    model = _model(profile=_profile(contact=Contact(email="x@example.org")))
    labels = [a.label for a in model.contact_actions]
    assert labels == ["Email MP"]


def test_no_contact_fields_at_all_states_the_gap_not_empty_buttons():
    model = _model(profile=_profile(contact=Contact()))
    assert model.contact_actions == ()
    html = render_mp_profile_body(model)
    assert "No correspondence address published" in html


def test_the_government_chip_reads_government_coalition_for_a_government_seat():
    model = _model()
    assert model.government is True
    assert "Government Coalition" in render_mp_profile_body(model)


def test_the_full_page_renders_with_the_shell():
    html = render_mp_profile(_model())
    assert "<!doctype html>" in html
    assert "YB Tuan Contoh" in html


# ── #81: bilingual copy ──────────────────────────────────────────────────


def test_bm_rendering_differs_from_english_and_translates_the_chrome_copy():
    model = _model()
    en = render_mp_profile_body(model)
    ms = render_mp_profile_body(model, Language.MS)

    assert en != ms
    assert "Gabungan Kerajaan" in ms
    assert "Government Coalition" not in ms
    assert "Rekod penggal ini" in ms  # Record this term
    assert "Kehadiran" in ms  # Attendance
    assert "Hubungi &amp; pusat khidmat" in ms  # Contact & service centre
    # The MP's own name and the real MP profile's proper nouns are identical
    # in both languages — nothing here is a fact hidden from one reader.
    assert "YB Tuan Contoh" in ms


def test_the_not_calibrated_tag_translates_and_stays_inline_in_bm():
    ms = render_mp_profile_body(_model(), Language.MS)
    headline_idx = ms.index('class="pk-mp-projection-headline">')
    assert "BELUM DITENTUKUR" in ms[headline_idx : headline_idx + 300]
    assert "NOT CALIBRATED" not in ms


def test_bm_projection_headline_translates_hold_and_gain():
    hold_model = _model(call=_call(coalition=PH, margin=0.20))
    gain_model = _model(call=_call(coalition=PN, margin=0.05))

    assert "Pakatan Harapan kekal" in render_mp_profile_body(hold_model, Language.MS)
    assert "Perikatan Nasional rampas" in render_mp_profile_body(gain_model, Language.MS)


def test_bm_vote_pill_labels_stay_aye_no_absent_untranslated():
    # Hansard vote codes, not translated (see `_VOTE_PILL_LABEL`'s docstring).
    ms = render_mp_profile_body(_model(), Language.MS)
    assert "AYE" in ms


def test_a_data_sourced_gap_reason_is_left_untranslated_in_both_languages():
    # `_gap_note`: a real per-profile `unverified` reason has no BM
    # translation this codebase invents — identical text in both.
    model = _model()
    en = render_mp_profile_body(model)
    ms = render_mp_profile_body(model, Language.MS)
    assert "attendance page 500s" in en
    assert "attendance page 500s" in ms


def test_the_full_bm_page_wraps_in_the_shell_with_the_bm_lang_attribute():
    page = render_mp_profile(_model(), language=Language.MS)
    assert '<html lang="ms">' in page
    assert "Gabungan Kerajaan" in page
