"""The PolitikKu Dewan Rakyat Activity page: model arithmetic and rendered markup."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import Any

from lpa.domain import ElectionStatus
from lpa.politikku_dewan import (
    PAGE_DIR,
    build_and_write_dewan_pages,
    dewan_page_model,
    format_dewan_date,
    load_dewan_data,
    main,
    party_color,
    pill_style,
    render_dewan_body,
    render_dewan_page,
    swatch_text_color,
)
from lpa.politikku_shell import Language

NOT_CALLED = ElectionStatus(constitutional_deadline=date(2028, 2, 17), source="test")


def _sample_seats() -> list[dict[str, Any]]:
    return [
        {"code": "P.001", "name": "Padang Besar", "state": "Perlis"},
        {"code": "P.002", "name": "Kangar", "state": "Perlis"},
        {"code": "P.003", "name": "Arau", "state": "Perlis"},
    ]


def _sample_hansard(sittings: int = 100) -> dict[str, Any]:
    return {
        "meta": {
            "sittings": sittings,
            "from": "2022-12-19",
            "to": "2026-07-16",
        },
        "seats": {
            "P.001": {"turns": 250, "qa": 80, "sittings": 90, "last": "2026-07-16"},
            "P.002": {"turns": 150, "qa": 40, "sittings": 60, "last": "2026-06-10"},
            "P.003": {"turns": 300, "qa": 95, "sittings": 95, "last": "2026-07-15"},
        },
    }


def _sample_politicians() -> dict[str, Any]:
    return {
        "mps": {
            "P.001": {"name": "Rushdan Rusmi", "coalition": "PN", "party": "PAS"},
            "P.002": {"name": "Zakri Hassan", "coalition": "PN", "party": "BERSATU"},
            "P.003": {"name": "Shahirah Kassim", "coalition": "PH", "party": "PKR"},
        }
    }


# ── Page Model Unit Tests (Pure, I/O-free) ─────────────────────────────────


def test_empty_input_produces_empty_dewan_model():
    model = dewan_page_model(None, None, None)
    assert model.sittings_total == 0
    assert model.from_date == ""
    assert model.to_date == ""
    assert model.top_mp is None
    assert model.median_turns == 0
    assert model.coalitions == ()
    assert model.rows == ()
    assert model.all_rows == ()

    model2 = dewan_page_model([], {}, {})
    assert model2.sittings_total == 0
    assert model2.rows == ()


def test_dewan_model_joins_seats_hansard_and_politicians():
    seats = _sample_seats()
    hansard = _sample_hansard(100)
    politicians = _sample_politicians()

    model = dewan_page_model(seats, hansard, politicians)

    assert model.sittings_total == 100
    assert model.from_date == "2022-12-19"
    assert model.to_date == "2026-07-16"
    assert len(model.rows) == 3
    assert len(model.all_rows) == 3

    # Initial order is sorted by turns descending: P.003 (300), P.001 (250), P.002 (150)
    assert model.rows[0].code == "P.003"
    assert model.rows[0].mp == "Shahirah Kassim"
    assert model.rows[0].coalition == "PH"
    assert model.rows[0].turns == 300
    assert model.rows[0].qa == 95
    assert model.rows[0].sittings == 95
    assert model.rows[0].pct == 95
    assert model.rows[0].last == "2026-07-15"

    assert model.rows[1].code == "P.001"
    assert model.rows[1].turns == 250
    assert model.rows[1].pct == 90

    assert model.rows[2].code == "P.002"
    assert model.rows[2].turns == 150
    assert model.rows[2].pct == 60


def test_dewan_model_top_mp_and_median_turns():
    seats = _sample_seats()
    hansard = _sample_hansard(100)
    politicians = _sample_politicians()

    model = dewan_page_model(seats, hansard, politicians)

    assert model.top_mp is not None
    assert model.top_mp.code == "P.003"
    assert model.top_mp.mp == "Shahirah Kassim"
    assert model.top_mp.turns == 300

    # Turn values: [150, 250, 300] -> median is 250
    assert model.median_turns == 250
    assert model.coalitions == ("PH", "PN")


def test_dewan_model_median_with_even_number_of_rows():
    seats = [
        {"code": "P.001", "name": "Seat 1", "state": "Perlis"},
        {"code": "P.002", "name": "Seat 2", "state": "Perlis"},
        {"code": "P.003", "name": "Seat 3", "state": "Perlis"},
        {"code": "P.004", "name": "Seat 4", "state": "Perlis"},
    ]
    hansard = {
        "meta": {"sittings": 100},
        "seats": {
            "P.001": {"turns": 10, "sittings": 10},
            "P.002": {"turns": 20, "sittings": 20},
            "P.003": {"turns": 30, "sittings": 30},
            "P.004": {"turns": 40, "sittings": 40},
        },
    }
    model = dewan_page_model(seats, hansard, None)
    # Sorted turns: [10, 20, 30, 40], len//2 index = 2 -> 30 (matching JS Math.floor(len/2))
    assert model.median_turns == 30


def test_dewan_model_handles_missing_hansard_and_mp_gracefully():
    seats = [{"code": "P.999", "name": "Unrecorded Seat", "state": "Sabah"}]
    hansard = {"meta": {"sittings": 50}, "seats": {}}
    politicians = {"mps": {}}

    model = dewan_page_model(seats, hansard, politicians)
    assert len(model.rows) == 1
    row = model.rows[0]
    assert row.code == "P.999"
    assert row.mp == ""
    assert row.coalition == ""
    assert row.turns == 0
    assert row.qa == 0
    assert row.sittings == 0
    assert row.pct == 0
    assert row.last == ""


def test_dewan_model_handles_zero_sittings_without_zero_division():
    seats = [{"code": "P.001", "name": "Padang Besar", "state": "Perlis"}]
    hansard = {"meta": {"sittings": 0}, "seats": {"P.001": {"sittings": 10, "turns": 5}}}

    model = dewan_page_model(seats, hansard, None)
    assert model.sittings_total == 0
    assert model.rows[0].pct == 0


def test_dewan_model_ties_in_turns_preserves_stability():
    seats = [
        {"code": "P.001", "name": "Seat 1", "state": "Perlis"},
        {"code": "P.002", "name": "Seat 2", "state": "Perlis"},
    ]
    hansard = {
        "meta": {"sittings": 50},
        "seats": {
            "P.001": {"turns": 100, "sittings": 40},
            "P.002": {"turns": 100, "sittings": 40},
        },
    }
    model = dewan_page_model(seats, hansard, None)
    assert len(model.rows) == 2
    assert model.rows[0].turns == 100
    assert model.rows[1].turns == 100
    assert model.rows[0].code == "P.001"
    assert model.rows[1].code == "P.002"


# ── Color & Formatting Helpers ─────────────────────────────────────────────


def test_party_color_and_pill_style():
    assert party_color("PH") == "#d7263d"
    assert party_color("ph") == "#d7263d"
    assert party_color("UNKNOWN_PARTY") == "#5d6b7d"
    assert party_color("") == "#5d6b7d"
    assert party_color(None) == "#5d6b7d"

    # White text on dark red
    assert swatch_text_color("#d7263d") == "#fff"
    # Dark text on bright blue (BN)
    assert swatch_text_color("#1f9bd6") == "#05070c"

    style = pill_style("#d7263d")
    assert "background:#d7263d" in style
    assert "color:#fff" in style


def test_format_dewan_date():
    assert format_dewan_date("2026-07-16", Language.EN) == "16 Jul 2026"
    assert format_dewan_date("2026-07-16", Language.MS) == "16 Jul 2026"
    assert format_dewan_date("2022-12-19", Language.EN) == "19 Dec 2022"
    assert format_dewan_date("2022-12-19", Language.MS) == "19 Dis 2022"
    assert format_dewan_date("2026-03-05", Language.MS) == "5 Mac 2026"
    assert format_dewan_date("", Language.EN) == ""
    assert format_dewan_date(None, Language.EN) == ""


# ── Render Body Smoke Tests ────────────────────────────────────────────────


def test_render_dewan_body_contains_key_elements_and_classes():
    seats = _sample_seats()
    hansard = _sample_hansard(100)
    politicians = _sample_politicians()

    model = dewan_page_model(seats, hansard, politicians)
    body = render_dewan_body(model, Language.EN)

    # Shell elements matching app.js DOM contract
    assert '<section id="dewan-view"' in body
    assert 'class="pol-dir dewan-page"' in body
    assert 'class="pol-back"' in body
    assert "data-dewan-back" in body
    assert "<h1>Dewan Rakyat activity</h1>" in body
    assert 'class="dewan-tiles"' in body
    assert 'class="pol-dir-controls dewan-controls"' in body
    assert 'id="dewan-search"' in body
    assert 'id="dewan-coal"' in body
    assert 'class="seg chip dewan-sorts"' in body
    assert 'data-dewan-sort="turns"' in body
    assert 'id="dewan-count"' in body
    assert "3 seats" in body
    assert 'class="dewan-table"' in body
    assert 'id="dewan-rows"' in body
    assert 'data-dewan-seat="P.003"' in body
    assert "Shahirah Kassim" in body
    assert "Padang Besar" in body
    assert 'class="dewan-num mono">300</span>' in body
    assert 'class="note dewan-page-note"' in body
    assert 'class="pol-dir-src"' in body


def test_render_dewan_body_empty_model():
    model = dewan_page_model([], {}, {})
    body = render_dewan_body(model, Language.EN)

    assert "pol-dir-empty" in body
    assert "No matching representatives" in body


# ── Render Page Smoke Tests ────────────────────────────────────────────────


def test_render_dewan_page_wraps_in_shell_with_meta_tags():
    seats = _sample_seats()
    hansard = _sample_hansard(100)
    politicians = _sample_politicians()

    model = dewan_page_model(seats, hansard, politicians)
    page_en = render_dewan_page(model, language=Language.EN, status=NOT_CALLED)
    page_ms = render_dewan_page(model, language=Language.MS, status=NOT_CALLED)

    assert '<html lang="en">' in page_en
    assert "<title>Dewan Rakyat Activity — PolitikKu</title>" in page_en
    assert '<meta property="og:title" content="Dewan Rakyat Activity — PolitikKu">' in page_en
    assert '<meta property="og:url" content="https://politikku.my/dewan/">' in page_en
    assert '<link rel="canonical" href="https://politikku.my/dewan/">' in page_en
    assert '<link rel="alternate" hreflang="en" href="https://politikku.my/dewan/">' in page_en
    assert '<link rel="alternate" hreflang="ms" href="https://politikku.my/ms/dewan/">' in page_en

    assert '<html lang="ms">' in page_ms
    assert "<title>Aktiviti Dewan Rakyat — PolitikKu</title>" in page_ms
    assert '<meta property="og:title" content="Aktiviti Dewan Rakyat — PolitikKu">' in page_ms
    assert '<meta property="og:url" content="https://politikku.my/ms/dewan/">' in page_ms
    assert '<link rel="canonical" href="https://politikku.my/ms/dewan/">' in page_ms
    assert "Aktiviti Dewan Rakyat" in page_ms
    assert "Sidang diliputi" in page_ms


# ── I/O & File Writing Tests ───────────────────────────────────────────────


def test_load_dewan_data():
    seats, hansard, politicians = load_dewan_data("frontend/public/data")
    assert "seats" in seats
    assert len(seats["seats"]) == 222
    assert "meta" in hansard
    assert "seats" in hansard
    assert "mps" in politicians


def test_build_and_write_dewan_pages(tmp_path: Path):
    en_len, ms_len = build_and_write_dewan_pages(
        output_dir=tmp_path, data_dir="frontend/public/data"
    )

    en_file = tmp_path / PAGE_DIR / "index.html"
    ms_file = tmp_path / "ms" / PAGE_DIR / "index.html"

    assert en_file.is_file()
    assert ms_file.is_file()
    assert len(en_file.read_bytes()) == en_len
    assert len(ms_file.read_bytes()) == ms_len


def test_main_cli(tmp_path: Path, monkeypatch: Any):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "politikku_dewan",
            "--output-dir",
            str(tmp_path),
            "--data-dir",
            "frontend/public/data",
        ],
    )
    main()
    assert (tmp_path / "dewan" / "index.html").is_file()
    assert (tmp_path / "ms" / "dewan" / "index.html").is_file()
