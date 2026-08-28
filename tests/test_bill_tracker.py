"""Bill Tracker, and the shipped register coverage (issues #80, #106).

Split the way `test_mp_profile.py` is: the loader against synthetic
fixtures, the register parser against a fixture built to reproduce a real
parsing failure (see `parse_register`'s docstring), and the shipped record
against what its real sources say — structurally, never a hardcoded copy of
a real figure, which would pass just as happily if the figure were invented.
"""

import json
from datetime import date

import pytest
from build_bill_tracker import (
    build_bill,
    parse_register,
    sync_bills,
)

from lpa.bill_tracker import DivisionResult, missing_fields, unexplained_fields
from lpa.config import load_bills

DIVISION = {
    "sitting_date": "2025-08-28",
    "ayes": 125,
    "noes": 63,
    "abstentions": 1,
    "absent": 32,
    "outcome": "Dibacakan kali kedua",
    "hansard_url": "https://hansard.parlimen.gov.my/hansard/dewan-rakyat/2025-08-28",
}

# Everything a Bill must carry, with nothing optional left out.
COMPLETE = {
    "title": "RUU Ujian 2025",
    "year": 2025,
    "stage": "Lulus",
    "stage_date": "2025-08-28",
    "summary": "Rang Undang-Undang ini bertujuan untuk mengadakan peruntukan ujian.",
    "summary_source_url": "https://www.parlimen.gov.my/files/billindex/pdf/2025/DR/test.pdf#page=1",
    "division": DIVISION,
    "unverified": {},
}


def write_bills(tmp_path, bills):
    path = tmp_path / "bills.json"
    path.write_text(json.dumps({"bills": bills}))
    return path


def test_the_loader_reads_a_complete_bill(tmp_path):
    bills = load_bills(write_bills(tmp_path, {"D.R.1/2025": COMPLETE}))

    bill = bills["D.R.1/2025"]
    assert bill.code == "D.R.1/2025"
    assert bill.stage_date.isoformat() == "2025-08-28"
    assert bill.division is not None
    assert bill.division.ayes == 125
    assert missing_fields(bill) == ()


def test_the_loader_rejects_a_bill_with_no_division_and_no_reason(tmp_path):
    entry = {**COMPLETE, "division": None}

    with pytest.raises(ValueError, match="division"):
        load_bills(write_bills(tmp_path, {"D.R.1/2025": entry}))


def test_the_loader_accepts_a_bill_with_no_division_that_says_why(tmp_path):
    entry = {
        **COMPLETE,
        "division": None,
        "unverified": {"division": "Passed on a voice vote; no recorded Division."},
    }

    bill = load_bills(write_bills(tmp_path, {"D.R.1/2025": entry}))["D.R.1/2025"]

    assert bill.division is None
    assert missing_fields(bill) == ("division",)
    assert unexplained_fields(bill) == ()


def test_a_division_result_rejects_more_members_than_the_house_has():
    with pytest.raises(ValueError, match="more than"):
        DivisionResult(**{**DIVISION, "sitting_date": date(2025, 8, 28), "absent": 200})


def test_a_division_result_rejects_a_negative_tally():
    with pytest.raises(ValueError, match="negative"):
        DivisionResult(**{**DIVISION, "sitting_date": date(2025, 8, 28), "noes": -1})


# Two rows shaped like the real register: each has its own detail popup
# embedded as a sibling <div> inside the status cell, and a naive
# text-flattening parse would interleave Row A's popup with Row B's visible
# cells (or vice versa) because the popups aren't nested inside their own
# row's boundary in a way flattening respects. Row-by-row parsing must keep
# each field with the row it actually belongs to.
def _row(code, title, minister, second_reading, passed):
    return f"""
<tr class="maintable">
  <td align="center" scope="row" class="maintd">
    <a href="#" onclick="loadResult('/files/billindex/pdf/2025/DR/{code}.pdf','{code}.pdf');">{code}</a>
  </td>
  <td align="center" class="maintd">2025</td>
  <td class="maintd">{title}</td>
  <td class="maintd" style="position: relative;">
    <div class="parent ruustatus3" id="row1">Lulus</div>
    <div class="alertBox child-row1" id="ruudiv-row1">
      <table>
        <tr><td>Bacaan Pertama Pada</td><td>:</td><td>01/01/2025</td></tr>
        <tr><td>Bacaan Kedua Pada</td><td>:</td><td>{second_reading}</td></tr>
        <tr><td>Dibentang Oleh</td><td>:</td><td>{minister}</td></tr>
        <tr><td>Diluluskan Pada</td><td>:</td><td>{passed}</td></tr>
        <tr><td>Dibentang Oleh</td><td>:</td><td>{minister}</td></tr>
      </table>
    </div>
  </td>
</tr>
"""


REGISTER_FIXTURE = _row(
    "D.R.1/2025", "RUU Satu 2025", "YB Menteri A", "02/01/2025", "03/01/2025"
) + _row("D.R.2/2025", "RUU Dua 2025", "YB Menteri B", "05/01/2025", "06/01/2025")


def test_register_parsing_keeps_each_row_with_its_own_fields():
    bills = parse_register(REGISTER_FIXTURE)

    assert bills["D.R.1/2025"]["title"] == "RUU Satu 2025"
    assert bills["D.R.1/2025"]["passed"] == "03/01/2025"
    assert bills["D.R.2/2025"]["title"] == "RUU Dua 2025"
    assert bills["D.R.2/2025"]["passed"] == "06/01/2025"
    # The failure mode this guards against: a broken parse would have Row 1
    # picking up Row 2's minister or passage date, or vice versa.
    assert bills["D.R.1/2025"]["pdf_path"] == "/files/billindex/pdf/2025/DR/D.R.1/2025.pdf"
    assert bills["D.R.2/2025"]["pdf_path"] == "/files/billindex/pdf/2025/DR/D.R.2/2025.pdf"


def test_register_parsing_raises_on_a_page_with_no_bill_rows():
    with pytest.raises(ValueError, match="no Bill rows"):
        parse_register("<html><body>nothing here</body></html>")


SHIPPED_BILLS = load_bills()

PLACEHOLDER_WORDS = ("tbd", "tba", "todo", "fixme", "lorem", "ipsum", "placeholder", "sample")


def test_every_shipped_bill_explains_every_field_it_leaves_unset():
    for code, bill in SHIPPED_BILLS.items():
        assert unexplained_fields(bill) == (), code


def test_no_shipped_bill_holds_a_placeholder_rather_than_a_value():
    for code, bill in SHIPPED_BILLS.items():
        for value in (bill.title, bill.stage, bill.summary):
            lowered = value.lower()
            assert not any(word in lowered for word in PLACEHOLDER_WORDS), f"{code}: {value!r}"


def test_most_shipped_summaries_are_parliaments_own_purpose_sentence():
    # Not a hard requirement of the schema — a Bill whose HURAIAN opens with
    # something other than its purpose (a constitutional citation, say)
    # falls back to its literal first sentence instead, still verbatim, per
    # ADR 0010 — but true of most Bills' HURAIAN sections, and a cheap check
    # that the "bertujuan" search itself did not regress to matching nothing.
    with_bertujuan = sum(
        1 for bill in SHIPPED_BILLS.values() if "bertujuan" in bill.summary.lower()
    )
    assert with_bertujuan / len(SHIPPED_BILLS) >= 0.7


def test_every_shipped_summary_source_points_at_a_pdf_page():
    for code, bill in SHIPPED_BILLS.items():
        assert bill.summary_source_url.endswith(".pdf") or "#page=" in bill.summary_source_url, code


def test_every_shipped_division_is_consistent_with_its_bills_own_stage_date():
    # A Bill's Division, where one exists, is the same event as its second
    # or third reading — the two dates should agree.
    for code, bill in SHIPPED_BILLS.items():
        if bill.division is not None:
            assert bill.division.sitting_date == bill.stage_date, code


def test_the_shipped_bills_carry_at_least_one_with_a_division_and_one_without():
    # Both shapes of the schema must be exercised by real data.
    has_division = [c for c, b in SHIPPED_BILLS.items() if b.division is not None]
    no_division = [c for c, b in SHIPPED_BILLS.items() if b.division is None]
    assert has_division and no_division


def test_every_shipped_division_is_derived_from_mp_profiles_not_retyped():
    # ADR 0010's central claim: a Bill's Division tally is read from
    # data/mp_profiles.json, not re-transcribed by hand into bills.json. If
    # the two ever drifted, this is the test that would catch it.
    from lpa.config import load_mp_profiles

    p102_divisions = {
        (d.sitting_date, d.ayes, d.noes, d.abstentions, d.absent, d.outcome, d.hansard_url)
        for d in load_mp_profiles()["P.102"].divisions
    }
    for code, bill in SHIPPED_BILLS.items():
        if bill.division is None:
            continue
        key = (
            bill.division.sitting_date,
            bill.division.ayes,
            bill.division.noes,
            bill.division.abstentions,
            bill.division.absent,
            bill.division.outcome,
            bill.division.hansard_url,
        )
        assert key in p102_divisions, f"{code}: division tally has no match in mp_profiles.json"


def test_every_shipped_no_division_reason_matches_the_bills_own_stage():
    # Regression: an earlier version of build_bill() applied one hard-coded
    # "passed on a voice vote" reason to every division-less Bill regardless
    # of stage, which was false for a Bill still in committee. A Bill that
    # has not reached "Lulus" cannot correctly be said to have "passed".
    for code, bill in SHIPPED_BILLS.items():
        if bill.division is not None:
            continue
        reason = bill.unverified["division"].lower()
        if bill.stage != "Lulus":
            assert "passed" not in reason, (
                f"{code}: stage is {bill.stage!r} but reason claims passage"
            )


def test_status_overrides_preserve_manual_withdrawal():
    # D.R.25/2025 was withdrawn by the Cabinet on 2026-01-23 (issue #117)
    row = {
        "code": "D.R.25/2025",
        "year": 2025,
        "title": "RUU Pembaharuan Semula Bandar 2025",
        "status": "Bacaan Kali Pertama",
        "first_reading": "21/08/2025",
        "second_reading": None,
        "referred_jkpk": None,
        "passed": None,
        "pdf_path": "/files/billindex/pdf/2025/DR/test.pdf",
    }
    bill = build_bill("D.R.25/2025", row, "Summary text", "http://example.com/test.pdf#page=1", None)
    assert bill["stage"] == "Ditarik Balik"
    assert bill["stage_date"] == "2026-01-23"
    assert bill["unverified"]["division"] == "Withdrawn by the Cabinet before a vote."


def test_sync_bills_reuses_cached_summary_without_network(monkeypatch):
    register = {
        "D.R.1/2025": {
            "code": "D.R.1/2025",
            "year": 2025,
            "title": "RUU Satu 2025",
            "status": "Lulus",
            "first_reading": "01/01/2025",
            "second_reading": "02/01/2025",
            "referred_jkpk": None,
            "passed": "03/01/2025",
            "pdf_path": "/files/billindex/pdf/2025/DR/D.R.1/2025.pdf",
        }
    }
    existing = {
        "D.R.1/2025": {
            "title": "RUU Satu 2025",
            "year": 2025,
            "stage": "Bacaan Kali Pertama",
            "stage_date": "2025-01-01",
            "summary": "Existing summary text.",
            "summary_source_url": "http://example.com/test.pdf#page=1",
            "division": None,
            "unverified": {
                "division": 'Still at the "Bacaan Kali Pertama" stage per the Bills register.'
            },
        }
    }

    class DummyRobots:
        def is_allowed(self, url):
            return True
        def crawl_delay(self, url):
            return None

    class DummyLimiter:
        def wait_turn(self, url, delay):
            pass

    def fail_if_fetch_called(*args, **kwargs):
        raise AssertionError("PDF fetch should not be called for an existing bill with cached summary")

    monkeypatch.setattr("build_bill_tracker._fetch_summary_resilient", fail_if_fetch_called)

    bills, skipped, diffs = sync_bills(
        register=register,
        existing_bills=existing,
        divisions_by_subject={},
        client=None,  # type: ignore[arg-type]
        robots=DummyRobots(),  # type: ignore[arg-type]
        limiter=DummyLimiter(),  # type: ignore[arg-type]
        full_rebuild=False,
    )

    assert "D.R.1/2025" in bills
    assert bills["D.R.1/2025"]["stage"] == "Lulus"
    assert bills["D.R.1/2025"]["stage_date"] == "2025-01-03"
    assert bills["D.R.1/2025"]["summary"] == "Existing summary text."
    assert len(diffs) == 1
    assert "UPDATED" in diffs[0]
    assert skipped == []

