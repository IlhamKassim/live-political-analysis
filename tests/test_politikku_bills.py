"""Tests for the PolitikKu Parliamentary Bills Tracker page (#80)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lpa.bill_tracker import Bill, DivisionResult
from lpa.domain import ElectionStatus
from lpa.politikku_bills import (
    BillsPageModel,
    bills_page_model,
    build_and_write_bills_pages,
    render_bills_page,
)
from lpa.politikku_shell import Language

TEST_BILL_1 = Bill(
    code="D.R.1/2026",
    title="RUU Perlembagaan (Pindaan) 2026",
    year=2026,
    stage="Lulus",
    stage_date=date(2026, 7, 16),
    summary="Suatu Akta untuk meminda Perlembagaan Persekutuan.",
    summary_source_url="https://www.parlimen.gov.my/files/billindex/pdf/2026/DR/RUU1.pdf",
    division=DivisionResult(
        sitting_date=date(2026, 7, 16),
        ayes=148,
        noes=74,
        abstentions=0,
        absent=0,
        outcome="passed",
        hansard_url="https://www.parlimen.gov.my/hansard.pdf",
    ),
    unverified={},
)

TEST_BILL_2 = Bill(
    code="D.R.2/2026",
    title="RUU Kebebasan Maklumat 2026",
    year=2026,
    stage="Dirujuk ke JKPK",
    stage_date=date(2026, 7, 14),
    summary="Akta yang dicadangkan bertujuan untuk mengawal selia maklumat rasmi.",
    summary_source_url="https://www.parlimen.gov.my/files/billindex/pdf/2026/DR/RUU2.pdf",
    division=None,
    unverified={"division": "Passed on a voice vote."},
)


TEST_BILL_3 = Bill(
    code="D.R.4/2026",
    title="RUU Perlembagaan (Pindaan 2) 2026",
    year=2026,
    stage="Tidak Mendapat Undi 2/3 Peringkat Bacaan Ke-2",
    stage_date=date(2026, 3, 2),
    summary="Pindaan Perlembagaan gagal.",
    summary_source_url="https://www.parlimen.gov.my/files/billindex/pdf/2026/DR/RUU4.pdf",
    division=None,
    unverified={},
)

STATUS = ElectionStatus(constitutional_deadline=date(2027, 12, 18), source="Constitution")


@pytest.fixture
def sample_bills_model() -> BillsPageModel:
    return BillsPageModel(
        bills=(TEST_BILL_1, TEST_BILL_2, TEST_BILL_3),
        updated_at=date(2026, 8, 26),
        sources_count=12,
        status=STATUS,
    )


def test_bills_page_model_computes_stats(sample_bills_model: BillsPageModel):
    assert sample_bills_model.total_bills == 3
    assert sample_bills_model.passed_bills_count == 1
    assert sample_bills_model.committee_bills_count == 1


def test_bills_page_model_from_storage(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("lpa.config.load_election_status", lambda: STATUS)
    monkeypatch.setattr("lpa.storage.load_projections", lambda engine: [])
    monkeypatch.setattr("lpa.storage.load_sentiment_snapshots", lambda engine: [])
    monkeypatch.setattr("lpa.politikku_bills.load_bills", lambda: {"D.R.1/2026": TEST_BILL_1})

    model = bills_page_model(MagicMock())
    assert model.total_bills == 1
    assert model.status == STATUS


def test_render_bills_page_en(sample_bills_model: BillsPageModel):
    html_doc = render_bills_page(sample_bills_model, Language.EN)
    assert "<!doctype html>" in html_doc
    assert '<html lang="en">' in html_doc
    assert "Bills in the Dewan Rakyat" in html_doc
    assert "RUU Perlembagaan (Pindaan) 2026" in html_doc
    assert "Passed" in html_doc
    assert "Division 148–74" in html_doc
    assert "Referred to Committee" in html_doc
    assert "Failed to secure 2/3 majority at Second Reading" in html_doc
    assert "Voice vote" in html_doc
    assert "pk-bill-dot-fail" in html_doc


def test_render_bills_page_ms(sample_bills_model: BillsPageModel):
    html_doc = render_bills_page(sample_bills_model, Language.MS)
    assert '<html lang="ms">' in html_doc
    assert "Rang Undang-Undang di Dewan Rakyat" in html_doc
    assert "RUU Kebebasan Maklumat 2026" in html_doc
    assert "Lulus" in html_doc
    assert "Belah bahagian 148–74" in html_doc
    assert "Undian suara" in html_doc


def test_build_and_write_bills_pages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("lpa.config.load_election_status", lambda: STATUS)
    monkeypatch.setattr("lpa.storage.load_projections", lambda engine: [])
    monkeypatch.setattr("lpa.storage.load_sentiment_snapshots", lambda engine: [])
    monkeypatch.setattr("lpa.politikku_bills.load_bills", lambda: {"D.R.1/2026": TEST_BILL_1})

    en_len, ms_len = build_and_write_bills_pages(MagicMock(), tmp_path)
    assert en_len > 0
    assert ms_len > 0
    assert (tmp_path / "bills.html").exists()
    assert (tmp_path / "ms" / "bills.html").exists()
