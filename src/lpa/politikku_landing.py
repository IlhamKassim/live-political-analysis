"""PolitikKu landing page: the first-time visitor's decision to trust the
site and route into the lookup (#75).

Full layout spec: `design_handoff_politikku/README.md`, "1. Landing page" —
bands, exact hero copy and the FACT/MODEL panel's *structure* are given
verbatim. Its actual *content* is not: the mockup's own FACT/MODEL panel and
stat strip carry a mix of real and invented sample values (a pattern
Session 2 already found repeatedly — ADR 0008/0009/0010's own leads), and
checking each one against this repo's real data found the same split here:

- The Bangi majority FACT card is real (`data/mp_profiles.json` P.102, GE15
  majority 69,701) — kept, but read from `MPProfile`/live Storage rather
  than retyped as a string, so it can never drift from its own source.
- "The Urban Renewal Bill passed second reading 148–62" matches no Bill in
  `data/bills.json` — no Seat's Bill is titled that. Replaced with a real
  one: D.R.28/2025's real Division (125 ayes, 63 noes, second reading).
- "9 outlets read in EN and BM" is wrong on its own terms — `data/outlets.json`
  names 7. Replaced with the same real `sources_count` figure `#74`'s trust
  strip already states (outlets actually read the latest day, not the
  outlet list's static length).
- "1,284 articles scored this week" and "Coverage of PH rose 3.1 points this
  week" state a week's arithmetic nothing here was computing. Unlike `#74`'s
  homepage (which settled for a single day's count rather than invent a
  week), this page's stat strip literally promises "this week" — so it earns
  a real one, genuinely summed from Storage's own daily snapshots
  (`_recent_articles`), and the MODEL card states whichever Coalition's
  Sentiment actually moved most over the same real comparison `#74`'s digest
  already computes (`politikku_homepage.sentiment_rows`), not a hardcoded
  Coalition.

Follows `public_page.py`/`politikku_homepage.py`'s seam: `landing_model`
computes every number the page states; `render_landing` decides nothing;
`build_landing`/`main` is the one place that touches Storage.

Routing (`#75`'s own text: "the handoff doesn't specify the UI for that...
use judgement here"): this page is a real, standalone, reachable page at
its own route (`politikku_shell.LANDING_URL`) with a link back to it from
the persistent footer — not wired to any `localStorage`-based "only show this
to a first-time visitor" gate. That gate is real client-side state, and
`#70` already settled that all of PolitikKu's client-side state lives in
`#77`'s TypeScript module, not scattered inline scripts — building one here
would be a second, uncoordinated place client state gets decided. `#77`'s
own "Recently looked up" read of `localStorage` is the natural place to add
"and if there's nothing there, land here first" once it exists.
"""

from __future__ import annotations

import html
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from sqlalchemy.engine import Engine

from lpa.bill_tracker import Bill
from lpa.domain import Coalition, ElectionStatus
from lpa.mp_profile import MPProfile
from lpa.politikku_hemicycle import HemicycleCounts, Palette, render_hemicycle
from lpa.politikku_homepage import SentimentRow, hemicycle_counts, sentiment_rows
from lpa.politikku_i18n import (
    FIND_YOUR_MP_EN,
    FIND_YOUR_MP_MS,
    GE16_SEAT_PROJECTION_EN,
    GE16_SEAT_PROJECTION_MS,
    GOVERNMENT_COALITION_EN,
    GOVERNMENT_COALITION_MS,
    POSTCODE_OR_CONSTITUENCY_MS,
    not_calibrated_tag,
)
from lpa.politikku_shell import (
    LANDING_URL,
    Language,
    methodology_url,
    render_shell,
    short_date,
    t,
)
from lpa.public_page import PageModel
from lpa.storage import SentimentSnapshot

BANGI_SEAT_CODE = "P.102"
"""The Seat the FACT card quotes (#78, ADR 0009) — read live rather than
retyped. The first real MP Profile this repo had, and still the one the card
names; #105 built most of the House on the same schema, so which Seat to
feature is now an editorial choice rather than the only option."""

FEATURED_BILL_CODE = "D.R.28/2025"
"""RUU Perolehan Kerajaan 2025 — the pilot's own Bill with a real, on-the-
record second-reading Division (#80, ADR 0010), and the mockup's invented
"Urban Renewal Bill" swapped for it."""

RECENT_ARTICLE_WINDOW_DAYS = 7
"""How far back the stat strip's article count looks — matches the design's
own "this week" framing, genuinely summed rather than assumed."""


class CardKind(StrEnum):
    """Which of the two FACT/MODEL panel treatments a card gets — the
    design's own vocabulary (`design_handoff_politikku/README.md`'s "The
    FACT / MODEL panel" section), not an invented category."""

    FACT = "fact"
    MODEL = "model"


@dataclass(frozen=True)
class TrustCard:
    """One row of the landing page's FACT/MODEL panel.

    `claim`/`source` carry interpolated numbers (a majority, a Division
    tally, a seat count) computed once here — #81 needs both languages'
    version of the same sentence, so this dataclass carries a full sentence
    per language rather than a template plus a language switch at render
    time, keeping the one place that does the interpolation arithmetic the
    same as before (`landing_model`/its private card builders), not
    duplicated into `_trust_card` as well.
    """

    kind: CardKind
    claim_en: str
    claim_ms: str
    """`claim_en`'s BM sentence. Where `claim_en` states a real MP/Bill fact
    (cards 1–2), only the connecting words are translated — the sourced
    figures and proper nouns are identical in both, so there is no fact here
    an English-only reader could see that a BM-only reader cannot."""
    source_en: str
    source_ms: str
    modelled_number: bool = False
    """Whether `claim_en`/`claim_ms` state a modelled number that needs the
    inline NOT CALIBRATED tag beside it — trust rule 1 (non-negotiable):
    "appears inline beside every modelled number... Never on factual data."
    `False` for every FACT card and for a MODEL card stating no number at
    all (the "not enough history yet" fallback has nothing for a tag to
    travel beside). A plain `bool` rather than deriving it from `kind`
    alone, since not every MODEL card states a number."""


@dataclass(frozen=True)
class LandingModel:
    """Every number/claim the landing page states, computed once."""

    updated_at: date
    sources_count: int
    status: ElectionStatus
    total_seats: int
    government_seats: int
    hemicycle: HemicycleCounts
    """The hero's background texture (`politikku_hemicycle`'s `DARK_BAND`
    palette, per #73's own documented reuse) — the same real tally
    `politikku_homepage.hemicycle_counts` computes, not a second copy."""
    recent_articles: int
    recent_days: int
    """How many days `recent_articles` actually sums — may be fewer than
    `RECENT_ARTICLE_WINDOW_DAYS` early in Storage's history; stated
    honestly rather than implying a full week that hasn't happened yet."""
    cards: tuple[TrustCard, TrustCard, TrustCard, TrustCard]
    """Exactly four, FACT/FACT/MODEL/MODEL — the design's own panel shape."""


def landing_model(
    page: PageModel,
    sentiment_history: Sequence[SentimentSnapshot],
    names: Mapping[Coalition, str],
    bangi: MPProfile,
    featured_bill: Bill,
) -> LandingModel:
    """Build the landing page's model.

    `page` is the same `public_page.page_model()` output `#74`'s homepage
    reads — this page states the identical `government_seats`/`total_seats`
    the dashboard and homepage do, from one Storage read, never a second
    computation that could disagree. `bangi`/`featured_bill` are looked up
    by the caller (`build_landing`) from real Storage/config rather than
    hardcoded here, so a future pilot-slice expansion only changes which
    record is passed in, not this function.
    """
    seat = next((s for s in page.seats if s.code == bangi.seat_code), None)
    if seat is None:
        raise ValueError(
            f"{bangi.seat_code!r} (the landing page's featured MP Profile) has no "
            "matching Seat in the Baseline this Projection was built from."
        )
    if featured_bill.division is None:
        raise ValueError(
            f"{featured_bill.code!r} (the landing page's featured Bill) carries no "
            "Division to state a FACT card about."
        )
    articles, days = _recent_articles(sentiment_history)
    return LandingModel(
        updated_at=page.computed_at,
        sources_count=len(page.sources),
        status=page.status,
        total_seats=page.total_seats,
        government_seats=page.government_seats,
        hemicycle=hemicycle_counts(page),
        recent_articles=articles,
        recent_days=days,
        cards=(
            TrustCard(
                kind=CardKind.FACT,
                claim_en=f"{bangi.name} won {seat.name} with a majority of {bangi.ge15.majority:,}",
                claim_ms=f"{bangi.name} menang {seat.name} dengan majoriti {bangi.ge15.majority:,}",
                source_en="Election Commission, GE15 official result",
                source_ms="Suruhanjaya Pilihan Raya, keputusan rasmi PRU15",
            ),
            _bill_fact_card(featured_bill),
            TrustCard(
                kind=CardKind.MODEL,
                claim_en=(
                    f"{page.government_seats} of {page.total_seats} Seats projected "
                    f"to the {GOVERNMENT_COALITION_EN}"
                ),
                claim_ms=(
                    f"{page.government_seats} daripada {page.total_seats} Kerusi diunjurkan "
                    f"kepada {GOVERNMENT_COALITION_MS}"
                ),
                source_en="Swing Model against the GE15 Baseline · not calibrated",
                source_ms="Model Peralihan berbanding Asas PRU15 · belum ditentukur",
                modelled_number=True,
            ),
            _sentiment_mover_card(sentiment_history, names),
        ),
    )


def _bill_fact_card(bill: Bill) -> TrustCard:
    d = bill.division
    assert d is not None  # checked by the caller before this is reached
    sitting = short_date(d.sitting_date)
    return TrustCard(
        kind=CardKind.FACT,
        claim_en=f"{bill.title} passed second reading, {d.ayes}–{d.noes}",
        claim_ms=f"{bill.title} diluluskan bacaan kedua, {d.ayes}–{d.noes}",
        source_en=f"Dewan Rakyat Hansard, {sitting}",
        source_ms=f"Hansard Dewan Rakyat, {sitting}",
    )


def _sentiment_mover_card(
    history: Sequence[SentimentSnapshot], names: Mapping[Coalition, str]
) -> TrustCard:
    """The Coalition whose Sentiment moved most over the same real
    week-over-week comparison `#74`'s digest computes — never a hardcoded
    Coalition (the mockup names PH; this states whichever one actually
    moved), and "no movement to report" is a real, statable case rather
    than a card forced to say something."""
    rows = sentiment_rows(history, names)
    movers: list[tuple[SentimentRow, float]] = [
        (row, row.delta) for row in rows if row.delta is not None
    ]
    if not movers:
        return TrustCard(
            kind=CardKind.MODEL,
            claim_en="Not enough Sentiment history yet to state a week-over-week move",
            claim_ms="Sejarah Sentimen belum mencukupi untuk menyatakan pergerakan minggu-ke-minggu",
            source_en="Open multilingual sentiment model",
            source_ms="Model sentimen berbilang bahasa sumber terbuka",
        )
    biggest, delta = max(movers, key=lambda pair: abs(pair[1]))
    direction_en = "rose" if delta > 0 else "fell"
    direction_ms = "meningkat" if delta > 0 else "menurun"
    points = abs(delta) * 100
    recent_articles = sum(
        snap.sentiment.total_articles for snap in history[-RECENT_ARTICLE_WINDOW_DAYS:]
    )
    return TrustCard(
        kind=CardKind.MODEL,
        claim_en=f"Coverage of {biggest.name} {direction_en} {points:.1f} points this week",
        claim_ms=f"Liputan {biggest.name} {direction_ms} {points:.1f} mata minggu ini",
        source_en=f"Open multilingual sentiment model, {recent_articles:,} articles",
        source_ms=f"Model sentimen berbilang bahasa sumber terbuka, {recent_articles:,} artikel",
        modelled_number=True,
    )


def _recent_articles(history: Sequence[SentimentSnapshot]) -> tuple[int, int]:
    """`(total articles, days summed)` over the most recent
    `RECENT_ARTICLE_WINDOW_DAYS` stored snapshots — fewer than that early in
    Storage's history, stated honestly via the second value rather than
    implied as a full week."""
    window = history[-RECENT_ARTICLE_WINDOW_DAYS:]
    return sum(snap.sentiment.total_articles for snap in window), len(window)


# ── rendering ─────────────────────────────────────────────────────────────


def _stat_strip(model: LandingModel, language: Language) -> str:
    status_text = (
        t(
            language,
            f"GE16 not yet called · deadline {short_date(model.status.constitutional_deadline)}",
            f"PRU16 belum diisytiharkan · tarikh akhir {short_date(model.status.constitutional_deadline)}",
        )
        if not model.status.called
        else t(language, "GE16 called", "PRU16 diisytiharkan")
    )
    seats_tracked = t(language, "Seats tracked", "Kerusi dijejaki")
    outlets_read = t(language, "outlets read in EN and BM", "portal berita dibaca dalam BI dan BM")
    days_word_en = "day" if model.recent_days == 1 else "days"
    articles_clause = t(
        language,
        f"articles scored, past {model.recent_days} {days_word_en}",
        f"artikel dinilai, {model.recent_days} hari lepas",
    )
    return f"""
<div class="pk-landing-stats">
  <span><strong>{model.total_seats}</strong> {seats_tracked}</span>
  <span><strong>{model.sources_count}</strong> {outlets_read}</span>
  <span><strong>{model.recent_articles:,}</strong> {articles_clause}</span>
  <span class="pk-landing-stats-status">{html.escape(status_text)}</span>
</div>
""".strip()


def _what_is_inside(language: Language) -> str:
    items = (
        (
            "01",
            "Your MP",
            "Ahli Parlimen anda",
            "Enter a postcode and get your Seat, your MP, their attendance and how they voted.",
            (
                "Masukkan poskod dan dapatkan kerusi, Ahli Parlimen, kehadiran mereka dan cara "
                "mereka mengundi."
            ),
            "Factual · SPR, Hansard",
            "Fakta · SPR, Hansard",
        ),
        (
            "02",
            "Bills in plain language",
            "Rang undang-undang dalam bahasa mudah",
            "Every Bill before the Dewan Rakyat, what stage it has reached and how the vote fell.",
            "Setiap rang undang-undang di Dewan Rakyat, peringkat yang dicapai dan keputusan undian.",
            "Factual · parlimen.gov.my",
            "Fakta · parlimen.gov.my",
        ),
        (
            "03",
            GE16_SEAT_PROJECTION_EN,
            GE16_SEAT_PROJECTION_MS,
            (
                "GE15 results plus a uniform-within-state Swing, published per Seat with its "
                "margin — arithmetic, openly shown."
            ),
            (
                "Keputusan PRU15 ditambah Peralihan seragam dalam setiap negeri, diterbitkan bagi "
                "setiap kerusi berserta majoritinya — pengiraan yang dipaparkan secara terbuka."
            ),
            "Modelled · not calibrated",
            "Model · belum ditentukur",
        ),
        (
            "04",
            "News sentiment",
            "Sentimen berita",
            "The tone of coverage about each Coalition. Coverage tone is not support, and not a poll.",
            (
                "Nada liputan tentang setiap Gabungan. Nada liputan bukan sokongan, dan bukan "
                "tinjauan pendapat."
            ),
            "Modelled · not calibrated",
            "Model · belum ditentukur",
        ),
    )
    cells = "".join(
        f'<div class="pk-landing-cell"><span class="pk-landing-cell-n">{n}</span>'
        f"<h3>{html.escape(t(language, title_en, title_ms))}</h3>"
        f"<p>{html.escape(t(language, body_en, body_ms))}</p>"
        f'<span class="pk-landing-cell-tag">{html.escape(t(language, tag_en, tag_ms))}</span></div>'
        for n, title_en, title_ms, body_en, body_ms, tag_en, tag_ms in items
    )
    eyebrow = t(language, "What is inside", "Apa yang ada")
    return f"""
<section class="pk-landing-inside">
  <div class="pk-eyebrow">{eyebrow}</div>
  <div class="pk-landing-grid">{cells}</div>
</section>
""".strip()


def _trust_card(card: TrustCard, language: Language) -> str:
    cls = "pk-trust-card-fact" if card.kind is CardKind.FACT else "pk-trust-card-model"
    pill_cls = "pk-pill-fact" if card.kind is CardKind.FACT else "pk-pill-model"
    pill_label = t(language, "FACT", "FAKTA") if card.kind is CardKind.FACT else "MODEL"
    # Trust rule 1 (non-negotiable): the tag travels beside the number
    # itself, not just named in the source line — a repeat of the exact
    # gap #74's own code review caught for the homepage's sentiment
    # deltas, fixed the same way here.
    tag = f" {not_calibrated_tag(language)}" if card.modelled_number else ""
    claim = html.escape(t(language, card.claim_en, card.claim_ms))
    source = html.escape(t(language, card.source_en, card.source_ms))
    return f"""
<div class="pk-trust-card {cls}">
  <span class="{pill_cls}">{pill_label}</span>
  <div><div class="pk-trust-claim">{claim}{tag}</div>
  <div class="pk-trust-source">{source}</div></div>
</div>
""".strip()


def _where_the_line_is_drawn(model: LandingModel, language: Language) -> str:
    cards = "".join(_trust_card(c, language) for c in model.cards)
    eyebrow = t(language, "Where the line is drawn", "Di mana garisan dilukis")
    heading = t(
        language,
        "Facts are labelled as facts. Estimates are labelled as estimates.",
        "Fakta dilabel sebagai fakta. Anggaran dilabel sebagai anggaran.",
    )
    p1 = t(
        language,
        "An MP's name, a GE15 majority, a recorded vote — these are matters of record, and "
        "we cite where each came from. A projected Seat Call is the output of a model that has "
        "never been calibrated against survey data, and it carries a tag saying so everywhere "
        "it appears.",
        "Nama Ahli Parlimen, majoriti PRU15, undian yang direkodkan — ini adalah fakta rasmi, "
        "dan kami menyatakan sumber setiap satu. Keputusan Kerusi yang diunjurkan adalah output "
        "model yang tidak pernah ditentukur terhadap data tinjauan, dan ia membawa tag yang "
        "menyatakan ini di mana sahaja ia muncul.",
    )
    p2 = t(
        language,
        "The code, the data and the model are public. Disagree with the Swing assumptions "
        "and you can read them, or fork them.",
        "Kod, data dan model adalah terbuka kepada umum. Tidak bersetuju dengan andaian "
        "Peralihan? Anda boleh membacanya, atau fork ia.",
    )
    link = t(
        language, "Full methodology and source list →", "Metodologi penuh dan senarai sumber →"
    )
    return f"""
<section class="pk-landing-trust">
  <div class="pk-landing-trust-prose">
    <div class="pk-eyebrow">{eyebrow}</div>
    <h2>{heading}</h2>
    <p>{p1}</p>
    <p>{p2}</p>
    <a href="{html.escape(methodology_url(language))}" class="pk-landing-methodology-link">{link}</a>
  </div>
  <div class="pk-landing-trust-cards">{cards}</div>
</section>
""".strip()


def _hero(model: LandingModel, language: Language) -> str:
    # Dark-band palette, no threshold line — #73's own documented reuse for
    # exactly this ("dark-band variant... reused at opacity .14-.16 as hero
    # texture on the landing page"), not a decorative shape invented here.
    texture = render_hemicycle(
        model.hemicycle,
        palette=Palette.DARK_BAND,
        show_threshold=False,
        css_class="pk-landing-hero-texture",
    )
    eyebrow = t(
        language, "A public reference for Malaysian politics", "Rujukan awam untuk politik Malaysia"
    )
    h1 = t(
        language,
        "Know your Seat.<br>Read the Dewan Rakyat.<br>See where GE16 stands.",
        "Kenali kerusi anda.<br>Baca Dewan Rakyat.<br>Lihat kedudukan PRU16.",
    )
    lede = t(
        language,
        "PolitikKu puts your Member of Parliament, the bills before "
        "Parliament, and an open seat projection for GE16 in one place. No party affiliation, "
        "no advertising, no account.",
        "PolitikKu meletakkan Ahli Parlimen anda, rang undang-undang yang dibentangkan di "
        "Parlimen, dan unjuran kerusi terbuka untuk PRU16 di satu tempat. Tiada pertalian "
        "parti, tiada iklan, tiada akaun.",
    )
    find_your_mp = t(language, FIND_YOUR_MP_EN, FIND_YOUR_MP_MS)
    read_methodology = t(language, "Read the methodology", "Baca metodologi")
    return f"""
<section class="pk-landing-hero">
  {texture}
  <div class="pk-landing-hero-content">
    <div class="pk-eyebrow pk-eyebrow-on-dark">{eyebrow}</div>
    <h1>{h1}</h1>
    <p class="pk-lede-on-dark">{lede}</p>
    <div class="pk-landing-hero-actions">
      <a class="pk-landing-cta-primary" href="/politikku/">{find_your_mp}</a>
      <a class="pk-landing-cta-secondary" href="{html.escape(methodology_url(language))}">{read_methodology}</a>
    </div>
  </div>
</section>
""".strip()


def _search_cta(language: Language) -> str:
    heading = t(language, "Start with where you live", "Mula dengan tempat tinggal anda")
    lede = t(
        language,
        "Everything else on this site follows from your Seat.",
        "Semua yang lain di laman ini bermula daripada kerusi anda.",
    )
    placeholder = t(language, "Postcode or constituency name", POSTCODE_OR_CONSTITUENCY_MS)
    search = t(language, "Search", "Cari")
    return f"""
<section class="pk-landing-search-cta">
  <div>
    <h2>{heading}</h2>
    <p>{lede}</p>
  </div>
  <form class="pk-lookup-form" data-pk-lookup-form>
    <label class="pk-visually-hidden" for="pk-landing-lookup-input">{placeholder}</label>
    <input id="pk-landing-lookup-input" name="q" type="text" autocomplete="off"
           placeholder="{placeholder}" data-pk-lookup-input>
    <button type="submit" class="pk-search-btn" data-pk-lookup-submit>{search}</button>
  </form>
  <div class="pk-lookup-results" data-pk-lookup-results hidden></div>
</section>
""".strip()


def render_landing_body(model: LandingModel, language: Language = Language.EN) -> str:
    """The landing page's `body_html`, without the persistent shell."""
    return (
        f"<style>{_CSS}</style>"
        f"{_hero(model, language)}{_stat_strip(model, language)}{_what_is_inside(language)}"
        f"{_where_the_line_is_drawn(model, language)}{_search_cta(language)}"
    )


def render_landing(model: LandingModel, *, language: Language = Language.EN) -> str:
    """The landing page as one full HTML document, shell included."""
    title = t(
        language,
        "PolitikKu — a public reference for Malaysian politics",
        "PolitikKu — rujukan awam untuk politik Malaysia",
    )
    return render_shell(
        title=title,
        active_nav="landing",
        language=language,
        page_path="landing.html",
        updated_at=model.updated_at,
        sources_count=model.sources_count,
        status=model.status,
        body_html=render_landing_body(model, language),
    )


_CSS = """
  .pk-eyebrow-on-dark { color: var(--on-dark-muted); }
  .pk-landing-hero {
    background: var(--ink); position: relative; overflow: hidden;
    padding: 74px var(--gutter-desktop) 66px;
  }
  .pk-landing-hero-texture {
    position: absolute; right: -30px; top: 24px; width: 520px; opacity: .16;
  }
  .pk-landing-hero-content { position: relative; max-width: 640px; }
  .pk-landing-hero h1 {
    font-family: var(--serif); font-weight: 400; font-size: var(--text-hero-desktop);
    line-height: 1.04; letter-spacing: -.025em; color: var(--paper); margin: 20px 0;
  }
  .pk-lede-on-dark { font-size: 17px; line-height: 1.6; color: var(--on-dark-body); max-width: 520px; margin: 0 0 30px; }
  .pk-landing-hero-actions { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
  .pk-landing-cta-primary, .pk-landing-cta-secondary {
    height: 52px; padding: 0 24px; border-radius: var(--radius-lg); font-size: 15px;
    display: inline-flex; align-items: center; text-decoration: none;
  }
  .pk-landing-cta-primary { background: var(--paper); color: var(--ink); font-weight: 500; }
  .pk-landing-cta-secondary { border: 1px solid rgba(251,250,247,.3); color: var(--on-dark-body); }

  .pk-landing-stats {
    background: var(--paper-alt); border-bottom: 1px solid var(--line);
    padding: 16px var(--gutter-desktop); display: flex; gap: 40px; flex-wrap: wrap;
    font-size: 13px; color: var(--ink-secondary);
  }
  .pk-landing-stats strong { font-family: var(--serif); font-size: 18px; color: var(--ink); font-weight: 500; }
  .pk-landing-stats-status { margin-left: auto; font-family: var(--mono); font-size: 11px; color: var(--muted); }

  .pk-landing-inside { background: var(--paper); padding: 46px var(--gutter-desktop); }
  .pk-landing-grid {
    display: grid; grid-template-columns: repeat(4, 1fr); gap: 1px;
    background: var(--line-soft); border: 1px solid var(--line-soft); border-radius: var(--radius-lg);
    overflow: hidden; margin-top: 22px;
  }
  .pk-landing-cell { background: var(--white); padding: 24px 20px; display: flex; flex-direction: column; gap: 9px; }
  .pk-landing-cell-n { font-family: var(--mono); font-size: 10.5px; color: var(--muted); }
  .pk-landing-cell h3 { font-family: var(--serif); font-weight: 500; font-size: 20px; color: var(--ink); margin: 0; line-height: 1.2; }
  .pk-landing-cell p { margin: 0; font-size: 13.5px; line-height: 1.5; color: var(--ink-secondary); }
  .pk-landing-cell-tag {
    margin-top: auto; padding-top: 12px; font-family: var(--mono); font-size: 10px;
    letter-spacing: .06em; text-transform: uppercase; color: var(--accent);
  }

  .pk-landing-trust {
    background: var(--paper-alt); border-top: 1px solid var(--line-soft);
    padding: 46px var(--gutter-desktop); display: grid; grid-template-columns: 1fr 1.1fr; gap: 52px;
  }
  .pk-landing-trust-prose h2 {
    font-family: var(--serif); font-weight: 500; font-size: 30px; line-height: 1.15;
    color: var(--ink); margin: 12px 0 14px; letter-spacing: -.015em;
  }
  .pk-landing-trust-prose p { margin: 0 0 12px; font-size: 14.5px; line-height: 1.6; color: var(--ink-secondary); }
  .pk-landing-methodology-link { display: inline-block; margin-top: 16px; font-size: 13px; color: var(--accent); }
  .pk-landing-trust-cards { display: flex; flex-direction: column; gap: 12px; }
  .pk-trust-card {
    background: var(--paper); border-radius: var(--radius-lg); padding: 18px 20px;
    display: flex; gap: 16px; align-items: flex-start;
  }
  .pk-trust-card-fact { border: 1px solid var(--line); }
  .pk-trust-card-model { border: 1px solid var(--caution-border); }
  .pk-pill-fact, .pk-pill-model {
    font-family: var(--mono); font-size: 9.5px; letter-spacing: .08em; border-radius: var(--radius-sm);
    padding: 3px 7px; white-space: nowrap; margin-top: 2px;
  }
  .pk-pill-fact { color: var(--accent); background: var(--positive-bg); border: 1px solid var(--positive-border); }
  .pk-pill-model { color: var(--caution-deep); background: var(--caution-bg); border: 1px solid var(--caution-border); }
  .pk-trust-claim { font-size: 14.5px; color: var(--ink); margin-bottom: 3px; }
  .pk-trust-source { font-size: 12.5px; color: var(--muted); }

  .pk-landing-search-cta {
    background: var(--paper); border-top: 1px solid var(--line-soft); padding: 44px var(--gutter-desktop);
    display: flex; align-items: center; justify-content: space-between; gap: 40px; flex-wrap: wrap;
  }
  .pk-landing-search-cta h2 { font-family: var(--serif); font-weight: 500; font-size: 28px; color: var(--ink); margin: 0 0 8px; }
  .pk-landing-search-cta p { margin: 0; font-size: 14.5px; color: var(--ink-secondary); }
  .pk-landing-search-cta .pk-lookup-form { display: flex; gap: 10px; flex: 1; min-width: 320px; max-width: 520px; }
  .pk-landing-search-cta input {
    flex: 1; height: 52px; padding: 0 14px; font-size: 15px; border: 1px solid var(--line-strong);
    border-radius: var(--radius-md); font-family: var(--sans);
  }
  .pk-landing-search-cta .pk-search-btn {
    height: 52px; padding: 0 24px; background: var(--ink); color: var(--paper); border: none;
    border-radius: var(--radius-md); font-size: 14.5px; font-weight: 500; cursor: pointer;
  }

  @media (max-width: 900px) {
    .pk-landing-hero { padding: 36px var(--gutter-mobile) 34px; }
    .pk-landing-hero h1 { font-size: var(--text-hero-mobile); }
    .pk-landing-stats, .pk-landing-inside, .pk-landing-trust, .pk-landing-search-cta {
      padding: 24px var(--gutter-mobile);
    }
    .pk-landing-stats-status { margin-left: 0; }
    .pk-landing-grid { grid-template-columns: 1fr; }
    /* README §1 mobile spec: "moves the Factual/Modelled tag up beside
       each heading" — desktop pins it to the card's bottom edge
       (`margin-top: auto` above); reorder the flex column so it sits
       right after the heading instead, on the stacked mobile layout only. */
    .pk-landing-cell-n { order: 1; }
    .pk-landing-cell h3 { order: 2; }
    .pk-landing-cell-tag { order: 3; margin-top: 0; padding-top: 0; }
    .pk-landing-cell p { order: 4; }
    .pk-landing-trust { grid-template-columns: 1fr; gap: 24px; }
    /* README §1: "cut from four rows to one of each" — cards are ordered
       FACT, FACT, MODEL, MODEL, so the second of each kind (positions 2
       and 4) is what drops, keeping one FACT + one MODEL, not just the
       first two children. */
    .pk-landing-trust-cards .pk-trust-card:nth-child(2),
    .pk-landing-trust-cards .pk-trust-card:nth-child(4) { display: none; }
    .pk-landing-search-cta { flex-direction: column; align-items: stretch; }
  }
"""


def build_landing(engine: Engine, *, language: Language = Language.EN) -> tuple[str, date]:
    """Read Storage and render the landing page. The whole I/O half."""
    from lpa.config import (
        coalition_names,
        load_coalition_config,
        load_election_status,
        load_mp_profiles,
        load_state_election_signals,
        swing_model_config,
    )
    from lpa.config import load_bills as load_bills_config
    from lpa.public_page import page_model
    from lpa.storage import (
        load_projections,
        load_seat_baselines,
        load_sentiment_snapshots,
        load_state_swing,
    )

    projections = load_projections(engine)
    if not projections:
        raise SystemExit("No Projection stored. Run `python -m lpa.pipeline` to compute one.")
    baseline = load_seat_baselines(engine)
    if not baseline:
        raise SystemExit("No Seat Baseline in Storage. Run `python -m lpa.baseline_loader` first.")

    config = load_coalition_config()
    names = coalition_names(config)
    snapshots = load_sentiment_snapshots(engine)
    latest_sentiment = snapshots[-1].sentiment if snapshots else None
    page = page_model(
        projection=projections[-1],
        baseline=baseline,
        status=load_election_status(),
        config=swing_model_config(config),
        names=names,
        sentiment=latest_sentiment,
        state_election_signals=load_state_election_signals(),
        total_seats=config["total_seats"],
        state_swing=load_state_swing(engine, projections[-1].computed_at),
    )
    bangi = load_mp_profiles()[BANGI_SEAT_CODE]
    featured_bill = load_bills_config()[FEATURED_BILL_CODE]
    model = landing_model(page, snapshots, names, bangi, featured_bill)
    return render_landing(model, language=language), model.updated_at


def build_all_landing_languages(engine: Engine) -> list[tuple[Language, str, date]]:
    """`build_landing`, once per `Language` — matching `politikku_homepage.
    build_all_homepage_languages`'s own naming, which itself follows
    `politikku_mp_profile.build_all_mp_profile_pages`'s "build every variant
    this page has" precedent."""
    return [(language, *build_landing(engine, language=language)) for language in Language]


def main() -> None:
    """Render the landing page from Storage and write both languages to disk."""
    import argparse
    from pathlib import Path

    from lpa.storage import connect

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("public") / LANDING_URL.removeprefix("/"),
        help="where to write the English page; the BM variant is written alongside it at "
        "<output-dir>/ms/<output-name>, matching `politikku_shell._ms_route`'s own path convention",
    )
    args = parser.parse_args()

    engine = connect()
    for language, page, computed_at in build_all_landing_languages(engine):
        target = (
            args.output if language is Language.EN else args.output.parent / "ms" / args.output.name
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(page, encoding="utf-8")
        print(f"Wrote {target} ({len(page):,} bytes), computed {computed_at}")


if __name__ == "__main__":
    main()
