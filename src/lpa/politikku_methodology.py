"""PolitikKu's methodology page (/methodology.html and /ms/methodology.html).

Houses the colophon and provenance blocks explaining how the GE16 projection
is computed, swing assumptions, and data sources.
"""

from __future__ import annotations

import argparse
import html
from collections.abc import Mapping
from pathlib import Path

from sqlalchemy.engine import Engine

from lpa.politikku_shell import (
    METHODOLOGY_PAGE,
    PROJECTION_PREFIX,
    Language,
    projection_url,
    render_shell,
    t,
)
from lpa.public_page import (
    PageModel,
    _article_counts_line,
    _long_date,
    _permalink_path,
    load_projection_page_model,
    status_sentence,
)

SITE_URL = "https://politikku.my/"


def _permalink_url(model: PageModel, language: Language) -> str:
    """The dated copy of this exact run (#55), as an absolute URL."""
    prefix = PROJECTION_PREFIX.strip("/")
    if language is Language.EN:
        return f"{SITE_URL}{prefix}/{_permalink_path(model.computed_at)}"
    return f"{SITE_URL}ms/{prefix}/{_permalink_path(model.computed_at)}"


def _band(css_class: str, inner: str, *, alt: bool = False) -> str:
    alt_class = " pk-proj-band-alt" if alt else ""
    return f'<section class="pk-proj-band{alt_class} {css_class}">{inner}</section>'


def _colophon(model: PageModel, language: Language) -> str:
    """Method, Read from, Election status, Not calibrated."""
    read_from = " · ".join(html.escape(s) for s in model.sources) or t(
        language, "No outlets read", "Tiada portal berita dibaca"
    )
    articles_in_latest = t(
        language,
        f"{model.article_count} articles in the latest run.",
        f"{model.article_count} artikel dalam larian terkini.",
    )
    cards = (
        (
            t(language, "Method", "Kaedah"),
            t(
                language,
                "A Swing from each Seat's GE15 result, moved by daily News Sentiment "
                "and blended, state by state, with any state election held since. The "
                "Swing is uniform within a state, so a Seat's call is arithmetic against "
                "GE15.",
                "Peralihan daripada keputusan PRU15 setiap Kerusi, digerakkan oleh "
                "Sentimen berita harian dan digabungkan, negeri demi negeri, dengan "
                "mana-mana pilihan raya negeri yang diadakan sejak itu. Peralihan "
                "adalah seragam dalam sesebuah negeri, jadi keputusan sesuatu Kerusi "
                "adalah pengiraan berbanding PRU15.",
            ),
            False,
        ),
        (
            t(language, "Read from", "Dibaca daripada"),
            f"{read_from}. {articles_in_latest}{_article_counts_line(model, language)}",
            False,
        ),
        (
            t(language, "Election status", "Status pilihan raya"),
            html.escape(status_sentence(model.status, language)),
            False,
        ),
        (
            t(language, "Not calibrated", "Belum ditentukur"),
            t(
                language,
                "Two constants in the Swing Model were set by judgement, not fitted to "
                "data. Treat every figure here as a direction, not a forecast.",
                "Dua pemalar dalam Model Peralihan ditetapkan melalui pertimbangan, "
                "bukan disuaipadan kepada data. Anggap setiap angka di sini sebagai "
                "arah, bukan ramalan.",
            ),
            True,
        ),
    )
    return "".join(
        f'<div class="pk-proj-card{" pk-proj-caution" if caution else ""}">'
        f"<h2>{heading}</h2><p>{body}</p></div>"
        for heading, body, caution in cards
    )


def _cite_this(
    model: PageModel,
    language: Language,
    *,
    heading_tag: str = "h3",
) -> str:
    """The provenance block (#55): what to cite, and against exactly which constants."""
    read_from = ", ".join(html.escape(s) for s in model.sources) or t(
        language, "no outlets read", "tiada portal berita dibaca"
    )
    run_date = html.escape(_long_date(model.computed_at, language))
    body = t(
        language,
        f"Model run {run_date}. Swing Model: "
        f"sentiment sensitivity {model.sentiment_sensitivity:.2f}, state signal "
        f"weight {model.state_signal_weight:.2f}. Read from: {read_from}.",
        f"Larian model {run_date}. Model Peralihan: "
        f"kepekaan sentimen {model.sentiment_sensitivity:.2f}, pemberat isyarat "
        f"negeri {model.state_signal_weight:.2f}. Dibaca daripada: {read_from}.",
    )
    link_text = t(language, "A dated copy of this exact run", "Salinan bertarikh larian ini")
    trailer = t(
        language,
        ", unaffected by tomorrow's overwrite.",
        ", tidak terjejas oleh penulisan ganti esok.",
    )
    url = html.escape(_permalink_url(model, language))
    heading = t(language, "Cite this", "Petik ini")
    return (
        '<div class="pk-proj-card pk-proj-cite">'
        f"<{heading_tag}>{heading}</{heading_tag}><p>{body}</p>"
        f'<p><a href="{url}">{link_text}</a>{trailer}</p></div>'
    )


_CSS = """
  .pk-eyebrow {
    font-family: var(--font-mono, monospace);
    font-size: 0.72rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--muted, #64748b);
    margin-bottom: 0.4rem;
  }
  .pk-proj-methodology-hero {
    max-width: 860px;
    margin: 0 auto;
    padding: 3rem 1.5rem 2rem;
  }
  .pk-proj-methodology-hero h1 {
    font-family: var(--font-display, serif);
    font-size: clamp(1.75rem, 3.5vw, 2.5rem);
    font-weight: 700;
    line-height: 1.15;
    margin: 0.25rem 0 1rem;
    letter-spacing: -0.02em;
  }
  .pk-proj-methodology-hero p {
    font-size: 1.05rem;
    line-height: 1.6;
    color: var(--muted, #475569);
    max-width: 68ch;
    margin-bottom: 1.5rem;
  }
  .pk-proj-methodology-link {
    font-weight: 600;
    color: var(--accent, #0284c7);
    text-decoration: none;
  }
  .pk-proj-methodology-link:hover {
    text-decoration: underline;
  }
  .pk-proj-colophon-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 1.25rem;
    max-width: 860px;
    margin: 0 auto;
    padding: 1.5rem;
  }
  .pk-proj-card {
    background: var(--white, #ffffff);
    border: 1px solid var(--line, #e2e8f0);
    border-radius: var(--radius-lg, 0.75rem);
    padding: 1.25rem 1.5rem;
  }
  .pk-proj-card h2 {
    font-size: 1rem;
    font-weight: 700;
    margin: 0 0 0.5rem;
  }
  .pk-proj-card p {
    font-size: 0.92rem;
    line-height: 1.5;
    color: var(--muted, #475569);
    margin: 0;
  }
  .pk-proj-caution {
    border-left: 3px solid var(--caution, #eab308);
  }
  .pk-proj-provenance {
    max-width: 860px;
    margin: 0 auto;
    padding: 1.5rem;
  }
"""


def render_methodology_body(model: PageModel, language: Language = Language.EN) -> str:
    """The methodology page's `body_html`, without the persistent shell."""
    heading = t(
        language,
        "How this projection is built",
        "Bagaimana unjuran ini dibina",
    )
    lede_text = t(
        language,
        "Everything on PolitikKu is either a matter of record with a source beside it, or "
        "the output of an open model that has never been calibrated against survey data. "
        "This page says which is which, and states the exact constants and sources behind "
        "the run currently published.",
        "Semua yang ada di PolitikKu sama ada fakta rasmi dengan sumbernya, atau hasil "
        "model terbuka yang tidak pernah ditentukur terhadap data tinjauan. Halaman ini "
        "menyatakan yang mana satu, serta pemalar dan sumber tepat di sebalik larian yang "
        "diterbitkan sekarang.",
    )
    see_projection = t(
        language,
        "See the full seat projection →",
        "Lihat unjuran kerusi penuh →",
    )
    href = html.escape(projection_url(language))
    hero = _band(
        "pk-proj-methodology-hero",
        f'<div class="pk-eyebrow">{t(language, "Methodology", "Metodologi")}</div>'
        f"<h1>{heading}</h1><p>{lede_text}</p>"
        f'<a class="pk-proj-methodology-link" href="{href}">{see_projection}</a>',
        alt=True,
    )
    colophon = _band(
        "pk-proj-colophon",
        f'<div class="pk-proj-colophon-grid">{_colophon(model, language)}</div>',
    )
    provenance = _band(
        "pk-proj-provenance",
        _cite_this(model, language, heading_tag="h2"),
        alt=True,
    )
    return f"<style>{_CSS}</style>{hero}{colophon}{provenance}"


def render_methodology(model: PageModel, *, language: Language = Language.EN) -> str:
    """The methodology page as one full HTML document, shell included."""
    title = t(
        language,
        "Methodology & sources — PolitikKu",
        "Metodologi & sumber — PolitikKu",
    )
    description = t(
        language,
        "How PolitikKu's GE16 Swing Model works: the Seats, Coalitions, and News "
        "Sentiment sources behind the projection.",
        "Cara Model Peralihan PRU16 PolitikKu berfungsi: Kerusi, Gabungan, dan sumber "
        "Sentimen Berita di sebalik unjuran.",
    )
    return render_shell(
        title=title,
        description=description,
        active_nav="methodology",
        language=language,
        page_path=METHODOLOGY_PAGE,
        updated_at=model.computed_at,
        sources_count=len(model.sources),
        status=model.status,
        body_html=render_methodology_body(model, language),
    )


def build_all_methodology_languages(
    engine_or_model: Engine | PageModel,
) -> Mapping[Language, str]:
    """Render the methodology page in every supported Language."""
    model = (
        load_projection_page_model(engine_or_model)
        if isinstance(engine_or_model, Engine)
        else engine_or_model
    )
    return {lang: render_methodology(model, language=lang) for lang in Language}


def _target(base: Path, language: Language) -> Path:
    if language is Language.EN:
        return base
    return base.parent / "ms" / base.name


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("public") / METHODOLOGY_PAGE,
        help="Where to write the EN methodology HTML.",
    )
    args = parser.parse_args()

    from lpa.storage import connect

    engine = connect()
    model = load_projection_page_model(engine)

    for language in Language:
        target = _target(args.output, language)
        target.parent.mkdir(parents=True, exist_ok=True)
        content = render_methodology(model, language=language)
        target.write_text(content, encoding="utf-8")
        print(f"Wrote {target} ({len(content):,} bytes)")


if __name__ == "__main__":
    main()
