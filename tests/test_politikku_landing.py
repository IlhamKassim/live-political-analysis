"""The PolitikKu landing page: its data reads, its fallbacks, and the gate.

Structural/string-membership tests, matching `test_politikku_shell.py`'s
discipline — markup is asserted where a rendering bug would put a wrong or
unlabelled claim in front of a first-time visitor, not pixel-for-pixel
against the spec.

Layout is deliberately not tested here. Every string-based proxy for it
(counting elements, matching a font-size) would pass while the page
overflowed and fail on a harmless copy edit. It is a visual check against
`docs/design/landing-page-spec.md`, listed in that spec.
"""

import re
from datetime import date

import pytest

from lpa.bill_tracker import Bill
from lpa.domain import ElectionStatus
from lpa.politikku_landing import (
    APP_URL,
    TEASER_COALITIONS,
    CoalitionRow,
    LandingModel,
    _coalition_rows,
    _read_bills,
    _read_projection,
    gate_script,
    landing_model,
    render_landing_body,
    render_landing_page,
)
from lpa.politikku_shell import Language

STATUS = ElectionStatus(constitutional_deadline=date(2028, 2, 17), source="x")

# The real August 2026 export, trimmed: PH+BN+GPS+GRS = 146 government,
# PN+WARISAN+BEBAS = 76 non-government, 222 total.
ROWS: tuple[CoalitionRow, ...] = (
    CoalitionRow("PH", 75, "#d7263d", True),
    CoalitionRow("BN", 41, "#1f9bd6", True),
    CoalitionRow("GPS", 23, "#b8332e", True),
    CoalitionRow("GRS", 7, "#e8772e", True),
    CoalitionRow("PN", 69, "#15387c", False),
    CoalitionRow("WARISAN", 3, "#16a085", False),
    CoalitionRow("BEBAS", 4, "#8a97a6", False),
)

BILLS: tuple[Bill, ...] = (
    Bill(
        code="D.R.22/2026",
        title="RUU Kumpulan Wang Amanah Negara 2026",
        year=2026,
        stage="Lulus",
        stage_date=date(2026, 7, 16),
        summary="Petikan HURAIAN.",
        summary_source_url="https://www.parlimen.gov.my/x.pdf",
    ),
    Bill(
        code="D.R.21/2026",
        title="RUU Perbekalan Tambahan 2026",
        year=2026,
        stage="Dirujuk ke JKPK",
        stage_date=date(2026, 7, 15),
        summary="Petikan HURAIAN kedua.",
        summary_source_url="https://www.parlimen.gov.my/y.pdf",
    ),
)


def model(
    government_majority: bool | None = True,
    coalitions: tuple[CoalitionRow, ...] = ROWS,
    bills: tuple[Bill, ...] = BILLS,
) -> LandingModel:
    return LandingModel(
        government_majority=government_majority,
        coalitions=coalitions,
        bills=bills,
        majority_threshold=112,
        total_seats=222,
        updated_at=date(2026, 8, 23),
        sources_count=7,
        status=STATUS,
    )


def markup(m: LandingModel, language: Language = Language.EN) -> str:
    """The body with its `<style>` block stripped.

    Every class name on this page appears twice — once in a CSS rule, once
    in the markup — so a bare `in page` check against the whole body
    silently passes on the stylesheet. Assertions about what the page
    *renders* go through here.
    """
    return re.sub(r"<style>.*?</style>", "", render_landing_body(m, language), flags=re.DOTALL)


# ── The page is not inside the app's chrome ───────────────────────────────


def test_the_landing_page_carries_no_app_sidebar_or_topbar():
    # A visitor who has not entered the app yet should not be framed by the
    # app's internal navigation. `chrome=False` is what does this; these
    # ids are the exact things it must stop emitting.
    page = render_landing_page(model())
    for chrome_id in ('id="sidebar"', 'id="topbar"', 'id="sb-map"', 'id="mobile-menu"'):
        assert chrome_id not in page
    assert 'class="pk-bare"' in page
    # Its own header, and the footer, are still there.
    assert 'class="pk-top"' in page
    assert 'class="pk-footer"' in page


def test_other_pages_keep_their_chrome():
    # The chrome opt-out must be landing-page-only — `chrome` defaults to
    # True, so no existing caller changes behaviour.
    from lpa.politikku_shell import render_shell

    page = render_shell(
        title="x",
        description="x",
        active_nav="bills",
        language=Language.EN,
        page_path="bills/",
        updated_at=date(2026, 8, 23),
        sources_count=1,
        status=STATUS,
        body_html="<p>body</p>",
    )
    assert 'id="sidebar"' in page and 'id="topbar"' in page
    assert "<body>" in page  # no pk-bare class on the body element


def test_the_page_header_switches_language_and_persists_the_choice():
    en = render_landing_page(model(), Language.EN)
    ms = render_landing_page(model(), Language.MS)
    for page in (en, ms):
        assert 'href="/" data-pk-set-lang="en"' in page
        assert 'href="/ms/" data-pk-set-lang="ms"' in page
    assert 'href="/" data-pk-set-lang="en" aria-current="page"' in en
    assert 'href="/ms/" data-pk-set-lang="ms" aria-current="page"' in ms


def test_the_page_adds_no_duplicate_landmark():
    body = render_landing_body(model())
    for tag in ("<main", "<header", "<footer", "<nav"):
        assert tag not in body
    page = render_landing_page(model())
    assert page.count("<main") == 1
    assert page.count("<footer") == 1
    assert page.count("<header") == 1


# ── The Seat lookup ───────────────────────────────────────────────────────


def test_the_lookup_renders_the_exact_contract_dom_ts_mounts_onto():
    # ts/src/dom.ts finds a scope, then a form and input inside it, and
    # renders into the results node. Miss any one attribute and the field
    # is inert markup that looks like it works.
    page = render_landing_body(model())
    for attr in (
        "data-pk-lookup-scope",
        "data-pk-lookup-form",
        "data-pk-lookup-input",
        "data-pk-locate",
        "data-pk-lookup-results",
    ):
        assert attr in page, attr


def test_the_lookup_input_has_a_real_label_bound_to_it():
    page = render_landing_body(model())
    assert 'for="pk-lookup-q"' in page
    assert 'id="pk-lookup-q"' in page
    assert 'role="search"' in page


def test_the_lookup_results_area_starts_hidden():
    # dom.ts un-hides it on the first state change. Shipping it visible
    # would flash an empty panel under the field on every page load.
    page = render_landing_body(model())
    assert "data-pk-lookup-results hidden" in page


def test_the_lookup_uses_the_settled_bilingual_copy():
    from lpa.politikku_i18n import (
        POSTCODE_OR_CONSTITUENCY_EN,
        POSTCODE_OR_CONSTITUENCY_MS,
        USE_MY_LOCATION_EN,
        USE_MY_LOCATION_MS,
    )

    en = render_landing_body(model(), Language.EN)
    ms = render_landing_body(model(), Language.MS)
    assert POSTCODE_OR_CONSTITUENCY_EN in en
    assert USE_MY_LOCATION_EN in en
    assert POSTCODE_OR_CONSTITUENCY_MS in ms
    assert USE_MY_LOCATION_MS in ms


def test_the_map_link_does_not_compete_with_the_lookup():
    # The lookup is the primary action; the map is a text link beside it,
    # not a second filled button.
    page = markup(model())
    assert f'class="pk-hero-secondary" href="{APP_URL}"' in page
    assert page.count("pk-search-btn") == 1


# ── The Majority bar ──────────────────────────────────────────────────────


def test_the_bar_segments_sum_to_exactly_one_hundred_percent():
    import re

    page = render_landing_body(model())
    widths = [float(w) for w in re.findall(r'pk-maj-seg" style="width:([\d.]+)%', page)]
    assert len(widths) == len(ROWS)
    assert abs(sum(widths) - 100.0) < 0.001


def test_the_majority_marker_sits_at_the_threshold():
    page = render_landing_body(model())
    # 112 of 222 = 50.4505%
    assert 'class="pk-maj-mark" style="left:50.4505%"' in page
    assert "Majority 112" in page


def test_the_two_sides_split_government_from_non_government():
    m = model()
    assert m.government_seats == 146
    assert m.nongovernment_seats == 76
    assert m.counted_seats == 222
    page = render_landing_body(m)
    assert ">146<" in page
    assert ">76<" in page


def test_the_bar_carries_an_accessible_label_since_it_is_an_image():
    page = render_landing_body(model())
    assert 'role="img"' in page
    assert "Government Coalition 146" in page
    assert "Non-government 76" in page


def test_the_bar_is_labelled_modelled_and_the_bills_are_not():
    # FACT/MODEL, per section. The projection is modelled; Parliament's own
    # register is not.
    page = markup(model())
    proj_tags = page.count("pk-not-calibrated")
    assert proj_tags == 2, "one on the majority call, one on the projection teaser"
    bills_block = page[page.index("pk-bill-rows") :]
    assert "pk-not-calibrated" not in bills_block


def test_coalition_colours_come_from_the_map_s_own_table():
    # Not restated here: a second copy is how the landing page and the map
    # end up disagreeing about what colour PH is.
    from lpa.politikku_politicians import load_coalition_colors

    colors = load_coalition_colors()
    rows = _coalition_rows({"PH": 75, "PN": 69})
    assert {r.code: r.color for r in rows} == {"PH": colors["PH"], "PN": colors["PN"]}


def test_government_membership_comes_from_the_coalition_config():
    from lpa.config import load_coalition_config

    government = set(load_coalition_config()["government_coalitions"])
    rows = _coalition_rows({"PH": 75, "PN": 69, "GPS": 23})
    assert {r.code for r in rows if r.government} == {"PH", "GPS"} & government | (
        {"PH", "GPS"} & government
    )
    assert all(r.government == (r.code in government) for r in rows)


def test_government_coalitions_are_ordered_first_then_by_seats():
    rows = _coalition_rows({"PN": 69, "GRS": 7, "PH": 75, "BN": 41})
    assert [r.code for r in rows] == ["PH", "BN", "GRS", "PN"]


# ── The data previews ─────────────────────────────────────────────────────


def test_the_projection_teaser_shows_the_five_coalitions_that_matter():
    page = markup(model())
    teaser = page[page.index("pk-proj-rows") : page.index("pk-bill-rows")]
    for code in TEASER_COALITIONS:
        assert f">{code}<" in teaser
    # WARISAN has seats but is not one of the five; it belongs to the bar's
    # totals, not to this list.
    assert "WARISAN" not in teaser


def test_the_bills_teaser_shows_parliaments_own_stage_label_verbatim():
    # ADR 0010: `stage` is Parliament's literal status word, in BM, in both
    # languages — never an invented English gloss.
    for language in Language:
        page = render_landing_body(model(), language)
        assert "Lulus" in page
        assert "Dirujuk ke JKPK" in page
        assert "D.R.22/2026" in page


def test_the_bills_teaser_uses_the_same_pill_styling_as_the_bills_page():
    from lpa.politikku_bills import bill_stage_style

    page = render_landing_body(model())
    assert f'class="pill" style="{bill_stage_style("Lulus")}"' in page


def test_sentiment_stays_a_link_because_it_has_no_export_to_preview():
    page = markup(model())
    assert 'href="/sentiment/"' in page
    assert "pk-preview" in page
    # Two panels, not three: a faked third would be the vanity metric the
    # spec forbids.
    assert page.count('class="bento-tile pk-preview"') == 2


# ── Fallbacks ─────────────────────────────────────────────────────────────


def test_no_seat_totals_drops_the_bar_but_keeps_the_call():
    page = markup(model(coalitions=()))
    assert "pk-maj-bar" not in page
    assert "pk-proj-rows" not in page
    assert "projected to hold its Majority" in page
    assert "pk-not-calibrated" in page


def test_no_bills_drops_only_the_bills_panel():
    page = markup(model(bills=()))
    assert "pk-bill-rows" not in page
    assert "pk-proj-rows" in page
    assert "pk-maj-bar" in page


def test_a_total_data_outage_still_renders_a_usable_page():
    # No projection, no bills. The Seat lookup and the glossary need
    # neither, and they are what has to survive.
    page = markup(model(government_majority=None, coalitions=(), bills=()))
    assert "data-pk-lookup-form" in page
    assert "pk-glossary" in page
    assert "pk-previews" not in page


def test_no_fallback_ever_admits_to_being_one():
    for m in (
        model(government_majority=None, coalitions=(), bills=()),
        model(coalitions=()),
        model(bills=()),
    ):
        page = markup(m, Language.EN)
        for word in ("unavailable", "Sorry", "error", "could not", "try again", "no data"):
            assert word not in page


def test_the_call_states_which_way_it_went():
    holds = render_landing_body(model(government_majority=True))
    falls = render_landing_body(model(government_majority=False))
    assert "projected to hold its Majority" in holds
    assert "fall short" not in holds
    assert "projected to fall short of a Majority" in falls


def test_has_live_call_distinguishes_a_false_call_from_no_call():
    # `False` is a real projection — the Government Coalition falling short
    # — and must not be swallowed by a truthiness check into the fallback.
    assert model(government_majority=False).has_live_call is True
    assert model(government_majority=None).has_live_call is False


# ── Reading the exports ───────────────────────────────────────────────────


def test_every_unreadable_projection_is_the_same_case(tmp_path):
    missing = tmp_path / "nope.json"
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{not json", encoding="utf-8")
    wrong_shape = tmp_path / "list.json"
    wrong_shape.write_text("[1, 2, 3]", encoding="utf-8")
    no_key = tmp_path / "nokey.json"
    no_key.write_text('{"computed_at": "2026-08-23"}', encoding="utf-8")
    not_a_bool = tmp_path / "notabool.json"
    not_a_bool.write_text('{"government_majority": "yes"}', encoding="utf-8")

    for path in (missing, invalid, wrong_shape, no_key, not_a_bool):
        majority, totals, _ = _read_projection(path)
        assert majority is None, path.name
        assert totals == {}, path.name


def test_zero_seat_coalitions_are_dropped_from_the_totals(tmp_path):
    # The export publishes a row for every party it knows about, most of
    # which win nothing. A 0px bar segment is noise in the legend.
    path = tmp_path / "p.json"
    path.write_text(
        '{"government_majority": true, "computed_at": "2026-08-23",'
        ' "coalition_seat_totals": {"PH": 75, "MUDA": 0, "PSM": 0, "PN": 69}}',
        encoding="utf-8",
    )
    _, totals, computed = _read_projection(path)
    assert totals == {"PH": 75, "PN": 69}
    assert computed == date(2026, 8, 23)


def test_a_bad_date_does_not_take_the_totals_down_with_it(tmp_path):
    path = tmp_path / "p.json"
    path.write_text(
        '{"government_majority": true, "computed_at": "soon", "coalition_seat_totals": {"PH": 75}}',
        encoding="utf-8",
    )
    majority, totals, computed = _read_projection(path)
    assert (majority, totals, computed) == (True, {"PH": 75}, None)


def test_bills_are_read_newest_first_and_capped(tmp_path):
    path = tmp_path / "nope.json"
    assert _read_bills(path) == ()
    real = _read_bills(limit=2)
    assert len(real) == 2
    assert real[0].stage_date >= real[1].stage_date


def test_landing_model_passes_through_everything_it_is_given():
    built = landing_model(
        government_majority=False,
        coalitions=ROWS,
        bills=BILLS,
        updated_at=date(2026, 8, 23),
        sources_count=7,
        status=STATUS,
    )
    assert built.government_majority is False
    assert built.coalitions == ROWS
    assert built.bills == BILLS
    assert built.updated_at == date(2026, 8, 23)


# ── The gate script ───────────────────────────────────────────────────────


def test_the_gate_script_forwards_a_hash_before_anything_else():
    script = gate_script()
    assert "location.replace(APP + location.hash)" in script
    assert script.index("location.hash") < script.index("pk-landing-seen")


def test_the_gate_script_skips_a_returning_visitor():
    script = gate_script()
    assert "pk-landing-seen" in script
    assert "localStorage" in script
    assert "location.href" not in script
    assert script.count("location.replace") == 2


def test_the_gate_script_does_not_mark_seen_on_a_page_it_is_about_to_leave():
    # The language script runs next and may redirect `/` to `/ms/`. Without
    # this guard a BM reader has the flag set on `/`, gets redirected, and
    # is bounced straight to /app/ — skipping the gate on their first ever
    # visit.
    script = gate_script()
    assert "(stored === 'ms') === onMs" in script
    assert "pk-language" in script


def test_the_gate_script_survives_blocked_storage():
    script = gate_script()
    assert script.count("try {") == script.count("catch (e)")
    assert script.count("try {") >= 3


def test_the_gate_script_runs_before_the_language_script():
    page = render_landing_page(model())
    assert page.index("pk-landing-seen") < page.index("pk-language")


def test_no_other_page_gets_a_gate_script():
    from lpa.politikku_shell import render_shell

    page = render_shell(
        title="x",
        description="x",
        active_nav="bills",
        language=Language.EN,
        page_path="bills/",
        updated_at=date(2026, 8, 23),
        sources_count=1,
        status=STATUS,
        body_html="<p>body</p>",
    )
    assert "pk-landing-seen" not in page


# ── Glossary, metadata, output paths ──────────────────────────────────────


def test_the_glossary_cites_context_md_in_english_only():
    # A Malay translation of an English source is not a verbatim claim
    # against it, and `lpa.citation_check` would only ever fail one.
    en = render_landing_body(model(), Language.EN)
    ms = render_landing_body(model(), Language.MS)
    assert en.count("data-cite=") == 4
    assert "data-cite=" not in ms
    assert "The unit an election is actually won or lost in." in en


def test_both_languages_declare_each_other_as_alternates():
    for page in (
        render_landing_page(model(), Language.EN),
        render_landing_page(model(), Language.MS),
    ):
        assert '<link rel="alternate" hreflang="en" href="https://politikku.my/">' in page
        assert '<link rel="alternate" hreflang="ms" href="https://politikku.my/ms/">' in page


@pytest.mark.parametrize("majority", [True, False, None])
def test_writing_both_pages_lands_at_the_paths_gitignore_names(tmp_path, majority, monkeypatch):
    # `.gitignore` names `public/index.html` and `public/ms/index.html`
    # against this module by name. If the write paths move, those entries
    # stop protecting anything.
    from lpa import politikku_landing

    monkeypatch.setattr(politikku_landing, "landing_model", lambda: model(majority))
    politikku_landing.build_and_write_landing_pages(tmp_path)

    assert (tmp_path / "index.html").is_file()
    assert (tmp_path / "ms" / "index.html").is_file()
    assert "<!doctype html>" in (tmp_path / "index.html").read_text(encoding="utf-8")
