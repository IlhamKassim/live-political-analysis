"""The PolitikKu News Sentiment Analysis page (#124).

Renders `/sentiment.html` (English) and `/ms/sentiment.html` (Bahasa Malaysia),
tracking daily news sentiment scores for political coalitions across Malaysian
media outlets, historical sentiment trends, and source coverage breakdowns.
"""

from __future__ import annotations

import argparse
import html
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy.engine import Engine

from lpa.domain import Coalition, ElectionStatus
from lpa.politikku_i18n import not_calibrated_tag
from lpa.politikku_shell import (
    Language,
    methodology_url,
    render_shell,
    short_date,
    t,
)
from lpa.storage import SentimentSnapshot

PAGE_PATH = "sentiment.html"
DELTA_WINDOW = timedelta(days=7)


@dataclass(frozen=True)
class SentimentPageRow:
    """One Coalition's score and coverage in the latest sentiment snapshot."""

    coalition: Coalition
    name: str
    article_count: int
    score: float
    delta: float | None


@dataclass(frozen=True)
class HistoricalSentimentPoint:
    """One day's aggregated sentiment scores for historical trend rendering."""

    computed_at: date
    total_articles: int
    scores: Mapping[Coalition, float]


@dataclass(frozen=True)
class SentimentPageModel:
    """Data backing `/sentiment.html` and `/ms/sentiment.html`."""

    updated_at: date
    sources_count: int
    status: ElectionStatus
    total_articles: int
    rows: tuple[SentimentPageRow, ...]
    history: tuple[HistoricalSentimentPoint, ...]
    sources: tuple[str, ...]


def _sentiment_rows(
    history: Sequence[SentimentSnapshot],
    names: Mapping[Coalition, str],
) -> tuple[SentimentPageRow, ...]:
    """Compute per-Coalition sentiment rows ordered by coverage volume."""
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
            SentimentPageRow(
                coalition=coalition,
                name=names.get(coalition, coalition),
                article_count=latest.article_counts[coalition],
                score=score,
                delta=delta,
            )
        )
    return tuple(rows)


def sentiment_page_model(
    engine: Engine | None = None,
    snapshots: Sequence[SentimentSnapshot] | None = None,
    names: Mapping[Coalition, str] | None = None,
    status: ElectionStatus | None = None,
) -> SentimentPageModel:
    """Build the model for the sentiment analysis page from Storage and configuration."""
    from lpa.config import coalition_names, load_coalition_config, load_election_status
    from lpa.pipeline import today_in_malaysia
    from lpa.storage import load_sentiment_snapshots

    if snapshots is None:
        if engine is None:
            from lpa.storage import connect

            engine = connect()
        snapshots = load_sentiment_snapshots(engine)

    if names is None:
        config = load_coalition_config()
        names = coalition_names(config)

    if status is None:
        status = load_election_status()

    if snapshots:
        latest = snapshots[-1]
        updated_at = latest.computed_at
        total_articles = latest.sentiment.total_articles
        sources = tuple(latest.sentiment.sources)
        sources_count = len(sources)
    else:
        updated_at = today_in_malaysia()
        total_articles = 0
        sources = ()
        sources_count = 0

    rows = _sentiment_rows(snapshots, names)

    history_points = tuple(
        HistoricalSentimentPoint(
            computed_at=snap.computed_at,
            total_articles=snap.sentiment.total_articles,
            scores=snap.sentiment.scores,
        )
        for snap in snapshots
    )

    return SentimentPageModel(
        updated_at=updated_at,
        sources_count=sources_count,
        status=status,
        total_articles=total_articles,
        rows=rows,
        history=history_points,
        sources=sources,
    )


# ── Rendering ─────────────────────────────────────────────────────────────


def _sentiment_bar(score: float, language: Language) -> str:
    """Score (clamped -1.0..+1.0) rendered as a visual bar centered at 50%."""
    clamped = max(-1.0, min(1.0, score))
    pct = (clamped + 1) / 2 * 100
    label = t(language, "Sentiment score", "Skor sentimen")
    return (
        f'<div class="pk-sent-bar" role="img" aria-label="{label} {score:+.2f}">'
        f'<div class="pk-sent-fill" style="width:{pct:.1f}%"></div></div>'
    )


def _sentiment_delta(delta: float | None, language: Language) -> str:
    if delta is None:
        return '<span class="pk-sent-delta-none">—</span>'
    arrow = "↑" if delta > 0 else "↓" if delta < 0 else "→"
    cls = (
        "pk-sent-delta-up"
        if delta > 0
        else "pk-sent-delta-down"
        if delta < 0
        else "pk-sent-delta-flat"
    )
    return f'<span class="{cls}">{arrow} {abs(delta):.2f}</span> {not_calibrated_tag(language)}'


def _score_cell(score: float) -> str:
    cls = (
        "pk-sent-score-pos"
        if score > 0.05
        else "pk-sent-score-neg"
        if score < -0.05
        else "pk-sent-score-neu"
    )
    return f'<span class="{cls}">{score:+.2f}</span>'


def _hero_section(model: SentimentPageModel, language: Language) -> str:
    eyebrow = t(language, "SENTIMENT ANALYSIS", "ANALISIS SENTIMEN")
    title = t(language, "News Sentiment Tracker", "Penjejak Sentimen Berita")
    lede = t(
        language,
        "Daily natural language processing of Malaysian political news coverage. Sentiment scores "
        "reflect media tone across monitored outlets, not voter intention or public opinion polls.",
        "Pemprosesan bahasa semula jadi harian bagi liputan berita politik Malaysia. Skor sentimen "
        "mencerminkan nada media merentasi portal berita yang dipantau, bukan niat pengundi atau tinjauan pendapat awam.",
    )
    tag = not_calibrated_tag(language)

    stat_updated = t(language, "Latest Run", "Larian Terkini")
    stat_articles = t(language, "Articles Analyzed", "Artikel Dianalisis")
    stat_sources = t(language, "Monitored Outlets", "Portal Dipantau")
    stat_snapshots = t(language, "Snapshots Stored", "Larian Disimpan")

    return f"""
<section class="pk-sent-band pk-sent-band-alt">
  <div class="pk-sent-hero">
    <div class="pk-eyebrow">{eyebrow}</div>
    <div class="pk-sent-title-row">
      <h1>{title}</h1>
      {tag}
    </div>
    <p class="pk-sent-lede">{lede}</p>
    <div class="pk-sent-stats">
      <div class="pk-sent-stat-card">
        <dt>{stat_updated}</dt>
        <dd>{html.escape(short_date(model.updated_at))}</dd>
      </div>
      <div class="pk-sent-stat-card">
        <dt>{stat_articles}</dt>
        <dd>{model.total_articles:,}</dd>
      </div>
      <div class="pk-sent-stat-card">
        <dt>{stat_sources}</dt>
        <dd>{model.sources_count}</dd>
      </div>
      <div class="pk-sent-stat-card">
        <dt>{stat_snapshots}</dt>
        <dd>{len(model.history)}</dd>
      </div>
    </div>
  </div>
</section>
""".strip()


def _latest_scores_section(model: SentimentPageModel, language: Language) -> str:
    heading = t(language, "Current Sentiment by Coalition", "Sentimen Semasa Mengikut Gabungan")
    subhead = t(
        language,
        "Coverage tone scored from -1.00 (negative) to +1.00 (positive), with 0.00 representing neutral reporting. "
        "Deltas compare against coverage 7 days prior.",
        "Nada liputan dinilai dari -1.00 (negatif) hingga +1.00 (positif), dengan 0.00 mewakili laporan neutral. "
        "Perubahan dibandingkan dengan liputan 7 hari sebelumnya.",
    )
    th_coalition = t(language, "Coalition", "Gabungan")
    th_articles = t(language, "Articles", "Artikel")
    th_score = t(language, "Score", "Skor")
    th_tone = t(language, "Tone", "Nada")
    th_change = t(language, "7-Day Change", "Perubahan 7 Hari")

    if not model.rows:
        rows_html = f'<tr><td colspan="5" style="text-align:center;padding:24px;color:var(--muted);">{t(language, "No sentiment snapshots stored yet.", "Tiada larian sentimen disimpan lagi.")}</td></tr>'
    else:
        rows_html = "".join(
            f"""<tr>
  <td><span class="pk-coalition"><strong>{html.escape(row.name)}</strong> <small>{html.escape(row.coalition)}</small></span></td>
  <td class="pk-sent-figure">{row.article_count:,}</td>
  <td class="pk-sent-figure">{_score_cell(row.score)}</td>
  <td>{_sentiment_bar(row.score, language)}</td>
  <td>{_sentiment_delta(row.delta, language)}</td>
</tr>"""
            for row in model.rows
        )

    return f"""
<section class="pk-sent-band">
  <div class="pk-sent-section-head">
    <div class="pk-eyebrow">{t(language, "LATEST DIGEST", "RINGKASAN TERKINI")}</div>
    <h2>{heading}</h2>
    <p>{subhead}</p>
  </div>
  <div class="pk-sent-table-wrap">
    <table class="pk-sent-table">
      <thead>
        <tr>
          <th scope="col">{th_coalition}</th>
          <th scope="col">{th_articles}</th>
          <th scope="col">{th_score}</th>
          <th scope="col">{th_tone}</th>
          <th scope="col">{th_change}</th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
    </table>
  </div>
</section>
""".strip()


def _historical_trend_section(model: SentimentPageModel, language: Language) -> str:
    heading = t(language, "Historical Sentiment Trend", "Tren Sentimen Sejarah")
    subhead = t(
        language,
        "Daily sentiment scores across stored runs. Tracks how coverage tone has shifted over time.",
        "Skor sentimen harian merentasi larian yang disimpan. Menjejaki perubahan nada liputan dari semasa ke semasa.",
    )
    th_date = t(language, "Date", "Tarikh")
    th_total = t(language, "Articles", "Artikel")

    # Collect all coalitions that appear in history
    coalition_keys: list[Coalition] = []
    for pt in reversed(model.history):
        for c in pt.scores:
            if c not in coalition_keys:
                coalition_keys.append(c)

    if not model.history:
        history_rows = f'<tr><td colspan="{2 + len(coalition_keys)}" style="text-align:center;padding:24px;color:var(--muted);">{t(language, "No historical runs recorded.", "Tiada larian sejarah direkodkan.")}</td></tr>'
    else:
        recent_history = list(reversed(model.history))[:14]  # Show up to 14 latest runs
        history_rows = "".join(
            f"""<tr>
  <td>{html.escape(short_date(pt.computed_at))}</td>
  <td class="pk-sent-figure">{pt.total_articles:,}</td>
  {"".join(f'<td class="pk-sent-figure">{_score_cell(pt.scores[c]) if c in pt.scores else "—"}</td>' for c in coalition_keys)}
</tr>"""
            for pt in recent_history
        )

    headers_html = f'<th scope="col">{th_date}</th><th scope="col">{th_total}</th>' + "".join(
        f'<th scope="col">{html.escape(c)}</th>' for c in coalition_keys
    )

    return f"""
<section class="pk-sent-band pk-sent-band-alt">
  <div class="pk-sent-section-head">
    <div class="pk-eyebrow">{t(language, "TIMELINE", "GARIS MASA")}</div>
    <h2>{heading}</h2>
    <p>{subhead}</p>
  </div>
  <div class="pk-sent-table-wrap">
    <table class="pk-sent-table">
      <thead><tr>{headers_html}</tr></thead>
      <tbody>{history_rows}</tbody>
    </table>
  </div>
</section>
""".strip()


def _sources_section(model: SentimentPageModel, language: Language) -> str:
    heading = t(language, "Monitored News Outlets", "Portal Berita Dipantau")
    subhead = t(
        language,
        "Articles are scraped from RSS feeds and public news portals across Malaysia in English and Bahasa Malaysia.",
        "Artikel dikumpulkan daripada suapan RSS dan portal berita awam di seluruh Malaysia dalam Bahasa Inggeris dan Bahasa Malaysia.",
    )
    if not model.sources:
        sources_list = f'<p style="color:var(--muted);">{t(language, "No outlets recorded in latest run.", "Tiada portal direkodkan dalam larian terkini.")}</p>'
    else:
        sources_list = (
            '<div class="pk-sent-sources-grid">'
            + "".join(
                f'<div class="pk-sent-source-card"><span class="pk-sent-source-name">{html.escape(src)}</span></div>'
                for src in sorted(model.sources)
            )
            + "</div>"
        )

    methodology_link_text = t(language, "Read the full methodology →", "Baca metodologi penuh →")
    methodology_href = html.escape(methodology_url(language))

    return f"""
<section class="pk-sent-band">
  <div class="pk-sent-section-head">
    <div class="pk-eyebrow">{t(language, "SOURCES & METHODOLOGY", "SUMBER & METODOLOGI")}</div>
    <h2>{heading}</h2>
    <p>{subhead}</p>
  </div>
  {sources_list}
  <div class="pk-sent-methodology-box">
    <h3>{t(language, "Model & Disclaimer", "Model & Penafian")}</h3>
    <p>{
        t(
            language,
            "News sentiment is parsed locally using the multilingual XLM-RoBERTa sentiment classification model. "
            "Media coverage reflects editorial attention and quoted statements, not electoral polling. "
            "Sentiment scores feed into the GE16 Seat Projection via uncalibrated model constants.",
            "Sentimen berita dianalisis secara setempat menggunakan model pengelasan sentimen berbilang bahasa XLM-RoBERTa. "
            "Liputan media mencerminkan perhatian editorial dan kenyataan yang dipetik, bukan tinjauan pilihan raya. "
            "Skor sentimen disalurkan ke Unjuran Kerusi PRU16 melalui pemalar model yang belum ditentukur.",
        )
    }</p>
    <a class="pk-sent-link" href="{methodology_href}">{methodology_link_text}</a>
  </div>
</section>
""".strip()


def render_sentiment_body(model: SentimentPageModel, language: Language = Language.EN) -> str:
    """The sentiment page's body HTML without the outer shell."""
    return (
        f"<style>{_CSS}</style>\n"
        f"{_hero_section(model, language)}\n"
        f"{_latest_scores_section(model, language)}\n"
        f"{_historical_trend_section(model, language)}\n"
        f"{_sources_section(model, language)}"
    )


def render_sentiment_page(
    model: SentimentPageModel,
    *,
    language: Language = Language.EN,
) -> str:
    """Render the full HTML document for the sentiment analysis page."""
    title = t(
        language,
        "News Sentiment Analysis — PolitikKu",
        "Analisis Sentimen Berita — PolitikKu",
    )
    description = t(
        language,
        "Daily news sentiment tracker for Malaysian political coalitions: coverage tone, historical trends, and media breakdown.",
        "Penjejak sentimen berita harian untuk gabungan politik Malaysia: nada liputan, tren sejarah, dan pecahan media.",
    )
    return render_shell(
        title=title,
        description=description,
        active_nav="sentiment",
        language=language,
        page_path=PAGE_PATH,
        updated_at=model.updated_at,
        sources_count=model.sources_count,
        status=model.status,
        body_html=render_sentiment_body(model, language),
    )


_CSS = """
  .pk-eyebrow {
    font-family: var(--mono); font-size: 11px; letter-spacing: .1em;
    text-transform: uppercase; color: var(--ink-secondary);
  }
  .pk-sent-band { background: var(--paper); padding: 42px var(--gutter-desktop); }
  .pk-sent-band-alt { background: var(--paper-alt); }
  .pk-sent-band + .pk-sent-band { border-top: 1px solid var(--line-soft); }

  .pk-sent-hero h1 {
    font-family: var(--serif); font-weight: 500; font-size: var(--text-h1-desktop);
    line-height: 1.08; letter-spacing: -.02em; color: var(--ink); margin: 10px 0 0;
  }
  .pk-sent-title-row { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
  .pk-sent-lede {
    font-size: 15px; line-height: 1.6; color: var(--ink-secondary); max-width: 64ch; margin: 0 0 24px;
  }
  .pk-sent-stats {
    display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px;
  }
  .pk-sent-stat-card {
    background: var(--white); border: 1px solid var(--line); border-radius: var(--radius-lg);
    padding: 16px 18px;
  }
  .pk-sent-stat-card dt {
    font-family: var(--mono); font-size: 10.5px; letter-spacing: .06em; text-transform: uppercase;
    color: var(--muted); margin: 0 0 4px;
  }
  .pk-sent-stat-card dd {
    margin: 0; font-family: var(--serif); font-size: 24px; color: var(--ink);
  }

  .pk-sent-section-head { margin-bottom: 20px; }
  .pk-sent-section-head h2 {
    font-family: var(--serif); font-weight: 500; font-size: 24px; letter-spacing: -.015em;
    color: var(--ink); margin: 6px 0 8px;
  }
  .pk-sent-section-head p { font-size: 13.5px; line-height: 1.5; color: var(--ink-secondary); margin: 0; max-width: 72ch; }

  .pk-sent-table-wrap {
    background: var(--white); border: 1px solid var(--line); border-radius: var(--radius-lg);
    overflow: hidden; overflow-x: auto;
  }
  .pk-sent-table { width: 100%; border-collapse: collapse; font-size: 13.5px; }
  .pk-sent-table th {
    font-family: var(--mono); font-size: 10px; letter-spacing: .06em; text-transform: uppercase;
    color: var(--muted); text-align: left; padding: 10px 14px; border-bottom: 1px solid var(--line);
    white-space: nowrap;
  }
  .pk-sent-table td {
    padding: 10px 14px; border-bottom: 1px solid var(--line-soft); color: var(--ink);
  }
  .pk-sent-table tbody tr:last-child td { border-bottom: none; }
  .pk-sent-figure { font-variant-numeric: tabular-nums; }

  .pk-coalition { display: inline-flex; align-items: center; gap: 6px; }
  .pk-coalition small { font-family: var(--mono); font-size: 10.5px; color: var(--muted); }

  .pk-sent-bar { width: 90px; height: 6px; background: var(--line-soft); border-radius: 3px; overflow: hidden; }
  .pk-sent-fill { height: 100%; background: var(--accent); border-radius: 3px; }

  .pk-sent-score-pos { color: var(--accent); font-weight: 500; }
  .pk-sent-score-neg { color: var(--caution-deep); font-weight: 500; }
  .pk-sent-score-neu { color: var(--ink-secondary); }

  .pk-sent-delta-up { color: var(--accent); }
  .pk-sent-delta-down { color: var(--caution-deep); }
  .pk-sent-delta-flat, .pk-sent-delta-none { color: var(--muted); }

  .pk-sent-sources-grid {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; margin-bottom: 24px;
  }
  .pk-sent-source-card {
    background: var(--white); border: 1px solid var(--line); border-radius: var(--radius-md);
    padding: 12px 14px; font-size: 13.5px; color: var(--ink);
  }
  .pk-sent-methodology-box {
    background: var(--white); border: 1px solid var(--line); border-radius: var(--radius-lg);
    padding: 20px 22px; max-width: 78ch;
  }
  .pk-sent-methodology-box h3 {
    font-family: var(--serif); font-weight: 500; font-size: 18px; margin: 0 0 8px; color: var(--ink);
  }
  .pk-sent-methodology-box p { font-size: 13.5px; line-height: 1.6; color: var(--ink-secondary); margin: 0 0 12px; }
  .pk-sent-link { font-size: 13.5px; color: var(--accent); }

  @media (max-width: 900px) {
    .pk-sent-band { padding: 24px var(--gutter-mobile); }
    .pk-sent-hero h1 { font-size: var(--text-h1-mobile); }
    .pk-sent-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  }
  @media (max-width: 600px) {
    .pk-sent-stats { grid-template-columns: 1fr; }
  }
"""


def build_and_write_sentiment_pages(
    engine: Engine,
    output_dir: Path | str = "public",
) -> tuple[int, int]:
    """Render and write both EN and BM versions of the sentiment page."""
    model = sentiment_page_model(engine)
    out = Path(output_dir)

    en_html = render_sentiment_page(model, language=Language.EN)
    en_path = out / PAGE_PATH
    en_path.parent.mkdir(parents=True, exist_ok=True)
    en_path.write_text(en_html, encoding="utf-8")

    ms_html = render_sentiment_page(model, language=Language.MS)
    ms_path = out / "ms" / PAGE_PATH
    ms_path.parent.mkdir(parents=True, exist_ok=True)
    ms_path.write_text(ms_html, encoding="utf-8")

    return len(en_html.encode("utf-8")), len(ms_html.encode("utf-8"))


def build_all_sentiment_languages(engine: Engine) -> list[tuple[Language, str, date]]:
    """Build sentiment pages for all supported languages."""
    model = sentiment_page_model(engine)
    return [
        (language, render_sentiment_page(model, language=language), model.updated_at)
        for language in Language
    ]


def main() -> None:
    """CLI entry point to render the sentiment analysis page."""
    from lpa.storage import connect

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default="public",
        help="Directory to write output files (default: public)",
    )
    args = parser.parse_args()

    engine = connect()
    en_size, ms_size = build_and_write_sentiment_pages(engine, args.output_dir)
    print(
        f"Wrote {args.output_dir}/sentiment.html ({en_size:,} bytes) and "
        f"{args.output_dir}/ms/sentiment.html ({ms_size:,} bytes)"
    )


if __name__ == "__main__":
    main()
