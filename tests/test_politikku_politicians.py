"""The PolitikKu Politicians Directory page (#143): model tests and HTML smoke tests."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

from lpa.domain import ElectionStatus
from lpa.politikku_politicians import (
    COALITION_COLORS,
    PoliticianCardModel,
    build_and_write_politicians_pages,
    coalition_pill_style,
    dual_seat_map,
    load_coalition_colors,
    namekey_loose,
    names_likely_same_person,
    party_color,
    party_stats_list,
    person_initials,
    person_name_tokens,
    person_photo_html,
    pill_style,
    politicians_page_model,
    render_party_card,
    render_politician_card,
    render_politicians_body,
    render_politicians_page,
    swatch_text_color,
    title_case_name,
)
from lpa.politikku_shell import Language

NOT_CALLED = ElectionStatus(constitutional_deadline=date(2028, 2, 17), source="test")
NOW = datetime(2026, 8, 23, 12, 0, tzinfo=UTC).date()


# ── Pure helper unit tests ────────────────────────────────────────────────


def test_namekey_loose_strips_honorifics_and_particles():
    raw = "Dato' Seri Haji Abdul Hadi bin Awang"
    assert namekey_loose(raw) == "abdulhadiawang"

    dr_tan = "Dr. Tan Sri Lim Guan Eng"
    assert namekey_loose(dr_tan) == "limguaneng"
    assert namekey_loose("") == ""
    assert namekey_loose(None) == ""


def test_names_likely_same_person_matches_ballot_and_common_names():
    # Identical after strip
    assert names_likely_same_person("Mohammad Yusof bin Apdal", "Yusof Apdal")
    # Same person with prefix
    assert names_likely_same_person("Md Israk bin Abdullah", "Mohd Israk Abdullah")
    # Suffix containment: Madius Tangau vs Wilfred Madius Tangau
    assert names_likely_same_person("Madius Tangau", "Wilfred Madius Tangau")
    # Different persons / short tokens should not match
    assert not names_likely_same_person("Munirah Majilis", "Isnaraissah Munirah Majilis")
    assert not names_likely_same_person("Ali", "Abu")


def test_person_name_tokens_extracts_significant_tokens():
    tokens = person_name_tokens("YB Dato' Sri Alexander Nanta Linggi")
    assert "alexander" in tokens
    assert "nanta" in tokens
    assert "linggi" in tokens
    assert "dato" not in tokens
    assert "sri" not in tokens


def test_title_case_name_formats_names_while_preserving_particles():
    assert title_case_name("MOHAMAD BIN SABU") == "Mohamad bin Sabu"
    assert title_case_name("SITI BINTI AHMAD") == "Siti binti Ahmad"
    # Mixed case should be left untouched
    assert title_case_name("Dr. Wee Ka Siong") == "Dr. Wee Ka Siong"


def test_person_initials_and_photo_html():
    assert person_initials("Anwar Ibrahim") == "AI"
    assert person_initials("Gobind Singh Deo") == "GD"
    assert person_initials("Single") == "S"
    assert person_initials("") == "?"

    img_html = person_photo_html("Anwar Ibrahim", "https://example.com/anwar.jpg")
    assert '<img class="pol-photo "' in img_html
    assert 'src="https://example.com/anwar.jpg"' in img_html

    monogram_html = person_photo_html("Anwar Ibrahim", None)
    assert '<span class="pol-photo pol-monogram "' in monogram_html
    assert ">AI</span>" in monogram_html


def test_pill_style_and_party_color():
    colors = load_coalition_colors()
    assert colors["PH"] == "#d7263d"
    assert colors["PN"] == "#15387c"

    color = party_color("PH")
    assert color == "#d7263d"
    style = pill_style(color)
    assert "background:#d7263d" in style
    assert "color:#fff" in style

    # Contrast floor >= 4.5:1
    from lpa.politikku_politicians import _contrast_ratio, _hex_to_rgb

    for name, hex_code in COALITION_COLORS.items():
        fg = swatch_text_color(hex_code)
        fg_rgb = _hex_to_rgb(fg)
        bg_rgb = _hex_to_rgb(hex_code)
        assert fg_rgb is not None
        assert bg_rgb is not None
        ratio = _contrast_ratio(fg_rgb, bg_rgb)
        assert ratio >= 4.5, f"{name} ({hex_code}) failed contrast with {fg}"


def test_coalition_pill_style():
    style = coalition_pill_style("PH")
    assert "background:#d7263d" in style
    assert "color:#fff" in style

    gov_style = coalition_pill_style(is_government=True)
    assert "var(--data-government)" in gov_style
    assert "var(--paper)" in gov_style


# ── Dual Seat Map Tests ───────────────────────────────────────────────────


def test_dual_seat_map_pairs_same_state_and_cross_state():
    mp1 = PoliticianCardModel(
        code="P.024",
        name="Tuan Ibrahim Tuan Man",
        party="PAS",
        coalition="PN",
        seat_name="Kubang Kerian",
        state="Kelantan",
    )
    adun1 = PoliticianCardModel(
        code="6_N.04",
        dun_code="N.04",
        name="Tuan Ibrahim Tuan Man",
        party="PAS",
        coalition="PN",
        seat_name="Cheka",
        state="Pahang",
    )
    mp2 = PoliticianCardModel(
        code="P.043",
        name="Lim Guan Eng",
        party="DAP",
        coalition="PH",
        seat_name="Bagan",
        state="Pulau Pinang",
    )
    adun2 = PoliticianCardModel(
        code="7_N.23",
        dun_code="N.23",
        name="Lim Guan Eng",
        party="DAP",
        coalition="PH",
        seat_name="Air Putih",
        state="Pulau Pinang",
    )
    unrelated_adun = PoliticianCardModel(
        code="7_N.24",
        dun_code="N.24",
        name="Chow Kon Yeow",
        party="DAP",
        coalition="PH",
        seat_name="Padang Kota",
        state="Pulau Pinang",
    )

    mp_to_dun, matched_dun = dual_seat_map([mp1, mp2], [adun1, adun2, unrelated_adun])
    assert "P.024" in mp_to_dun
    assert mp_to_dun["P.024"].seat_name == "Cheka"
    assert "6_N.04" in matched_dun

    assert "P.043" in mp_to_dun
    assert mp_to_dun["P.043"].seat_name == "Air Putih"
    assert "7_N.23" in matched_dun
    assert "7_N.24" not in matched_dun


def test_dual_seat_map_drops_ambiguous_matches():
    mp = PoliticianCardModel(
        code="P.100",
        name="Mohd Noor bin Ahmad",
        party="PAS",
        coalition="PN",
        seat_name="Seat A",
        state="Perak",
    )
    adun1 = PoliticianCardModel(
        code="8_N.01",
        name="Mohd Noor bin Ahmad",
        party="PAS",
        coalition="PN",
        seat_name="Dun 1",
        state="Perak",
    )
    adun2 = PoliticianCardModel(
        code="8_N.02",
        name="Mohd Noor bin Ahmad",
        party="PAS",
        coalition="PN",
        seat_name="Dun 2",
        state="Perak",
    )

    mp_to_dun, matched_dun = dual_seat_map([mp], [adun1, adun2])
    assert "P.100" not in mp_to_dun
    assert len(matched_dun) == 0


# ── Party Rollup Tests ────────────────────────────────────────────────────


def test_party_stats_list_aggregates_and_ignores_vacated():
    mp1 = PoliticianCardModel(
        code="P.001",
        name="Rep One",
        party="PAS",
        coalition="PN",
        seat_name="Parlimen 1",
        state="Perlis",
    )
    mp2 = PoliticianCardModel(
        code="P.002",
        name="Rep Two (Vacant)",
        party="PAS",
        coalition="PN",
        seat_name="Parlimen 2",
        state="Perlis",
        vacated=True,
    )
    adun1 = PoliticianCardModel(
        code="N.01",
        dun_code="N.01",
        name="Rep Three",
        party="PAS",
        coalition="PN",
        seat_name="Dun 1",
        state="Kedah",
    )
    adun2 = PoliticianCardModel(
        code="N.02",
        dun_code="N.02",
        name="Rep Four",
        party="DAP",
        coalition="PH",
        seat_name="Dun 2",
        state="Penang",
    )

    stats = party_stats_list([mp1, mp2], [adun1, adun2])
    by_party = {p.party: p for p in stats}

    assert "PAS" in by_party
    pas = by_party["PAS"]
    assert pas.parliament == 1  # mp2 was vacated
    assert pas.dun == 1
    assert pas.total == 2
    assert pas.coalition == "PN"
    assert len(pas.top_states) == 2
    assert len(pas.samples) == 2
    # MP is ordered ahead of ADUN in samples
    assert pas.samples[0].tier == "parlimen"
    assert pas.samples[1].tier == "dun"

    assert "DAP" in by_party
    assert by_party["DAP"].total == 1


# ── Politicians Page Model Builder Tests ──────────────────────────────────


def test_empty_politicians_page_model():
    model = politicians_page_model(
        parlimen_seats=[],
        dun_seats=[],
        status=NOT_CALLED,
        updated_at=NOW,
    )
    assert model.all_politicians == ()
    assert model.mps == ()
    assert model.aduns == ()
    assert model.parties == ()
    assert model.states == ()
    assert model.coalitions == ()
    assert model.updated_at == NOW
    assert model.status == NOT_CALLED


def test_politicians_page_model_with_sample_records():
    parlimen_seats = [
        {"code": "P.001", "name": "Padang Besar", "state": "Perlis"},
        {"code": "P.002", "name": "Kangar", "state": "Perlis"},
    ]
    dun_seats = [
        {"code": "09_N.01", "dun_code": "N.01", "name": "Titi Tinggi", "state": "Perlis"},
    ]
    politicians_data = {
        "mps": {
            "P.001": {"name": "Rushdan Rusmi", "party": "PAS", "coalition": "PN"},
            "P.002": {"name": "Zakri Hassan", "party": "BERSATU", "coalition": "PN"},
        }
    }
    results_dun = {
        "09_N.01": {"name": "IZIZAM IBRAHIM", "party": "BERSATU", "coalition": "PN"},
    }
    current_affiliations = {
        "parlimen": {
            "P.001": {"current_name": "Rushdan Bin Rusmi", "current_party": "PAS"},
        }
    }

    model = politicians_page_model(
        parlimen_seats=parlimen_seats,
        dun_seats=dun_seats,
        politicians_data=politicians_data,
        results_dun=results_dun,
        current_affiliations=current_affiliations,
        status=NOT_CALLED,
        updated_at=NOW,
    )

    assert len(model.mps) == 2
    assert len(model.aduns) == 1
    assert len(model.all_politicians) == 3
    assert len(model.parties) == 2

    p001 = next(m for m in model.mps if m.code == "P.001")
    assert p001.name == "Rushdan Bin Rusmi"
    assert p001.party == "PAS"
    assert p001.coalition == "PN"
    assert p001.seat_name == "Padang Besar"

    adun = model.aduns[0]
    assert adun.name == "Izizam Ibrahim"
    assert adun.dun_code == "N.01"


# ── Rendering Smoke Tests ─────────────────────────────────────────────────


def test_render_politicians_card_and_party_card():
    card = PoliticianCardModel(
        code="P.100",
        name="YB Contoh",
        party="PKR",
        coalition="PH",
        seat_name="Kawasan Ujian",
        state="Selangor",
        divisions_count=12,
        bills_count=3,
        has_legislative=True,
        socials={"fb": "ybcontoh", "tw": "ybcontoh"},
        socials_source="wikidata",
    )
    html_card = render_politician_card(card, Language.EN)
    assert 'data-pol-code="P.100"' in html_card
    assert "YB Contoh" in html_card
    assert "Kawasan Ujian" in html_card
    assert "12 votes · 3 bills" in html_card
    assert 'class="pol-soc-icon"' in html_card
    assert (
        'class="pol-card-badge pill" style="background:#d7263d;color:#fff">PKR</span>' in html_card
    )

    party = party_stats_list([card], [])[0]
    html_party = render_party_card(party, Language.EN)
    assert 'data-pol-party="PKR"' in html_party
    assert 'class="pol-party-mark" style="background:#d7263d;color:#fff">PKR</span>' in html_party
    assert '<span class="pill" style="background:#d7263d;color:#fff">PH</span>' in html_party
    assert ">1<" in html_party


def test_render_politicians_body_structure():
    model = politicians_page_model(
        parlimen_seats=[{"code": "P.001", "name": "Seat A", "state": "Johor"}],
        dun_seats=[],
        politicians_data={"mps": {"P.001": {"name": "YB A", "party": "UMNO", "coalition": "BN"}}},
        status=NOT_CALLED,
        updated_at=NOW,
    )
    body_all = render_politicians_body(model, Language.EN, tier="all")
    assert '<div class="pol-dir">' in body_all
    assert 'data-pol-tier="all" aria-selected="true" class="on"' in body_all
    assert 'data-pol-tier="parlimen" aria-selected="false"' in body_all
    assert 'id="pol-search"' in body_all
    assert 'id="pol-state"' in body_all
    assert 'id="pol-coal"' in body_all
    assert 'id="pol-grid" class="pol-grid"' in body_all
    assert "1 politicians" in body_all
    assert "YB A" in body_all
    assert 'style="background:#1f9bd6;color:#05070c">UMNO</span>' in body_all

    body_parties = render_politicians_body(model, Language.EN, tier="parties")
    assert 'data-pol-tier="parties" aria-selected="true" class="on"' in body_parties
    assert 'id="pol-grid" class="pol-party-grid"' in body_parties
    assert "1 parties / blocs" in body_parties


def test_render_politicians_page_shell_and_meta_en_ms():
    model = politicians_page_model(
        parlimen_seats=[],
        dun_seats=[],
        status=NOT_CALLED,
        updated_at=NOW,
    )
    en_page = render_politicians_page(model, language=Language.EN)
    assert "<!doctype html>" in en_page
    assert '<html lang="en">' in en_page
    assert "<title>Politicians — Dewan Rakyat &amp; State Assemblies | PolitikKu</title>" in en_page
    assert 'href="/politicians/"' in en_page

    ms_page = render_politicians_page(model, language=Language.MS)
    assert '<html lang="ms">' in ms_page
    assert (
        "<title>Ahli Politik — Dewan Rakyat &amp; Dewan Undangan Negeri | PolitikKu</title>"
        in ms_page
    )
    assert 'href="/ms/politicians/"' in ms_page
    assert "Kembali ke peta" not in ms_page


def test_build_and_write_politicians_pages_writes_files(tmp_path: Path):
    en_bytes, ms_bytes = build_and_write_politicians_pages(
        output_dir=tmp_path,
        base_data_path=Path("frontend/public/data"),
    )
    en_file = tmp_path / "politicians" / "index.html"
    ms_file = tmp_path / "ms" / "politicians" / "index.html"

    assert en_file.exists()
    assert ms_file.exists()
    assert len(en_file.read_bytes()) == en_bytes
    assert len(ms_file.read_bytes()) == ms_bytes
