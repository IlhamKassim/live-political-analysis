"""The PolitikKu Observatory landing page at the site root (ADR 0017).

Renders `/` (English) and `/ms/` (Bahasa Malaysia) from the self-authored
Observatory build in `scrollcraft/builds/observatory/`. The build replaces
the previous server-rendered orientation page while keeping the existing
pipeline command, public routes, and live Seat lookup contract. The
interactive map remains one click away at `/app/`.

The page is a full-width public front door with no app chrome. Its 222-seat
chamber animation is explanatory artwork, not a current Coalition count;
the lookup is the live platform feature mounted by `public/lookup.js`.
Static Observatory assets are copied into the generated `public/assets/`
tree during the same build that writes the English and Bahasa pages.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from lpa.bill_tracker import Bill
from lpa.domain import ElectionStatus
from lpa.politikku_shell import (
    APP_URL,
    LANDING_PAGE,
    SITE_URL,
    Language,
    _en_route,
    _ms_route,
    route,
    t,
)

PAGE_PATH = LANDING_PAGE
"""`""` — `route()` resolves it to `/` (EN) and `/ms/` (BM). Taken from the
shell rather than restated so `landing_url()`, this page's own canonical
URL, and its hreflang alternates cannot drift apart."""

"""`APP_URL` is imported from `politikku_shell` rather than restated here:
the map link on this page and the `map` nav item on every other page must
resolve to the same path, and two copies of "/app/" is how they drift."""

PROJECTION_JSON = Path("public/projection.json")
"""Written by `python -m lpa.public_export` earlier in the same workflow
run."""

BILLS_JSON = Path("frontend/public/data/bills.json")
"""The same file `lpa.bill_tracker` reads and `app.js` fetches — read here
too rather than via Storage, for the identical reason that module gives:
two renderings of the same Bill must not be able to disagree."""

TEASER_BILL_COUNT = 2
"""How many Bills the tracker teaser shows. Two, not five: this is a
pointer at `/bills/`, and a longer list starts competing with the Seat
lookup for the same attention."""

@dataclass(frozen=True)
class CoalitionRow:
    """One Coalition's projected Seat total, with the colour the map draws
    it in and whether it sits in the Government Coalition."""

    code: str
    seats: int
    color: str
    government: bool


@dataclass(frozen=True)
class LandingModel:
    """The data backing `/` and `/ms/`.

    Every data-bearing field is independently optional, and each section
    renders only if its own data read succeeded. That is deliberate: a day
    when `public_export` fails should cost the Majority bar and the
    projection teaser, not the Bills teaser, the Seat lookup, the glossary
    or the page. `government_majority` being `None` in particular is not an
    error state to report — the spec is explicit that a first-time visitor
    must not be able to tell a fallback is a fallback, so nothing
    downstream may branch on it to render an apology.
    """

    government_majority: bool | None
    coalitions: tuple[CoalitionRow, ...]
    bills: tuple[Bill, ...]
    majority_threshold: int
    total_seats: int
    updated_at: date
    sources_count: int
    status: ElectionStatus


# ── Reading the data ──────────────────────────────────────────────────────


def _read_projection(
    path: Path = PROJECTION_JSON,
) -> tuple[bool | None, Mapping[str, int], date | None]:
    """`government_majority`, `coalition_seat_totals` and `computed_at`.

    Returns empty/`None` values for every failure mode — no file,
    unreadable file, invalid JSON, missing or wrongly-typed key. The caller
    has one fallback branch per section, not one per failure mode, because
    the page has one fallback rendering per section.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, {}, None
    if not isinstance(raw, dict):
        return None, {}, None

    majority = raw.get("government_majority")
    if not isinstance(majority, bool):
        majority = None

    totals_raw = raw.get("coalition_seat_totals")
    totals: dict[str, int] = {}
    if isinstance(totals_raw, dict):
        # Zero-seat Coalitions are dropped rather than drawn: the export
        # publishes a row for every party it knows about, most of which win
        # nothing, and a 0px bar segment is noise in the legend.
        totals = {
            str(k): int(v)
            for k, v in totals_raw.items()
            if isinstance(v, int) and not isinstance(v, bool) and v > 0
        }

    computed_at: date | None = None
    try:
        computed_at = date.fromisoformat(str(raw["computed_at"]))
    except (KeyError, TypeError, ValueError):
        computed_at = None

    return majority, totals, computed_at


def _coalition_rows(totals: Mapping[str, int]) -> tuple[CoalitionRow, ...]:
    """Totals as drawable rows: Government Coalitions first, each side
    ordered by Seats descending.

    That order is the bar's reading order — safest-Government on the left
    running to safest Non-government on the right — the same single axis
    `CONTEXT.md`'s `Non-government` entry describes the public chamber as
    having.
    """
    if not totals:
        return ()
    from lpa.coalition_colors import party_color
    from lpa.config import load_coalition_config

    try:
        government = frozenset(load_coalition_config()["government_coalitions"])
    except (OSError, KeyError, TypeError, ValueError):
        government = frozenset()

    rows = [
        CoalitionRow(
            code=code,
            seats=seats,
            color=party_color(code),
            government=code in government,
        )
        for code, seats in totals.items()
    ]
    rows.sort(key=lambda r: (not r.government, -r.seats, r.code))
    return tuple(rows)


def _read_bills(path: Path = BILLS_JSON, limit: int = TEASER_BILL_COUNT) -> tuple[Bill, ...]:
    """The most recent Bills by stage date, newest first.

    Same sort key `bills_page_model` uses, so the teaser's two rows are the
    top two rows of `/bills/` and a reader who follows the link sees the
    same Bills in the same order.
    """
    from lpa.config import load_bills

    try:
        bills = load_bills(path)
    except (OSError, KeyError, TypeError, ValueError):
        return ()
    ordered = sorted(bills.values(), key=lambda b: (b.stage_date, b.code), reverse=True)
    return tuple(ordered[:limit])


def _outlets_count() -> int:
    """How many news outlets the Scraper is configured to read.

    The footer's trust language and this count both describe the site, not
    this page. Counted from `data/outlets.json` — the file `CONTEXT.md`'s
    News Sentiment entry names as the record of which outlets are read —
    because this page reads no database. That is the configured set, not a
    per-run tally, which is why this is a documented function rather than
    an inline `len()` that would read as a stronger claim than it is.
    """
    from lpa.config import load_outlets

    try:
        return len(load_outlets())
    except (OSError, KeyError, TypeError, ValueError):
        return 0


def landing_model(
    government_majority: bool | None = None,
    coalitions: Sequence[CoalitionRow] | None = None,
    bills: Sequence[Bill] | None = None,
    updated_at: date | None = None,
    sources_count: int | None = None,
    status: ElectionStatus | None = None,
) -> LandingModel:
    """Build the model for the landing page.

    Every argument defaults to a real read, so `main()` can call this with
    none of them and a test can pass all of them and touch no file — the
    same shape as `bills_page_model`/`sentiment_page_model`.
    """
    from lpa.config import load_coalition_config, load_election_status
    from lpa.domain import TOTAL_SEATS
    from lpa.pipeline import today_in_malaysia

    computed_at: date | None = None
    if government_majority is None or coalitions is None:
        read_majority, totals, computed_at = _read_projection()
        if government_majority is None:
            government_majority = read_majority
        if coalitions is None:
            coalitions = _coalition_rows(totals)

    if bills is None:
        bills = _read_bills()

    if updated_at is None:
        updated_at = computed_at if computed_at is not None else today_in_malaysia()

    if sources_count is None:
        sources_count = _outlets_count()

    if status is None:
        status = load_election_status()

    try:
        threshold = int(load_coalition_config()["majority_threshold"])
    except (OSError, KeyError, TypeError, ValueError):
        threshold = 112

    return LandingModel(
        government_majority=government_majority,
        coalitions=tuple(coalitions),
        bills=tuple(bills),
        majority_threshold=threshold,
        total_seats=TOTAL_SEATS,
        updated_at=updated_at,
        sources_count=sources_count,
        status=status,
    )


# ── The deep-link forwarder ───────────────────────────────────────────────

DEEP_LINK_SCRIPT = """
<script>
(function () {
  try {
    if (location.hash && !/^#(?:top|perspective|chamber|evidence|find)$/.test(location.hash)) {
      location.replace('__APP_URL__' + location.hash); return;
    }
  } catch (e) {}
})();
</script>
"""
"""Forwards SPA fragments to `/app/#<hash>` while preserving Observatory scenes.

Every SPA deep link (`politikku.my/#parlimen/parti`, `/#seat-P.102`) was a
root URL until ADR 0017 moved the SPA to `/app/`. Without this the whole
existing set of shared links, bookmarks and indexed results would land on
the landing page carrying a fragment that means nothing here.

Two properties are load-bearing:

- **It runs before `_language_persistence_script`.** That script redirects
  on `location.pathname` alone, so a deep link reaching it first would
  arrive at `/ms/` with the fragment already dropped. See `render_shell`'s
  `extra_head_script` docstring.
- **`location.replace`, never `.href`.** No extra history entry, so Back
  from `/app/` leaves the site rather than bouncing off the landing page —
  matching every other redirect in this codebase.

**This is deliberately not a gate.** ADR 0017 originally shipped a
`pk-landing-seen` flag in `localStorage` that sent a returning visitor
straight to `/app/`, so the landing page was shown exactly once, plus a
`pk-landing-lang-switch` marker to stop that flag hijacking the language
toggle. Both are gone: the landing page is the site's front door and shows
on every visit to `/`. Do not reintroduce a "seen" flag without reading
ADR 0017's revision note first — the skip is what made the language toggle
unusable, and re-adding it re-adds that bug along with a second piece of
storage state to keep in step.

Anything that fails here fails silently into showing the landing page,
which is the correct page for `/` to show.
"""


def deep_link_script(app_url: str = APP_URL) -> str:
    """`DEEP_LINK_SCRIPT` with its redirect target substituted in."""
    return DEEP_LINK_SCRIPT.replace("__APP_URL__", app_url)


def main() -> None:
    """CLI entry point to render the landing page."""
    parser = argparse.ArgumentParser(description="Render the PolitikKu landing page.")
    parser.add_argument(
        "--output-dir",
        default="public",
        help="Directory to write output files (default: public)",
    )
    args = parser.parse_args()

    en_size, ms_size = build_and_write_landing_pages(args.output_dir)
    print(
        f"Wrote {args.output_dir}/index.html ({en_size:,} bytes) and "
        f"{args.output_dir}/ms/index.html ({ms_size:,} bytes)"
    )


# ── Observatory landing integration ──────────────────────────────────────
#
# The original landing renderer above remains useful as a record of the
# previous orientation page and its data model. The public root now uses the
# Observatory concept as its actual landing page. Keeping this adapter here
# means the pipeline command and its output paths do not change.

_OBSERVATORY_ROOT = Path(__file__).resolve().parents[2] / "scrollcraft" / "builds"
_OBSERVATORY_PAGE = _OBSERVATORY_ROOT / "observatory"
_OBSERVATORY_SHARED = _OBSERVATORY_ROOT / "shared"


def _observatory_body_template() -> str:
    source = (_OBSERVATORY_PAGE / "index.html").read_text(encoding="utf-8")
    match = re.search(r"<body>(.*?)</body>", source, flags=re.DOTALL)
    if not match:
        raise ValueError("The Observatory template has no body")
    return match.group(1)


def _observatory_lookup(language: Language) -> str:
    label = t(language, "Your Malaysian postcode", "Poskod Malaysia anda")
    placeholder = t(language, "e.g. 06050", "cth. 06050")
    search = t(language, "Find your Seat", "Cari kerusi anda")
    locate = t(language, "Use my location", "Guna lokasi saya")
    hint = t(
        language,
        "A postcode can cross Seat boundaries. We'll show every possible match in the verified index.",
        "Satu poskod boleh merentasi sempadan kerusi. Kami akan tunjukkan semua padanan yang mungkin dalam indeks yang disahkan.",
    )
    return f"""<div class="lookup" data-pk-lookup-scope>
<form class="lookup" data-pk-lookup-form role="search" novalidate>
<label class="obs-lookup-label" for="pk-lookup-q">{html.escape(label)}</label>
<div class="obs-input-row">
<input id="pk-lookup-q" name="q" type="search" autocomplete="postal-code" spellcheck="false" maxlength="5" inputmode="numeric" placeholder="{html.escape(placeholder)}" data-pk-lookup-input aria-describedby="pk-lookup-note">
<button class="obs-submit" type="submit" aria-label="{html.escape(search)}"><svg class="ico-arrow" viewBox="0 0 16 16" aria-hidden="true" focusable="false"><path d="M4.5 11.5l7-7M6 4.5h5.5V10" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg></button>
</div>
<button class="obs-locate" type="button" data-pk-locate>{html.escape(locate)}</button>
<p class="lookup-note" id="pk-lookup-note">{html.escape(hint)}</p>
<div class="results pk-lookup-results" data-pk-lookup-results role="status" aria-live="polite" hidden></div>
</form>
</div>"""


def _observatory_header(language: Language) -> str:
    home = _ms_route(PAGE_PATH) if language is Language.MS else _en_route(PAGE_PATH)
    en_class = "on" if language is Language.EN else ""
    ms_class = "on" if language is Language.MS else ""
    home_label = t(language, "PolitikKu home", "Laman utama PolitikKu")
    analyst_link = (
        '<a href="/analyst/">Analyst <span aria-hidden="true"><svg class="ico-arrow" viewBox="0 0 16 16" focusable="false"><path d="M4.5 11.5l7-7M6 4.5h5.5V10" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg></span></a>'
        if language is Language.EN
        else ""
    )
    return f"""<header class="nav wrap">
<a class="brand" href="{html.escape(home)}" aria-label="{html.escape(home_label)}"><svg viewBox="0 0 32 32" width="28" aria-hidden="true"><path d="M3 28V4h8v24M15 28V4h7l7 8-7 8h-7" fill="none" stroke="currentColor" stroke-width="3"/></svg>PolitikKu<span class="brand-small">THE CIVIC OBSERVATORY</span></a>
<nav class="nav-links" id="navigation" aria-label="{html.escape(t(language, "Main navigation", "Navigasi utama"))}"><a href="#perspective">{html.escape(t(language, "The perspective", "Perspektif"))}</a><a href="#chamber">{html.escape(t(language, "The 222 Seats", "222 kerusi"))}</a><a href="#find" class="nav-cta">{html.escape(t(language, "Find your Seat", "Cari kerusi anda"))} <span aria-hidden="true"><svg class="ico-arrow" viewBox="0 0 16 16" focusable="false"><path d="M4.5 11.5l7-7M6 4.5h5.5V10" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg></span></a>{analyst_link}</nav>
<div class="obs-lang" role="group" aria-label="Language"><a class="{en_class}" href="/"{' aria-current="page"' if language is Language.EN else ""} data-pk-set-lang="en">EN</a><a class="{ms_class}" href="/ms/"{' aria-current="page"' if language is Language.MS else ""} data-pk-set-lang="ms">BM</a></div>
<button class="menu-toggle" type="button" aria-controls="navigation" aria-expanded="false">{html.escape(t(language, "Menu", "Menu"))}</button>
</header>"""


_OBSERVATORY_COPY_MS = {
    "A CLEARER VIEW OF MALAYSIAN POLITICS": "PANDANGAN YANG LEBIH JELAS TENTANG POLITIK MALAYSIA",
    "A nation.<br>In perspective.": "Sebuah negara.<br>Dalam perspektif.",
    'Understand the Seats, the people, and the decisions<br class="desktop-break"> that shape the place we call home.': 'Fahami kerusi, rakyat, dan keputusan<br class="desktop-break"> yang membentuk tempat yang kita panggil rumah.',
    "MALAYSIA, SEEN TOGETHER": "MALAYSIA, DILIHAT BERSAMA",
    "Independent. Open source. For everyone.": "Bebas. Sumber terbuka. Untuk semua.",
    "Look a little closer": "Lihat dengan lebih dekat",
    "Politics can feel distant. But it starts with a place you know.": "Politik boleh terasa jauh. Tetapi ia bermula dengan tempat yang anda kenali.",
    "Your street belongs to a Seat. Your Seat sends an MP to Parliament. Together, those Seats shape the country's direction.": "Jalan anda berada dalam sebuah kerusi. Kerusi anda menghantar Ahli Parlimen ke Dewan Rakyat. Bersama-sama, kerusi ini membentuk hala tuju negara.",
    "See how it connects": "Lihat kaitannya",
    "Many places.": "Banyak tempat.",
    "One Parliament.": "Satu Parlimen.",
    "Each point is one Seat.<br>Every Seat has a place in the Dewan Rakyat.": "Setiap titik ialah satu kerusi.<br>Setiap kerusi mempunyai tempat di Dewan Rakyat.",
    "222 SEATS IN THE DEWAN RAKYAT": "222 KERUSI DI DEWAN RAKYAT",
    "Show the Majority threshold": "Tunjukkan ambang Majoriti",
    "112 Seats make a Majority.": "112 kerusi membentuk Majoriti.",
    "An explanation of Parliament.": "Penerangan tentang Parlimen.",
    "Not a current Coalition count.": "Bukan jumlah Gabungan semasa.",
    "A VIEW YOU CAN QUESTION": "PANDANGAN YANG BOLEH DIPERSOALKAN",
    "Follow the source.<br>Form your own view.": "Ikut sumbernya.<br>Bentuk pandangan anda.",
    "Records tell us what happened. Projections estimate what might happen. You should always know which you are reading.": "Rekod memberitahu apa yang telah berlaku. Unjuran menganggarkan apa yang mungkin berlaku. Anda perlu tahu yang mana sedang anda baca.",
    "The Seat map": "Peta kerusi",
    "Find a Seat and explore its GE15 Baseline.": "Cari kerusi dan terokai Baseline GE15-nya.",
    "The parliamentary record": "Rekod Parlimen",
    "Bills and the official record of the Dewan Rakyat.": "Rang Undang-Undang dan rekod rasmi Dewan Rakyat.",
    "The method, in the open": "Kaedah, secara terbuka",
    "How a Projection is built, and where it is limited.": "Cara Unjuran dibina dan batasannya.",
    "Seat Calls are model-driven and not calibrated against survey data. A Projection is an estimate, not an election result.": "Seat Call dijana oleh model dan belum ditentukur dengan data tinjauan. Unjuran ialah anggaran, bukan keputusan pilihan raya.",
    "START WITH SOMEWHERE FAMILIAR": "MULAKAN DENGAN TEMPAT YANG DIKENALI",
    "The bigger picture<br>starts <em>here.</em>": "Gambaran lebih besar<br>bermula <em>di sini.</em>",
    "Five digits. Your place in the story.": "Lima angka. Tempat anda dalam cerita.",
    "Or explore all 222 Seats": "Atau terokai semua 222 kerusi",
    "Made for a more informed Malaysia.": "Untuk Malaysia yang lebih berpengetahuan.",
    "Explore Suara": "Terokai peta",
    "Decorative artwork · Seat index snapshot: 26 August 2026": "Karya hiasan · Lookup menggunakan indeks Poskod → Seat yang disahkan",
}


def _translate_observatory_body(body: str, language: Language) -> str:
    if language is Language.EN:
        return body
    for source, target in _OBSERVATORY_COPY_MS.items():
        body = body.replace(source, target)
    return body


def _observatory_body(model: LandingModel, language: Language) -> str:
    body = _observatory_body_template()
    header_start = body.index('<header class="nav wrap">')
    header_end = body.index("</header>", header_start) + len("</header>")
    body = body[:header_start] + _observatory_header(language) + body[header_end:]

    form_start = body.index('<form class="lookup" novalidate>')
    form_end = body.index("</form>", form_start) + len("</form>")
    body = body[:form_start] + _observatory_lookup(language) + body[form_end:]
    body = body.replace('src="assets/skyline.png"', 'src="/assets/observatory/skyline.png"')
    body = body.replace("https://politikku.my/app/", APP_URL)
    body = body.replace("https://politikku.my/bills/", route(language, "bills/"))
    body = body.replace(
        "https://politikku.my/methodology.html", route(language, "methodology.html")
    )
    body = body.replace('href="../suara/"', f'href="{APP_URL}"')
    body = body.replace(
        "Explore Suara",
        t(language, "Explore the map", "Terokai peta"),
    )
    body = body.replace(
        "Design edition · Decorative AI-generated city artwork · Seat index snapshot: 26 August 2026",
        "Decorative artwork · Seat index snapshot: 26 August 2026",
    )
    body = _translate_observatory_body(body, language)
    body = body.replace(
        'href="/methodology.html"',
        f'href="{html.escape(route(language, "methodology.html"))}"',
    )
    return body.strip()


def _copy_observatory_assets(output_dir: Path) -> None:
    target = output_dir / "assets" / "observatory"
    target.mkdir(parents=True, exist_ok=True)
    assets = (
        (_OBSERVATORY_PAGE / "style.css", target / "style.css"),
        (_OBSERVATORY_PAGE / "integrated.js", target / "integrated.js"),
        (_OBSERVATORY_PAGE / "scrollcraft.js", target / "scrollcraft.js"),
        (_OBSERVATORY_PAGE / "scrollcraft.css", target / "scrollcraft.css"),
        (_OBSERVATORY_PAGE / "assets" / "skyline.png", target / "skyline.png"),
        (_OBSERVATORY_PAGE / "icon.svg", target / "icon.svg"),
        (_OBSERVATORY_SHARED / "base.css", target / "base.css"),
        (_OBSERVATORY_SHARED / "sans.woff2", target / "sans.woff2"),
        (_OBSERVATORY_SHARED / "serif.woff2", target / "serif.woff2"),
        (_OBSERVATORY_SHARED / "grotesk.woff2", target / "grotesk.woff2"),
    )
    for source, destination in assets:
        if not source.is_file():
            raise ValueError(f"Missing Observatory asset: {source}")
        shutil.copy2(source, destination)


def render_landing_body(model: LandingModel, language: Language = Language.EN) -> str:
    """Render the Observatory scenes with the platform's live Seat lookup."""
    return _observatory_body(model, language)


def render_landing_page(model: LandingModel, language: Language = Language.EN) -> str:
    """Render the Observatory as the complete public root document."""
    title = t(
        language,
        "PolitikKu — The civic observatory",
        "PolitikKu — Balai cerap sivik",
    )
    description = t(
        language,
        "A clearer view of Malaysian politics. Explore 222 Seats, understand the Majority, and find your Seat.",
        "Pandangan yang lebih jelas tentang politik Malaysia. Terokai 222 kerusi, fahami Majoriti, dan cari kerusi anda.",
    )
    escaped_title = html.escape(title)
    escaped_description = html.escape(description)
    page_url = f"{SITE_URL.rstrip('/')}{_ms_route(PAGE_PATH) if language is Language.MS else _en_route(PAGE_PATH)}"
    return f"""<!doctype html>
<html lang="{"ms" if language is Language.MS else "en"}">
<head>
<meta charset="utf-8">
{deep_link_script()}
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#101e23">
<meta name="description" content="{escaped_description}">
<meta property="og:title" content="{escaped_title}">
<meta property="og:description" content="{escaped_description}">
<meta property="og:url" content="{html.escape(page_url)}">
<meta property="og:type" content="website">
<link rel="canonical" href="{html.escape(page_url)}">
<link rel="alternate" hreflang="en" href="{html.escape(SITE_URL)}">
<link rel="alternate" hreflang="ms" href="{html.escape(SITE_URL.rstrip("/") + "/ms/")}">
<link rel="icon" href="/favicon.ico?v=3" sizes="any">
<link rel="icon" href="/app/assets/icon.svg?v=3" type="image/svg+xml">
<link rel="icon" type="image/png" sizes="32x32" href="/app/assets/icon-32x32.png?v=3">
<link rel="icon" type="image/png" sizes="16x16" href="/app/assets/icon-16x16.png?v=3">
<link rel="apple-touch-icon" sizes="180x180" href="/app/assets/apple-touch-icon.png?v=3">
<link rel="preload" href="/assets/observatory/grotesk.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="/assets/observatory/base.css">
<link rel="stylesheet" href="/assets/observatory/scrollcraft.css">
<link rel="stylesheet" href="/assets/observatory/style.css">
<title>{escaped_title}</title>
</head>
<body class="pk-bare">
{render_landing_body(model, language)}
<script defer src="/assets/observatory/scrollcraft.js"></script>
<script defer src="/assets/observatory/integrated.js"></script>
<script type="module" src="/lookup.js"></script>
</body>
</html>"""


def build_and_write_landing_pages(output_dir: Path | str = "public") -> tuple[int, int]:
    """Write the Observatory at `/` and `/ms/`, including its static assets."""
    model = landing_model()
    out = Path(output_dir)
    _copy_observatory_assets(out)
    en_html = render_landing_page(model, Language.EN)
    en_path = out / "index.html"
    en_path.parent.mkdir(parents=True, exist_ok=True)
    en_path.write_text(en_html, encoding="utf-8")
    ms_html = render_landing_page(model, Language.MS)
    ms_path = out / "ms" / "index.html"
    ms_path.parent.mkdir(parents=True, exist_ok=True)
    ms_path.write_text(ms_html, encoding="utf-8")
    return len(en_html.encode("utf-8")), len(ms_html.encode("utf-8"))


if __name__ == "__main__":
    main()
