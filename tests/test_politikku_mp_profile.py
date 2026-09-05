"""The PolitikKu MP profile page (#79, #143): model arithmetic, rendered markup, and static file generation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from lpa.domain import Coalition, ElectionStatus, SeatBaseline, SeatCall
from lpa.mp_profile import ABSTAIN, AYE, Contact, Division, GE15Result, MPProfile
from lpa.politikku_mp_profile import (
    DIVISIONS_SHOWN,
    build_and_write_mp_profile_pages,
    mp_profile_page_model,
    render_mp_profile,
    render_mp_profile_body,
)
from lpa.politikku_shell import Language

PH = "PH"
PN = "PN"
NAMES: dict[Coalition, str] = {
    "PH": "Pakatan Harapan",
    "PN": "Perikatan Nasional",
    "BN": "Barisan Nasional",
    "GPS": "Gabungan Parti Sarawak",
}

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


@dataclass(frozen=True)
class _DummyPageContext:
    updated_at: date
    sources_count: int
    status: ElectionStatus
    government_coalitions: frozenset[Coalition]


def _page_model() -> _DummyPageContext:
    return _DummyPageContext(
        updated_at=datetime(2026, 8, 23, tzinfo=UTC).date(),
        sources_count=222,
        status=ElectionStatus(constitutional_deadline=date(2028, 2, 17), source="test"),
        government_coalitions=frozenset({"PH", "BN", "GPS"}),
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


def _profile(**overrides: Any) -> MPProfile:
    default_divisions = tuple(_division(date(2026, 3, i + 1)) for i in range(DIVISIONS_SHOWN + 2))
    payload: dict[str, Any] = {
        "seat_code": "P.000",
        "name": "YB Tuan Contoh",
        "coalition": PH,
        "party": "DAP",
        "term_start": date(2022, 12, 19),
        "ge15": GE15,
        "contact": Contact(
            address="Pusat Khidmat Rakyat, Bangi",
            email="yb@example.org",
            phone="+60389201234",
            profile_url="https://www.parlimen.gov.my/ahli-dewan.html?uweb=dr&id=0",
        ),
        "divisions": default_divisions,
        "bills_sponsored": (),
        "unverified": {
            "attendance": "Parliament's attendance page 500s",
            "bills_sponsored": "Bills register 404s",
        },
    }
    payload.update(overrides)
    return MPProfile(**payload)


def _baseline(**overrides: Any) -> SeatBaseline:
    payload: dict[str, Any] = {
        "code": "P.000",
        "name": "Kawasan Contoh",
        "state": "Selangor",
        "vote_share": {PH: 0.60, PN: 0.40},
        "margin": 0.20,
    }
    payload.update(overrides)
    return SeatBaseline(**payload)


def _call(**overrides: Any) -> SeatCall:
    payload: dict[str, Any] = {
        "code": "P.000",
        "coalition": PH,
        "margin": 0.15,
    }
    payload.update(overrides)
    return SeatCall(**payload)


def _model(
    *,
    page: Any | None = None,
    profile: MPProfile | None = None,
    baseline: SeatBaseline | None = None,
    call: SeatCall | None = None,
    names: dict[Coalition, str] | None = None,
) -> Any:
    return mp_profile_page_model(
        page=page or _page_model(),
        profile=profile or _profile(),
        baseline=baseline or _baseline(),
        call=call or _call(),
        names=names or NAMES,
    )


# ── Model Arithmetic & Invariant Tests ────────────────────────────────────


def test_a_profile_for_a_different_seat_than_the_baseline_is_rejected():
    with pytest.raises(ValueError, match="does not match"):
        mp_profile_page_model(
            _page_model(), _profile(seat_code="P.999"), _baseline(), _call(), NAMES
        )


def test_a_profile_for_a_different_seat_than_the_call_is_rejected():
    with pytest.raises(ValueError, match="does not match"):
        mp_profile_page_model(
            _page_model(),
            _profile(),
            _baseline(),
            SeatCall(code="P.999", coalition=PH, margin=0.1),
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
    html_text = render_mp_profile_body(_model())
    assert html_text.count("This Seat in the GE16 projection") == 1
    headline_idx = html_text.index('class="pk-mp-projection-headline">')
    assert "NOT CALIBRATED" in html_text[headline_idx : headline_idx + 300]


def test_a_published_attendance_figure_shows_a_percentage_and_no_gap_note():
    model = _model(profile=_profile(attendance=0.72))
    assert model.attendance_pct == pytest.approx(72.0)
    assert model.attendance_note_en is None
    assert model.attendance_note_ms is None


def test_an_unpublished_attendance_figure_states_why_rather_than_a_blank():
    model = _model()
    assert model.attendance_pct is None
    assert model.attendance_note_en == "Parliament's attendance page 500s"
    assert model.attendance_note_ms == "Parliament's attendance page 500s"


def test_interventions_is_not_a_field_anywhere_on_the_model():
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


def test_only_the_first_four_divisions_are_shown():
    model = _model()
    assert len(model.divisions) == DIVISIONS_SHOWN
    assert model.divisions[0].sitting_date_text == "1 Mar 2026"


def test_an_abstain_vote_gets_its_own_label_with_no_invented_colour():
    profile = _profile(divisions=(_division(date(2026, 3, 2), vote=ABSTAIN),))
    model = _model(profile=profile)
    html_text = render_mp_profile_body(model)
    assert "ABSTAIN" in html_text
    assert "pk-vote-absent" in html_text


def test_vote_pill_colours_match_the_readme_table_exactly():
    html_text = render_mp_profile_body(_model())
    assert (
        "background: var(--positive-bg); border: 1px solid var(--positive-border); color: var(--accent);"
        in html_text
    )
    assert (
        "background: var(--caution-bg); border: 1px solid var(--caution-border); color: var(--caution);"
        in html_text
    )
    assert (
        "background: var(--paper-alt); border: 1px solid var(--line); color: var(--muted);"
        in html_text
    )


def test_the_mobile_media_query_puts_the_projection_right_after_record():
    html_text = render_mp_profile_body(_model())
    assert ".pk-mp-record { order: 1;" in html_text
    assert ".pk-mp-projection { order: 2;" in html_text


def test_who_lives_here_states_the_ingestion_gap_not_fabricated_figures():
    html_text = render_mp_profile_body(_model())
    assert "Census profile not yet ingested" in html_text
    assert "DOSM" in html_text


def test_no_photo_field_exists_the_page_always_renders_the_fallback():
    html_text = render_mp_profile_body(_model())
    assert "No portrait available" in html_text


def test_contact_actions_are_built_only_from_fields_actually_present():
    model = _model(profile=_profile(contact=Contact(email="x@example.org")))
    labels = [a.label for a in model.contact_actions]
    assert labels == ["Email MP"]


def test_no_contact_fields_at_all_states_the_gap_not_empty_buttons():
    model = _model(profile=_profile(contact=Contact()))
    assert model.contact_actions == ()
    html_text = render_mp_profile_body(model)
    assert "No correspondence address published" in html_text


def test_the_government_chip_reads_government_coalition_for_a_government_seat():
    model = _model()
    assert model.government is True
    assert "Government Coalition" in render_mp_profile_body(model)


def test_the_full_page_renders_with_the_shell():
    html_text = render_mp_profile(_model())
    assert "<!doctype html>" in html_text
    assert "YB Tuan Contoh" in html_text
    assert 'href="/mp/P.000/"' in html_text


# ── Bilingual Copy Tests ──────────────────────────────────────────────────


def test_bm_rendering_differs_from_english_and_translates_the_chrome_copy():
    model = _model()
    en = render_mp_profile_body(model)
    ms = render_mp_profile_body(model, Language.MS)

    assert en != ms
    assert "Gabungan Kerajaan" in ms
    assert "Government Coalition" not in ms
    assert "Rekod penggal ini" in ms
    assert "Kehadiran" in ms
    assert "Hubungi &amp; pusat khidmat" in ms
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
    ms = render_mp_profile_body(_model(), Language.MS)
    assert "AYE" in ms


def test_a_data_sourced_gap_reason_is_left_untranslated_in_both_languages():
    model = _model()
    en = render_mp_profile_body(model)
    ms = render_mp_profile_body(model, Language.MS)
    assert "attendance page 500s" in en
    assert "attendance page 500s" in ms


def test_the_full_bm_page_wraps_in_the_shell_with_the_bm_lang_attribute():
    page = render_mp_profile(_model(), language=Language.MS)
    assert '<html lang="ms">' in page
    assert "Gabungan Kerajaan" in page
    assert 'href="/ms/mp/P.000/"' in page


# ── Disk Writing Smoke Tests ──────────────────────────────────────────────


def test_build_and_write_mp_profile_pages_writes_directory_structure(tmp_path: Path):
    count = build_and_write_mp_profile_pages(
        output_dir=tmp_path,
        base_data_path=Path("frontend/public/data"),
    )
    assert count > 0

    # P.001 is Padang Besar, which has an MP profile
    en_file = tmp_path / "mp" / "P.001" / "index.html"
    ms_file = tmp_path / "ms" / "mp" / "P.001" / "index.html"

    assert en_file.exists(), f"Expected {en_file} to exist"
    assert ms_file.exists(), f"Expected {ms_file} to exist"

    en_content = en_file.read_text(encoding="utf-8")
    assert "<!doctype html>" in en_content
    assert '<html lang="en">' in en_content

    ms_content = ms_file.read_text(encoding="utf-8")
    assert "<!doctype html>" in ms_content
    assert '<html lang="ms">' in ms_content
