"""The PolitikKu site shell: header, trust strip, EN/BM toggle, footer.

Structural/string-membership tests, matching `test_public_page.py`'s
discipline — the markup is covered where a rendering bug would put a wrong
or unescaped claim on the page, not pixel-for-pixel against the mockup.
"""

from datetime import date

from lpa.domain import ElectionStatus
from lpa.politikku_shell import (
    NAV_LINKS,
    Language,
    render_header,
    render_methodology_footer,
    render_shell,
    render_trust_strip,
    trust_strip_status_text,
)

NOT_CALLED = ElectionStatus(constitutional_deadline=date(2028, 2, 17), source="x")
CALLED_NO_POLLING = ElectionStatus(
    constitutional_deadline=date(2028, 2, 17), source="x", dissolved_on=date(2026, 10, 1)
)
CALLED_WITH_POLLING = ElectionStatus(
    constitutional_deadline=date(2028, 2, 17),
    source="x",
    dissolved_on=date(2026, 10, 1),
    polling_date=date(2026, 11, 8),
)


def test_the_three_election_statuses_each_get_their_own_compact_line():
    assert trust_strip_status_text(NOT_CALLED) == (
        "GE16 not yet called — constitutional deadline 17 Feb 2028"
    )
    assert "dissolved 1 Oct 2026" in trust_strip_status_text(CALLED_NO_POLLING)
    assert "polling day not yet announced" in trust_strip_status_text(CALLED_NO_POLLING)
    assert trust_strip_status_text(CALLED_WITH_POLLING) == "GE16 called — polling 8 Nov 2026"


def test_the_active_nav_link_is_the_only_one_marked_current():
    header = render_header(active_nav="bills", language=Language.EN, page_path="")

    # The nav is rendered twice (desktop row + mobile disclosure, only one
    # visible at a time via CSS), so the active link's aria-current appears
    # twice, plus once more for the current EN toggle link.
    assert header.count('aria-current="page"') == 3
    assert '<a class="active" href="/politikku/bills.html" aria-current="page">Bills</a>' in header
    for link in NAV_LINKS:
        if link.key != "bills":
            assert f'class="active" href="{link.href}"' not in header


def test_the_projection_nav_item_points_at_the_existing_dashboard_not_a_new_page():
    # #70: the new pages stand alongside the dashboard rather than replacing
    # it, and the dashboard already is the full seat-level projection page.
    projection_link = next(link for link in NAV_LINKS if link.key == "projection")
    assert projection_link.href == "/"


def test_the_language_toggle_marks_the_current_language_and_links_the_other():
    en_page = render_header(active_nav="home", language=Language.EN, page_path="bills.html")
    assert 'class="lang-current" href="/politikku/bills.html" aria-current="page">EN</a>' in en_page
    assert 'href="/politikku/ms/bills.html">BM</a>' in en_page

    ms_page = render_header(active_nav="home", language=Language.MS, page_path="bills.html")
    assert 'href="/politikku/bills.html">EN</a>' in ms_page
    assert 'class="lang-current" href="/politikku/ms/bills.html" aria-current="page">BM</a>' in ms_page


def test_the_trust_strip_states_sources_singular_and_plural_correctly():
    one = render_trust_strip(updated_at=date(2026, 8, 23), sources_count=1, status=NOT_CALLED)
    assert "1 news source read" in one

    many = render_trust_strip(updated_at=date(2026, 8, 23), sources_count=9, status=NOT_CALLED)
    assert "9 news sources read" in many


def test_the_trust_strip_never_states_a_clock_time_it_cannot_verify():
    # The handoff's mockup invents "06:00 MYT"; PageModel only ever carries a
    # date, and the real Action runs at 23:00 MYT, not 06:00 — so the strip
    # must not assert a specific time it has no source for (trust rule 2).
    strip = render_trust_strip(updated_at=date(2026, 8, 23), sources_count=9, status=NOT_CALLED)
    assert "06:00" not in strip
    assert "23 Aug 2026, MYT" in strip


def test_the_footer_carries_both_source_columns_and_the_not_calibrated_span():
    footer = render_methodology_footer()
    assert "Election Commission (SPR)" in footer
    assert "Dewan Rakyat Hansard" in footer
    assert "Merdeka Center polling" in footer
    assert '<span class="pk-not-calibrated">not calibrated</span>' in footer


def test_a_source_name_carrying_markup_cannot_break_out_of_the_footer():
    from lpa.politikku_shell import SourceGroup

    hostile = SourceGroup("Factual data", ("</div><script>alert(1)</script>",))
    footer = render_methodology_footer(factual=hostile)

    assert "<script>" not in footer
    assert "&lt;script&gt;" in footer


def test_the_shell_escapes_the_page_title():
    page = render_shell(
        title="Bills & motions </title>",
        active_nav="bills",
        language=Language.EN,
        page_path="bills.html",
        updated_at=date(2026, 8, 23),
        sources_count=9,
        status=NOT_CALLED,
        body_html="<main>placeholder</main>",
    )
    assert "<title>Bills &amp; motions &lt;/title&gt;</title>" in page
    assert '<html lang="en">' in page
    assert "<main>placeholder</main>" in page
    assert "newsreader-variable.woff2" in page


def test_the_shell_sets_the_bahasa_malaysia_lang_attribute():
    page = render_shell(
        title="Bil",
        active_nav="bills",
        language=Language.MS,
        page_path="bills.html",
        updated_at=date(2026, 8, 23),
        sources_count=9,
        status=NOT_CALLED,
        body_html="",
    )
    assert '<html lang="ms">' in page
