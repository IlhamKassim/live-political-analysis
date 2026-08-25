"""The PolitikKu site shell: header, trust strip, EN/BM toggle, footer.

Structural/string-membership tests, matching `test_public_page.py`'s
discipline — the markup is covered where a rendering bug would put a wrong
or unescaped claim on the page, not pixel-for-pixel against the mockup.
"""

from datetime import date

from lpa.domain import ElectionStatus
from lpa.politikku_shell import (
    NAV_LINKS,
    PROJECTION_PREFIX,
    Language,
    methodology_url,
    projection_url,
    render_header,
    render_methodology_footer,
    render_shell,
    render_trust_strip,
    route,
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
    # The nav renders twice (desktop + mobile disclosure); "active" must
    # land on Bills in both renderings and nowhere else.
    assert header.count('class="active"') == 2
    assert len(NAV_LINKS) > 1  # otherwise the count above would be trivially true


def test_the_projection_nav_item_points_at_politikkus_own_projection_page():
    # #102/ADR 0011 supersede #70's "stand alongside" resolution: the old
    # chamber dashboard at `/` is no longer any nav item's target, and
    # "Seat Projection" now means `politikku_projection.py`'s own page at
    # `PROJECTION_PREFIX` — a directory route, so its `href` is the empty
    # page path, the same shape the Home item uses for `/politikku/`.
    projection_link = next(link for link in NAV_LINKS if link.key == "projection")
    assert projection_link.prefix == PROJECTION_PREFIX
    assert projection_link.href == ""
    assert projection_url() == "/projection/"
    assert projection_url(Language.MS) == "/projection/ms/"


def test_a_localized_nav_link_stays_in_bm_not_just_the_toggle():
    # #81's own requirement ("persisted... drives /ms/ routes") extends to
    # in-site navigation: a BM page's Bills nav item must stay in BM, not
    # silently drop back to the EN route.
    header = render_header(active_nav="home", language=Language.MS, page_path="")
    # Nav renders twice (desktop + mobile) — the Bills nav link (not the
    # toggle) must be the /ms/ route in both, and the plain EN route must
    # appear nowhere except the toggle's own EN link.
    assert header.count('">Rang Undang-Undang</a>') == 2
    assert 'href="/politikku/ms/bills.html">Rang Undang-Undang</a>' in header
    assert 'href="/politikku/bills.html">Rang Undang-Undang</a>' not in header


def test_no_nav_link_opts_out_of_language_routing():
    # The `localized: bool` flag `NavLink.prefix` replaced existed for one
    # item only — the un-translated chamber dashboard at `/`, which #102
    # replaced with a page that has a real BM sibling. So there is no longer
    # any nav item whose BM href is its EN href: every link, whichever route
    # family it hangs off, goes through `/ms/` from a BM page.
    en_header = render_header(active_nav="home", language=Language.EN, page_path="")
    ms_header = render_header(active_nav="home", language=Language.MS, page_path="")
    assert 'href="/"' not in ms_header
    for link in NAV_LINKS:
        assert f'href="{link.prefix}{link.href}"' in en_header
        assert f'href="{link.prefix}ms/{link.href}"' in ms_header


def test_the_methodology_and_projection_urls_are_language_aware():
    # Before #102 the BM footer/trust strip linked the *English* methodology
    # page — invisible only because no methodology page existed in either
    # language. Both helpers now route through the current language.
    assert methodology_url() == "/politikku/methodology.html"
    assert methodology_url(Language.MS) == "/politikku/ms/methodology.html"
    assert route(Language.MS, "bills.html") == "/politikku/ms/bills.html"


def test_the_language_persistence_script_compares_the_pages_own_route_family():
    # A page served from `PROJECTION_PREFIX` has to compare its own prefix,
    # or a stored BM preference would silently no-op there (#102).
    kwargs = {
        "title": "x",
        "active_nav": "projection",
        "language": Language.EN,
        "page_path": "",
        "updated_at": date(2026, 8, 23),
        "sources_count": 3,
        "status": NOT_CALLED,
        "body_html": "<main></main>",
    }
    politikku = render_shell(**kwargs)  # type: ignore[arg-type]
    projection = render_shell(**kwargs, prefix=PROJECTION_PREFIX)  # type: ignore[arg-type]

    assert "'/politikku/ms/'" in politikku
    assert "'/projection/ms/'" in projection
    assert "'/politikku/ms/'" not in projection


def test_the_wordmark_stays_in_the_current_language():
    en_header = render_header(active_nav="home", language=Language.EN, page_path="")
    ms_header = render_header(active_nav="home", language=Language.MS, page_path="")
    assert '<a class="wordmark" href="/politikku/">PolitikKu</a>' in en_header
    assert '<a class="wordmark" href="/politikku/ms/">PolitikKu</a>' in ms_header


def test_the_language_persistence_script_is_present_and_reads_localstorage():
    header = render_shell(
        title="x",
        active_nav="home",
        language=Language.EN,
        page_path="",
        updated_at=date(2026, 8, 23),
        sources_count=1,
        status=NOT_CALLED,
        body_html="<p>body</p>",
    )
    assert "pk-language" in header
    assert "localStorage" in header
    assert "data-pk-set-lang" in header


def test_the_language_toggle_marks_the_current_language_and_links_the_other():
    # The toggle links also carry `data-pk-set-lang` (#81's persistence
    # script reads it on click) between `aria-current` and the label — so
    # these check substrings that survive that addition, not the exact
    # historical tag text.
    en_page = render_header(active_nav="home", language=Language.EN, page_path="bills.html")
    assert 'class="lang-current" href="/politikku/bills.html" aria-current="page"' in en_page
    assert 'data-pk-set-lang="en"' in en_page
    assert 'href="/politikku/ms/bills.html" data-pk-set-lang="ms">BM</a>' in en_page

    ms_page = render_header(active_nav="home", language=Language.MS, page_path="bills.html")
    assert 'href="/politikku/bills.html" data-pk-set-lang="en">EN</a>' in ms_page
    assert 'class="lang-current" href="/politikku/ms/bills.html" aria-current="page"' in ms_page
    assert 'data-pk-set-lang="ms"' in ms_page


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

    hostile = SourceGroup("Factual data", "Data faktual", ("</div><script>alert(1)</script>",))
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


# ── #81: bilingual copy ──────────────────────────────────────────────────


def test_t_picks_english_for_en_and_bm_for_ms():
    from lpa.politikku_shell import t

    assert t(Language.EN, "Home", "Utama") == "Home"
    assert t(Language.MS, "Home", "Utama") == "Utama"


def test_the_nav_labels_translate_in_bm_and_stay_english_by_default():
    en_header = render_header(active_nav="bills", language=Language.EN, page_path="")
    ms_header = render_header(active_nav="bills", language=Language.MS, page_path="")

    assert ">Bills</a>" in en_header
    assert ">Rang Undang-Undang</a>" in ms_header
    assert ">Bills</a>" not in ms_header


def test_the_trust_strip_translates_the_updated_word_and_status_sentence():
    ms_strip = render_trust_strip(
        updated_at=date(2026, 8, 23), sources_count=9, status=NOT_CALLED, language=Language.MS
    )
    assert "Dikemas kini 23 Aug 2026, MYT" in ms_strip
    assert "PRU16 belum diisytiharkan" in ms_strip
    assert "sumber berita dibaca" in ms_strip
    assert "Cara ini berfungsi" in ms_strip
    # English words the BM strip must not carry over verbatim.
    assert "Updated 23 Aug 2026" not in ms_strip
    assert "GE16 not yet called" not in ms_strip


def test_the_footer_heading_is_the_settled_bm_pair():
    footer = render_methodology_footer(language=Language.MS)
    assert "Metodologi &amp; sumber" in footer
    assert "Baca metodologi penuh" in footer
    # Source citations stay untranslated in both languages.
    assert "Election Commission (SPR)" in footer


def test_the_full_shell_in_bm_carries_no_leftover_english_chrome_copy():
    page = render_shell(
        title="Halaman ujian",
        active_nav="home",
        language=Language.MS,
        page_path="",
        updated_at=date(2026, 8, 23),
        sources_count=9,
        status=NOT_CALLED,
        body_html="<main>isi</main>",
    )
    assert ">Utama</a>" in page  # translated "Home" nav item
    assert "Metodologi &amp; sumber" in page
    for english_only in ("Home", "How this works", "Read the full methodology"):
        assert english_only not in page
