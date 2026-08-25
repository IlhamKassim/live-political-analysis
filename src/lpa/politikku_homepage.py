"""PolitikKu homepage: the returning-visitor view (#74).

Lookup is the primary action (the search *field* only — behaviour is #77's
job); the GE16 projection is the secondary draw; bills and sentiment are the
reasons to come back between elections. Full layout spec:
`design_handoff_politikku/README.md`, "2. Homepage".

Follows `public_page.py`'s seam: `homepage_model` computes every number the
page states and returns a plain `HomepageModel`; `render_homepage` turns
that into markup and decides nothing; `build_homepage` is the one place
that touches Storage.

Half this page is genuine reuse, not new arithmetic — the ticket's own "half
the homepage is backed by the existing pipeline" note made concrete. The
GE16 projection panel reads a `public_page.PageModel` — the same Swing
Model output the dashboard already renders — and only tallies its seats
into the hemicycle's three-way split. The sentiment digest reads the same
`AggregatedSentiment` history the dashboard's colophon cites, plus one
figure genuinely new here: a week-over-week delta. Only the bill tracker
and the lookup hero are new sections outright.

Per `lpa.bill_tracker`'s own docstring, a Bill's `stage` and `summary` both
need translation at the presentation layer — this page's job now. Only
`stage` is translated here, and only from the gloss the module's own
docstring already gives for this pilot's two values ("Lulus" = passed,
"Dirujuk ke JKPK" = referred to a Special Select Committee) — not an
independent translation. `summary` stays the sourced Malay excerpt
verbatim: writing an English paraphrase of a Bill's own legal text is
editorial judgement on its actual legal effect (`docs/agents/model-effort.md`
trigger 2), out of scope for this ticket. Full bilingual copy is #81's job.
"""

from __future__ import annotations

import html
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.engine import Engine

from lpa.bill_tracker import Bill
from lpa.domain import Coalition, ElectionStatus
from lpa.politikku_hemicycle import HemicycleCounts, Palette, render_hemicycle
from lpa.politikku_shell import DASHBOARD_URL, Language, render_shell, short_date
from lpa.public_page import PageModel, Tier, format_signed
from lpa.storage import SentimentSnapshot

BILLS_SHOWN = 3
"""Cards on the homepage grid — "All bills →" links to the rest, at a route
not yet built (same "wired to a route that doesn't need to exist yet"
allowance `politikku_shell` already uses for Bills/Sentiment/Methodology)."""

STAGE_LABELS_EN: Mapping[str, str] = {
    "Lulus": "Passed",
    "Dirujuk ke JKPK": "Referred to Special Select Committee",
}
"""Sourced from `lpa.bill_tracker`'s own module docstring, which glosses
exactly these two stages — not an independent translation. A stage this
pilot's data does not cover falls back to Parliament's own word rather than
an invented English label (`_stage_label`)."""

DELTA_WINDOW = timedelta(days=7)
"""How far back the sentiment digest's ↑/↓ looks for a comparison point."""


def _stage_label(stage: str) -> str:
    """The Bill's stage, translated where a sourced gloss exists."""
    return STAGE_LABELS_EN.get(stage, stage)


@dataclass(frozen=True)
class SentimentRow:
    """One Coalition's line in the sentiment digest table."""

    coalition: Coalition
    name: str
    article_count: int
    score: float
    delta: float | None
    """Change in score since the snapshot ~7 days earlier. `None` when
    Storage holds no snapshot at that point — never a guessed 0.0."""


@dataclass(frozen=True)
class HomepageModel:
    """Every number the homepage states, computed once and rendered as-is."""

    updated_at: date
    sources_count: int
    status: ElectionStatus
    hemicycle: HemicycleCounts
    government_seats: int
    total_seats: int
    majority_threshold: int
    government_majority: bool
    clear_seat_calls: int
    """Seats not `Tier.TIGHT`, either side — the projection panel's "Clear
    Seat Calls" stat."""
    sentiment_rows: tuple[SentimentRow, ...]
    sentiment_total_articles: int
    """The latest stored day's article count — the handoff's own sample
    footer ("1,284 articles · 17–23 Aug 2026") states a week's total and a
    week's date range, but `AggregatedSentiment` is a one-day snapshot
    (`pipeline.py`'s "one snapshot a day") and nothing here sums a week of
    them. Stating today's real count, with no date range, is honest about
    what the number covers; stating a week's worth without doing that sum
    would be the trust-strip's "invented clock time" problem again
    (`politikku_shell`'s own docstring) — a figure the page cannot verify."""
    bills: tuple[Bill, ...]
    """Up to `BILLS_SHOWN`, most recently updated first."""

    @property
    def margin_over_majority(self) -> int:
        """Seats clear of a Majority — negative means short of one.

        Same formula as `public_page.PageModel.buffer`, restated here on
        this page's own two fields rather than kept on the source
        `PageModel` — `homepage_model()` builds both from the same
        `page.government_seats`/`page.majority_threshold`, so the two can
        never disagree, only ever be computed from the same two numbers
        twice.
        """
        return self.government_seats - self.majority_threshold


def homepage_model(
    page: PageModel,
    sentiment_history: Sequence[SentimentSnapshot],
    names: Mapping[Coalition, str],
    bills: Mapping[str, Bill],
) -> HomepageModel:
    """Build the homepage's model from a dashboard `PageModel` plus this
    page's own sentiment history and Bills.

    `page` is the same `public_page.page_model()` output the dashboard
    renders — `build_homepage` reads Storage once and hands both pages the
    same Projection, so the two can never state a different seat total for
    the same day. `sentiment_history` is oldest-first, the same order
    `storage.load_sentiment_snapshots` returns; the latest entry is what the
    digest states, and the rest exist only to find the ~7-day-old point a
    delta is measured against.
    """
    return HomepageModel(
        updated_at=page.computed_at,
        sources_count=len(page.sources),
        status=page.status,
        hemicycle=hemicycle_counts(page),
        government_seats=page.government_seats,
        total_seats=page.total_seats,
        majority_threshold=page.majority_threshold,
        government_majority=page.government_majority,
        clear_seat_calls=sum(1 for seat in page.seats if seat.tier != Tier.TIGHT),
        sentiment_rows=sentiment_rows(sentiment_history, names),
        sentiment_total_articles=sentiment_history[-1].sentiment.total_articles
        if sentiment_history
        else 0,
        bills=_top_bills(bills),
    )


def hemicycle_counts(page: PageModel) -> HemicycleCounts:
    """The dashboard's per-Seat tiers, tallied into the hemicycle's
    Government clear / within model noise / Non-government clear split —
    the BM key-pair table's own wording for the three bands."""
    government_clear = sum(1 for s in page.seats if s.government and s.tier != Tier.TIGHT)
    nongovernment_clear = sum(1 for s in page.seats if not s.government and s.tier != Tier.TIGHT)
    noise = sum(1 for s in page.seats if s.tier == Tier.TIGHT)
    return HemicycleCounts(
        government_clear=government_clear, noise=noise, nongovernment_clear=nongovernment_clear
    )


def sentiment_rows(
    history: Sequence[SentimentSnapshot], names: Mapping[Coalition, str]
) -> tuple[SentimentRow, ...]:
    """One row per Coalition the latest snapshot named, most-covered first —
    the same ordering `public_page._article_counts` already uses. Public
    (not `_`-prefixed) because `politikku_landing`'s MODEL card reuses this
    exact computation for its own "biggest mover" figure — one place this
    delta is computed, not a second copy."""
    if not history:
        return ()
    latest = history[-1].sentiment
    target = history[-1].computed_at - DELTA_WINDOW
    earlier = next(
        (snap.sentiment for snap in reversed(history[:-1]) if snap.computed_at == target), None
    )
    coalitions = sorted(latest.article_counts, key=lambda c: (-latest.article_counts[c], c))
    rows = []
    for coalition in coalitions:
        score = latest.scores.get(coalition, 0.0)
        delta = (
            score - earlier.scores[coalition] if earlier and coalition in earlier.scores else None
        )
        rows.append(
            SentimentRow(
                coalition=coalition,
                name=names.get(coalition, coalition),
                article_count=latest.article_counts[coalition],
                score=score,
                delta=delta,
            )
        )
    return tuple(rows)


def _top_bills(bills: Mapping[str, Bill], limit: int = BILLS_SHOWN) -> tuple[Bill, ...]:
    """The `limit` most recently updated Bills, newest `stage_date` first."""
    return tuple(sorted(bills.values(), key=lambda b: b.stage_date, reverse=True)[:limit])


# ── rendering ─────────────────────────────────────────────────────────────


def _hero(model: HomepageModel) -> str:
    tag = '<span class="pk-tag-modelled">NOT CALIBRATED</span>'
    return f"""
<section class="pk-hero">
  <div class="pk-hero-lookup">
    <div class="pk-eyebrow">CONSTITUENCY LOOKUP</div>
    <h1>Find your MP</h1>
    <p class="pk-lede">Enter your postcode or the name of your constituency to see who
    represents you in the Dewan Rakyat.</p>
    <form class="pk-lookup-form" data-pk-lookup-form>
      <label class="pk-visually-hidden" for="pk-lookup-input">Postcode or constituency</label>
      <input id="pk-lookup-input" name="q" type="text" autocomplete="off"
             placeholder="Postcode or constituency" data-pk-lookup-input>
      <button type="submit" class="pk-search-btn" data-pk-lookup-submit>Search</button>
    </form>
    <button type="button" class="pk-locate-btn" data-pk-locate>Use my location</button>
    <p class="pk-privacy-note">Location is read in your browser and never sent to us.</p>
    <div class="pk-lookup-results" data-pk-lookup-results hidden></div>
    <div class="pk-recent-chips" data-pk-recent-chips hidden>
      <div class="pk-recent-label">Recently looked up</div>
      <div class="pk-recent-list" data-pk-recent-list></div>
    </div>
  </div>
  <div class="pk-hero-projection">
    <div class="pk-eyebrow-row">
      <div class="pk-eyebrow">GE16 SEAT PROJECTION</div>
      <a href="{html.escape(DASHBOARD_URL)}">Full projection →</a>
    </div>
    <div class="pk-projection-headline">
      <span class="pk-headline-number">{model.government_seats} of {model.total_seats}</span>
      <span class="pk-headline-unit">to the Government Coalition</span>
      {tag}
    </div>
    {render_hemicycle(model.hemicycle, palette=Palette.LIGHT, majority_label=f"MAJORITY {model.majority_threshold}")}
    <ul class="pk-hemicycle-legend">
      <li><span class="pk-swatch pk-swatch-gov"></span>Government clear</li>
      <li><span class="pk-swatch pk-swatch-noise"></span>Within model noise</li>
      <li><span class="pk-swatch pk-swatch-nongov"></span>Non-government clear</li>
    </ul>
    <div class="pk-stat-grid">
      <div><dt>Margin over majority</dt><dd>{format_signed(model.margin_over_majority)} seats</dd></div>
      <div><dt>Clear Seat Calls</dt><dd>{model.clear_seat_calls} of {model.total_seats}</dd></div>
    </div>
    <p class="pk-caveat">Seat Calls are model-driven and not calibrated against survey
    data — see <a href="/politikku/methodology.html">how this works</a>.</p>
  </div>
</section>
""".strip()


def _bill_card(bill: Bill) -> str:
    if bill.division is not None:
        d = bill.division
        footer = f"{d.ayes} AYE · {d.noes} NO"
    else:
        footer = "No Division — voice vote"
    positive = bill.stage == "Lulus"
    dot_class = "pk-dot-positive" if positive else "pk-dot-pending"
    return f"""
<article class="pk-bill-card">
  <div class="pk-bill-status"><span class="{dot_class}"></span>
    <span class="pk-bill-stage">{html.escape(_stage_label(bill.stage))}</span></div>
  <h3><a href="{html.escape(bill.summary_source_url)}">{html.escape(bill.title)}</a></h3>
  <p class="pk-bill-summary" lang="ms">{html.escape(bill.summary)}</p>
  <div class="pk-bill-note">Parliament's own text, Bahasa Malaysia — untranslated.</div>
  <div class="pk-bill-footer">
    <span>{html.escape(short_date(bill.stage_date))}</span>
    <span>{html.escape(footer)}</span>
  </div>
</article>
""".strip()


def _bill_tracker(model: HomepageModel) -> str:
    cards = "".join(_bill_card(bill) for bill in model.bills)
    return f"""
<section class="pk-bills">
  <div class="pk-section-head">
    <h2>Dewan Rakyat this week</h2>
    <a href="/politikku/bills.html">All bills →</a>
  </div>
  <div class="pk-bill-grid">{cards}</div>
</section>
""".strip()


def _sentiment_bar(score: float) -> str:
    """Score (roughly -1..+1) as a 0–100% fill, centred at 50%."""
    clamped = max(-1.0, min(1.0, score))
    pct = (clamped + 1) / 2 * 100
    return (
        f'<div class="pk-sentiment-bar" role="img" '
        f'aria-label="Sentiment score {score:+.2f}">'
        f'<div class="pk-sentiment-fill" style="width:{pct:.1f}%"></div></div>'
    )


_MODELLED_TAG = '<span class="pk-tag-modelled">NOT CALIBRATED</span>'
"""The handoff's trust rule 1 names this inline, travelling with the
number, as non-negotiable for "the sentiment deltas" by name — the
homepage mockup's own screenshot omits it there, which is a gap in the
mockup, not a narrower reading of the rule text (see the design handoff's
"Trust rules" section, resolved 24 Aug 2026)."""


def _sentiment_delta(delta: float | None) -> str:
    if delta is None:
        return '<span class="pk-delta-none">—</span>'
    arrow = "↑" if delta > 0 else "↓" if delta < 0 else "→"
    cls = "pk-delta-up" if delta > 0 else "pk-delta-down" if delta < 0 else "pk-delta-flat"
    return f'<span class="{cls}">{arrow} {abs(delta):.2f}</span> {_MODELLED_TAG}'


def _sentiment_row(row: SentimentRow) -> str:
    return (
        "<tr>"
        f'<td><span class="pk-coalition">{html.escape(row.name)} '
        f"<small>{html.escape(row.coalition)}</small></span></td>"
        f"<td>{row.article_count}</td>"
        f"<td>{_sentiment_bar(row.score)}</td>"
        f"<td>{_sentiment_delta(row.delta)}</td>"
        "</tr>"
    )


def _sentiment_digest(model: HomepageModel) -> str:
    rows = "".join(_sentiment_row(row) for row in model.sentiment_rows)
    return f"""
<section class="pk-sentiment">
  <div class="pk-sentiment-prose">
    <div class="pk-eyebrow">SENTIMENT DIGEST</div>
    <h2>How coverage is trending, by Coalition</h2>
    <p>Coverage tone is not support, and not a poll.</p>
  </div>
  <div class="pk-sentiment-table-wrap">
    <table class="pk-sentiment-table">
      <thead><tr><th scope="col">Coalition</th><th scope="col">Articles</th>
      <th scope="col">Tone</th><th scope="col">Change</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
    <div class="pk-sentiment-footer">{model.sentiment_total_articles:,} articles</div>
  </div>
</section>
""".strip()


def render_homepage_body(model: HomepageModel) -> str:
    """The homepage's `body_html`, without the persistent shell around it."""
    return f"<style>{_CSS}</style>{_hero(model)}{_bill_tracker(model)}{_sentiment_digest(model)}"


def render_homepage(model: HomepageModel, *, language: Language = Language.EN) -> str:
    """The homepage as one full HTML document, shell included.

    `page_path` is always `""` (the shell's own `Home` link target) — #81's
    BM route is what would give this a second `page_path` to render at.
    """
    return render_shell(
        title="PolitikKu — Find your MP",
        active_nav="home",
        language=language,
        page_path="",
        updated_at=model.updated_at,
        sources_count=model.sources_count,
        status=model.status,
        body_html=render_homepage_body(model),
    )


_CSS = """
  .pk-eyebrow {
    font-family: var(--mono); font-size: 11px; letter-spacing: .1em;
    text-transform: uppercase; color: var(--ink-secondary);
  }
  .pk-hero {
    display: grid; grid-template-columns: 1.05fr .95fr;
  }
  .pk-hero-lookup {
    background: var(--paper); padding: 44px 34px 46px 30px;
    border-right: 1px solid var(--line-soft);
  }
  .pk-hero-lookup h1 {
    font-family: var(--serif); font-size: var(--text-hero-desktop);
    font-weight: 500; line-height: 1.06; letter-spacing: -.02em; margin: 10px 0 12px;
  }
  .pk-lede { font-size: 15px; color: var(--ink-secondary); max-width: 46ch; margin: 0 0 22px; }
  .pk-lookup-form { display: flex; gap: 10px; max-width: 490px; }
  .pk-lookup-form input {
    flex: 1; height: 52px; padding: 0 14px; font-size: 15px;
    border: 1px solid var(--line-strong); border-radius: var(--radius-md); font-family: var(--sans);
  }
  .pk-search-btn, .pk-locate-btn {
    height: 52px; padding: 0 22px; font-size: 14px; border-radius: var(--radius-md);
    font-family: var(--sans); cursor: pointer;
  }
  .pk-search-btn { background: var(--ink); color: var(--paper); border: none; }
  .pk-locate-btn {
    display: block; margin-top: 14px; width: 100%; background: transparent;
    color: var(--ink); border: 1px solid var(--line-strong);
  }
  .pk-privacy-note { font-size: 12px; color: var(--muted); margin: 8px 0 22px; }
  .pk-recent-label {
    font-family: var(--mono); font-size: 10.5px; letter-spacing: .08em;
    text-transform: uppercase; color: var(--muted); margin-bottom: 8px;
  }
  .pk-recent-list { display: flex; gap: 8px; flex-wrap: wrap; }

  .pk-hero-projection { background: var(--paper-alt); padding: 44px 30px 46px 34px; }
  .pk-eyebrow-row { display: flex; justify-content: space-between; align-items: baseline; }
  .pk-projection-headline {
    display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; margin: 14px 0 18px;
  }
  .pk-headline-number { font-family: var(--serif); font-size: var(--text-hero-desktop); }
  .pk-headline-unit { font-size: 14px; color: var(--ink-secondary); }
  .pk-hemicycle-legend {
    list-style: none; display: flex; gap: 18px; margin: 12px 0; padding: 0;
    font-size: 12px; color: var(--ink-secondary);
  }
  .pk-hemicycle-legend li { display: flex; align-items: center; gap: 6px; }
  .pk-swatch { width: 9px; height: 9px; border-radius: 50%; display: inline-block; }
  .pk-swatch-gov { background: #14203a; }
  .pk-swatch-noise { background: #d6d1c6; }
  .pk-swatch-nongov { background: #93a0ac; }
  .pk-stat-grid {
    display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin: 18px 0;
  }
  .pk-stat-grid dt {
    font-family: var(--mono); font-size: 10.5px; letter-spacing: .06em;
    text-transform: uppercase; color: var(--muted); margin: 0 0 4px;
  }
  .pk-stat-grid dd { margin: 0; font-size: 17px; font-family: var(--serif); }
  .pk-caveat { font-size: 11.5px; color: var(--muted); margin: 0; }

  .pk-bills { background: var(--paper); padding: 38px 30px; }
  .pk-section-head { display: flex; justify-content: space-between; align-items: baseline; }
  .pk-section-head h2 { font-family: var(--serif); font-size: 22px; margin: 0; }
  .pk-bill-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-top: 18px; }
  .pk-bill-card {
    background: var(--white); border: 1px solid var(--line); border-radius: var(--radius-lg);
    padding: 20px; display: flex; flex-direction: column; gap: 10px;
  }
  .pk-bill-status { display: flex; align-items: center; gap: 8px; }
  .pk-dot-positive, .pk-dot-pending { width: 6px; height: 6px; border-radius: 50%; display: inline-block; }
  .pk-dot-positive { background: var(--accent); }
  .pk-dot-pending { background: var(--caution); }
  .pk-bill-stage {
    font-family: var(--mono); font-size: 10.5px; letter-spacing: .06em; text-transform: uppercase;
    color: var(--ink-secondary);
  }
  .pk-bill-card h3 { font-family: var(--serif); font-size: 19px; margin: 0; font-weight: 500; }
  .pk-bill-card h3 a { color: var(--ink); }
  .pk-bill-summary { font-size: 13.5px; line-height: 1.5; color: var(--ink-secondary); margin: 0; }
  .pk-bill-note { font-size: 11px; color: var(--muted); }
  .pk-bill-footer {
    margin-top: auto; padding-top: 10px; border-top: 1px solid var(--line-soft);
    display: flex; justify-content: space-between; font-family: var(--mono); font-size: 11px;
    color: var(--ink-secondary);
  }

  .pk-sentiment {
    background: var(--paper-alt); padding: 38px 30px;
    display: grid; grid-template-columns: 1fr 1.15fr; gap: 44px;
  }
  .pk-sentiment-prose h2 { font-family: var(--serif); font-size: 22px; margin: 8px 0 10px; }
  .pk-sentiment-prose p { font-size: 13.5px; color: var(--ink-secondary); }
  .pk-sentiment-table-wrap {
    background: var(--white); border: 1px solid var(--line); border-radius: var(--radius-lg);
    overflow: hidden;
  }
  .pk-sentiment-table { width: 100%; border-collapse: collapse; font-size: 13px; }
  .pk-sentiment-table th {
    font-family: var(--mono); font-size: 10px; letter-spacing: .06em; text-transform: uppercase;
    color: var(--muted); text-align: left; padding: 10px 14px; border-bottom: 1px solid var(--line);
  }
  .pk-sentiment-table td { padding: 10px 14px; border-bottom: 1px solid var(--line-soft); }
  .pk-coalition small { color: var(--muted); font-family: var(--mono); font-size: 10.5px; }
  .pk-sentiment-bar { width: 80px; height: 5px; background: var(--line-soft); border-radius: 3px; }
  .pk-sentiment-fill { height: 100%; background: var(--accent); border-radius: 3px; }
  .pk-delta-up { color: var(--accent); }
  .pk-delta-down { color: var(--caution-deep); }
  .pk-delta-flat, .pk-delta-none { color: var(--muted); }
  .pk-sentiment-footer {
    padding: 10px 14px; font-family: var(--mono); font-size: 11px; color: var(--muted);
  }

  @media (max-width: 900px) {
    .pk-hero { grid-template-columns: 1fr; }
    .pk-hero-lookup, .pk-hero-projection { padding: 28px var(--gutter-mobile); border-right: none; }
    .pk-hero-lookup h1 { font-size: var(--text-hero-mobile); }
    .pk-headline-number { font-size: var(--text-hero-mobile); }
    .pk-lookup-form { flex-direction: column; }
    .pk-search-btn { width: 100%; }
    .pk-bills, .pk-sentiment { padding: 22px var(--gutter-mobile); }
    .pk-bill-grid { grid-template-columns: 1fr; }
    .pk-bill-grid .pk-bill-card:nth-child(n+3) { display: none; }
    .pk-sentiment { grid-template-columns: 1fr; gap: 20px; }
    /* Condensed rows (README §2's mobile order): drop the Tone bar — its
       exact score is still in the bar's own aria-label, never lost, only
       hidden from a narrow layout that has no room for a fourth column —
       and let the row scroll horizontally rather than clip if it still
       doesn't fit (the NOT CALIBRATED tag beside each delta adds width). */
    .pk-sentiment-table-wrap { overflow-x: auto; }
    .pk-sentiment-table th:nth-child(3), .pk-sentiment-table td:nth-child(3) { display: none; }
  }
"""


def build_homepage(engine: Engine) -> tuple[str, date]:
    """Read Storage and render the homepage. The whole I/O half, in one place.

    Mirrors `public_page.build_page` exactly, plus the two reads this page
    alone needs (`load_sentiment_snapshots` for the digest's history,
    `load_bills` for the tracker) — reading Storage once rather than the
    dashboard and this page each opening their own connection.
    """
    from lpa.config import (
        coalition_names,
        load_bills,
        load_coalition_config,
        load_election_status,
        load_state_election_signals,
        swing_model_config,
    )
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
    model = homepage_model(page, snapshots, names, load_bills())
    return render_homepage(model), model.updated_at


def main() -> None:
    """Render the homepage from Storage and write it to disk."""
    import argparse
    from pathlib import Path

    from lpa.storage import connect

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("public/politikku/index.html"),
        help="where to write the page (default: public/politikku/index.html)",
    )
    args = parser.parse_args()

    page, computed_at = build_homepage(connect())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(page, encoding="utf-8")
    print(f"Wrote {args.output} ({len(page):,} bytes), computed {computed_at}")


if __name__ == "__main__":
    main()
