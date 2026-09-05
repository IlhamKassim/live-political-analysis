"""The PolitikKu Bills Tracker page (#143): model arithmetic and rendered markup.

Shaped like `tests/test_politikku_sentiment.py`: `bills_page_model()` gets
exhaustive, no-I/O unit tests (empty input, a realistic multi-row case, and
the no-Division edge case `Bill.unverified` documents elsewhere in this
codebase's style); `render_bills_body()`/`render_bills_page()` get light
smoke tests only.
"""

from __future__ import annotations

import sys
from datetime import date

from lpa.bill_tracker import Bill, DivisionResult
from lpa.domain import ElectionStatus
from lpa.politikku_bills import (
    PAGE_PATH,
    bills_page_model,
    build_and_write_bills_pages,
    main,
    render_bills_body,
    render_bills_page,
)
from lpa.politikku_shell import Language

STATUS = ElectionStatus(constitutional_deadline=date(2028, 2, 17), source="x")

DIVISION = DivisionResult(
    sitting_date=date(2026, 7, 20),
    ayes=110,
    noes=60,
    abstentions=2,
    absent=3,
    outcome="Dibacakan kali kedua",
    hansard_url="https://hansard.parlimen.gov.my/hansard/dewan-rakyat/2026-07-20",
)


def _bill(
    code: str,
    *,
    title: str = "RUU Ujian",
    stage: str = "Lulus",
    stage_date: date = date(2026, 7, 1),
    division: DivisionResult | None = None,
) -> Bill:
    return Bill(
        code=code,
        title=title,
        year=stage_date.year,
        stage=stage,
        stage_date=stage_date,
        summary="Petikan huraian rasmi.",
        summary_source_url="https://www.parlimen.gov.my/files/billindex/pdf/test.pdf#page=1",
        division=division,
        unverified={} if division is not None else {"division": "Passed on a voice vote."},
    )


def test_empty_bills_produces_empty_model():
    model = bills_page_model({}, retrieved=date(2026, 8, 1), status=STATUS)

    assert model.bills == ()
    assert model.total_bills == 0
    assert model.passed_bills_count == 0
    assert model.divisions_count == 0
    assert model.stages == ()
    assert model.sources_count == 0
    assert model.updated_at == date(2026, 8, 1)


def test_model_computes_counts_and_sorts_bills_by_stage_date_descending():
    bills = {
        "D.R.1/2026": _bill("D.R.1/2026", stage="Lulus", stage_date=date(2026, 6, 1)),
        "D.R.2/2026": _bill(
            "D.R.2/2026",
            stage="Dirujuk ke JKPK",
            stage_date=date(2026, 7, 20),
            division=DIVISION,
        ),
        "D.R.3/2026": _bill("D.R.3/2026", stage="Bacaan kali pertama", stage_date=date(2026, 8, 1)),
    }

    model = bills_page_model(bills, retrieved=date(2026, 8, 15), status=STATUS)

    assert model.total_bills == 3
    assert model.passed_bills_count == 1
    assert model.divisions_count == 1
    assert model.stages == ("Bacaan kali pertama", "Dirujuk ke JKPK", "Lulus")
    # Newest stage_date first.
    assert [b.code for b in model.bills] == ["D.R.3/2026", "D.R.2/2026", "D.R.1/2026"]
    assert model.updated_at == date(2026, 8, 15)


def test_model_leaves_a_bill_with_no_division_result_as_none_not_a_stub():
    # The Division edge case: a Bill passed on a voice vote never had one
    # taken, and `Bill.unverified` (mirroring `MPProfile.unverified`
    # elsewhere) is where that absence is explained rather than left to
    # look like an oversight.
    bill = _bill("D.R.9/2026", stage="Lulus", division=None)
    model = bills_page_model({"D.R.9/2026": bill}, retrieved=date(2026, 8, 1), status=STATUS)

    only = model.bills[0]
    assert only.division is None
    assert only.unverified["division"] == "Passed on a voice vote."
    assert model.divisions_count == 0


def test_render_bills_body_carries_known_content_and_dom_contract():
    bill = _bill(
        "D.R.5/2026",
        title="RUU Kumpulan Wang Amanah Negara 2026",
        stage="Lulus",
        stage_date=date(2026, 7, 16),
    )
    model = bills_page_model({"D.R.5/2026": bill}, retrieved=date(2026, 8, 1), status=STATUS)
    body = render_bills_body(model, Language.EN)

    # `app.js`'s current #bills-view DOM contract, not the retired pk-bill-*
    # print-register classes.
    assert 'id="bills-view"' in body
    assert 'class="pol-dir dewan-page bills-page"' in body
    assert 'id="bills-rows"' in body
    assert 'id="bills-search"' in body
    assert 'id="bills-stage"' in body
    assert 'class="bill-expandable"' in body

    assert "RUU Kumpulan Wang Amanah Negara 2026" in body
    assert "D.R.5/2026" in body


def test_render_bills_page_wraps_in_shell_with_real_meta_and_og_tags():
    bill = _bill("D.R.5/2026", title="RUU Ujian Utama")
    model = bills_page_model({"D.R.5/2026": bill}, retrieved=date(2026, 8, 1), status=STATUS)

    page_en = render_bills_page(model, Language.EN)
    page_ms = render_bills_page(model, Language.MS)

    assert "<title>Bills in the Dewan Rakyat — PolitikKu</title>" in page_en
    assert 'og:title" content="Bills in the Dewan Rakyat — PolitikKu"' in page_en
    assert 'og:description" content="Track active and passed Bills' in page_en
    assert 'og:image" content="https://politikku.my/og-image.png"' in page_en
    assert 'rel="canonical" href="https://politikku.my/bills/"' in page_en
    assert "RUU Ujian Utama" in page_en

    assert "<title>Rang Undang-Undang di Dewan Rakyat — PolitikKu</title>" in page_ms
    assert 'rel="canonical" href="https://politikku.my/ms/bills/"' in page_ms


def test_build_and_write_bills_pages(tmp_path, monkeypatch):
    bills = {"D.R.1/2026": _bill("D.R.1/2026")}
    monkeypatch.setattr("lpa.politikku_bills.load_bills", lambda path: bills)
    monkeypatch.setattr(
        "lpa.politikku_bills._load_bills_and_retrieved",
        lambda path: (bills, date(2026, 8, 1)),
    )
    monkeypatch.setattr("lpa.config.load_election_status", lambda: STATUS)

    en_len, ms_len = build_and_write_bills_pages(output_dir=tmp_path)

    en_file = tmp_path / "bills" / "index.html"
    ms_file = tmp_path / "ms" / "bills" / "index.html"
    assert en_file.is_file()
    assert ms_file.is_file()
    assert len(en_file.read_bytes()) == en_len
    assert len(ms_file.read_bytes()) == ms_len


def test_main_cli_writes_pages(tmp_path, monkeypatch):
    bills = {"D.R.1/2026": _bill("D.R.1/2026")}
    monkeypatch.setattr("lpa.politikku_bills.load_bills", lambda path: bills)
    monkeypatch.setattr(
        "lpa.politikku_bills._load_bills_and_retrieved",
        lambda path: (bills, date(2026, 8, 1)),
    )
    monkeypatch.setattr("lpa.config.load_election_status", lambda: STATUS)
    monkeypatch.setattr(sys, "argv", ["politikku_bills", "--output-dir", str(tmp_path)])

    main()

    assert (tmp_path / "bills" / "index.html").is_file()
    assert (tmp_path / "ms" / "bills" / "index.html").is_file()


def test_page_path_matches_the_directory_shape():
    assert PAGE_PATH == "bills/"
