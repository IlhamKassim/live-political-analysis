"""The PolitikKu Parliamentary Bills Tracker page.

Renders `/bills.html` (English) and `/ms/bills.html` (Bahasa Malaysia),
tracking all Bills before the 15th Parliament with verbatim explanatory
summaries from Parliament's official PDFs (ADR 0010) and recorded Division
voting results (ADR 0009).
"""

from __future__ import annotations

import argparse
import html
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy.engine import Engine

from lpa.bill_tracker import Bill
from lpa.config import load_bills
from lpa.domain import ElectionStatus
from lpa.politikku_shell import (
    Language,
    render_shell,
    short_date,
    t,
)

PAGE_PATH = "bills.html"


@dataclass(frozen=True)
class BillsPageModel:
    """The data backing `/bills.html` and `/ms/bills.html`."""

    bills: Sequence[Bill]
    updated_at: date
    sources_count: int
    status: ElectionStatus

    @property
    def total_bills(self) -> int:
        return len(self.bills)

    @property
    def passed_bills_count(self) -> int:
        return sum(1 for b in self.bills if "lulus" in b.stage.lower())

    @property
    def committee_bills_count(self) -> int:
        return sum(
            1 for b in self.bills if "jkpk" in b.stage.lower() or "jawatankuasa" in b.stage.lower()
        )


def bills_page_model(
    engine: Engine,
    bills: Mapping[str, Bill] | None = None,
) -> BillsPageModel:
    """Build the model for the bills tracker page from Storage and bills register."""
    from lpa.config import load_election_status
    from lpa.pipeline import today_in_malaysia
    from lpa.storage import load_projections, load_sentiment_snapshots

    projections = load_projections(engine)
    snapshots = load_sentiment_snapshots(engine)
    status = load_election_status()
    if bills is None:
        bills = load_bills()

    sorted_bills = tuple(sorted(bills.values(), key=lambda b: (b.stage_date, b.year), reverse=True))

    if projections:
        updated_at = projections[-1].computed_at
    else:
        updated_at = today_in_malaysia()

    sources_count = len(snapshots[-1].sentiment.sources) if snapshots else 0

    return BillsPageModel(
        bills=sorted_bills,
        updated_at=updated_at,
        sources_count=sources_count,
        status=status,
    )


# ── Rendering ─────────────────────────────────────────────────────────────


def _bill_card(bill: Bill, language: Language) -> str:
    stage_lower = bill.stage.lower()
    if "lulus" in stage_lower:
        dot_class = "pk-dot-positive pk-bill-dot-pass"
        stage_class = "pk-bill-stage-positive"
    elif "jkpk" in stage_lower or "jawatankuasa" in stage_lower:
        dot_class = "pk-dot-pending pk-bill-dot-committee"
        stage_class = "pk-bill-stage-pending"
    elif "tidak mendapat undi 2/3" in stage_lower or "ditarik balik" in stage_lower:
        dot_class = "pk-dot-fail pk-bill-dot-fail"
        stage_class = "pk-bill-stage-fail"
    else:
        dot_class = "pk-dot-progress pk-bill-dot-progress"
        stage_class = "pk-bill-stage-progress"

    stage_text = bill.stage
    if language is Language.EN:
        if stage_lower == "lulus":
            stage_text = "Passed"
        elif "dirujuk ke jkpk" in stage_lower:
            stage_text = "Referred to Committee"
        elif "bacaan kali pertama" in stage_lower:
            stage_text = "First Reading"
        elif "bacaan kali kedua" in stage_lower:
            stage_text = "Second Reading"
        elif "bacaan kali ketiga" in stage_lower:
            stage_text = "Third Reading"
        elif "tidak mendapat undi 2/3" in stage_lower:
            stage_text = "Failed to secure 2/3 majority at Second Reading"
        elif "ditarik balik" in stage_lower:
            stage_text = "Withdrawn"

    if bill.division is not None:
        footer = t(
            language,
            f"Division {bill.division.ayes}–{bill.division.noes}",
            f"Belah bahagian {bill.division.ayes}–{bill.division.noes}",
        )
    else:
        footer = t(language, "Voice vote", "Undian suara")

    bill_note = t(
        language,
        "Parliament's own text, Bahasa Malaysia — untranslated.",
        "Teks asal Parlimen.",
    )
    return f"""
<article class="pk-bill-card">
  <div class="pk-bill-status-row">
    <div class="pk-bill-status {stage_class}"><span class="{dot_class}"></span>
      <span class="pk-bill-stage">{html.escape(stage_text)}</span></div>
    <span class="pk-bill-vote-badge">{html.escape(footer)}</span>
  </div>
  <h3><a href="{html.escape(bill.summary_source_url)}" target="_blank" rel="noopener noreferrer">{html.escape(bill.title)}</a></h3>
  <p class="pk-bill-summary" lang="ms">{html.escape(bill.summary)}</p>
  <div class="pk-bill-note">{bill_note}</div>
  <div class="pk-bill-footer">
    <span>{html.escape(short_date(bill.stage_date))}</span>
    <span>Hansard</span>
  </div>
</article>
""".strip()


_BILLS_CSS = """
  .pk-bills-page {
    background: var(--paper);
    padding: 38px var(--gutter-desktop);
    max-width: 1120px;
    margin: 0 auto;
  }
  .pk-bills-head { margin-bottom: 24px; }
  .pk-bills-head h1 {
    font-family: var(--serif);
    font-size: var(--text-h1-desktop);
    font-weight: 500;
    line-height: 1.1;
    margin: 0 0 10px 0;
    color: var(--ink);
  }
  .pk-bills-head p {
    color: var(--ink-secondary);
    max-width: 72ch;
    font-size: 15px;
    line-height: 1.5;
    margin: 0;
  }
  .pk-bills-stats {
    display: flex;
    gap: 24px;
    margin-top: 18px;
    font-size: 13px;
    font-family: var(--mono);
  }
  .pk-bills-stats strong { color: var(--ink); font-size: 15px; }
  .pk-bills-stats span { color: var(--muted); letter-spacing: .04em; text-transform: uppercase; font-size: 11px; }
  .pk-bills-section { margin-top: 16px; margin-bottom: 40px; }
  .pk-bill-grid {
    display: grid;
    gap: 20px;
    grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  }
  
  .pk-bill-card {
    background: var(--white);
    border: 1px solid var(--line);
    border-radius: var(--radius-lg);
    padding: 20px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    transition: border-color .15s ease, box-shadow .15s ease;
  }
  .pk-bill-card:hover {
    border-color: var(--line-strong);
    box-shadow: 0 4px 12px rgba(0,0,0,.04);
  }
  .pk-bill-status-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    flex-wrap: wrap;
  }
  .pk-bill-status {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 2px 8px;
    border-radius: var(--radius-sm);
  }
  .pk-bill-status.pk-bill-stage-positive {
    background: var(--positive-bg);
    border: 1px solid var(--positive-border);
    color: var(--accent);
  }
  .pk-bill-status.pk-bill-stage-pending {
    background: var(--caution-bg);
    border: 1px solid var(--caution-border);
    color: var(--caution-deep);
  }
  .pk-bill-status.pk-bill-stage-fail {
    background: var(--paper-alt);
    border: 1px solid var(--line-strong);
    color: var(--ink-secondary);
  }
  .pk-bill-status.pk-bill-stage-progress {
    background: var(--paper-alt);
    border: 1px solid var(--line-soft);
    color: var(--ink-secondary);
  }
  .pk-bill-stage {
    font-family: var(--mono);
    font-size: 10.5px;
    letter-spacing: .06em;
    text-transform: uppercase;
    font-weight: 500;
  }
  .pk-bill-vote-badge {
    font-family: var(--mono);
    font-size: 10.5px;
    color: var(--ink-secondary);
    background: var(--paper-alt);
    border: 1px solid var(--line-soft);
    padding: 2px 6px;
    border-radius: var(--radius-sm);
  }
  .pk-bill-card h3 {
    font-family: var(--serif);
    font-size: 19px;
    margin: 0;
    font-weight: 500;
    line-height: 1.3;
  }
  .pk-bill-card h3 a { color: var(--ink); text-decoration: none; }
  .pk-bill-card h3 a:hover { color: var(--accent); text-decoration: underline; }
  .pk-bill-summary {
    font-size: 13.5px;
    line-height: 1.5;
    color: var(--ink-secondary);
    margin: 0;
    flex-grow: 1;
  }
  .pk-bill-note { font-size: 11px; color: var(--muted); font-style: italic; }
  .pk-bill-note:empty { display: none; }
  .pk-bill-footer {
    margin-top: auto;
    padding-top: 10px;
    border-top: 1px solid var(--line-soft);
    display: flex;
    justify-content: space-between;
    font-family: var(--mono);
    font-size: 11px;
    color: var(--ink-secondary);
  }
  
  .pk-dot-positive, .pk-bill-dot-pass { width: 6px; height: 6px; border-radius: 50%; display: inline-block; background-color: var(--accent); }
  .pk-dot-pending, .pk-bill-dot-committee { width: 6px; height: 6px; border-radius: 50%; display: inline-block; background-color: var(--caution); }
  .pk-dot-fail, .pk-bill-dot-fail { width: 6px; height: 6px; border-radius: 50%; display: inline-block; background-color: var(--ink-secondary); }
  .pk-dot-progress, .pk-bill-dot-progress { width: 6px; height: 6px; border-radius: 50%; display: inline-block; background-color: var(--line-strong); }

  @media (max-width: 900px) {
    .pk-bills-page { padding: 22px var(--gutter-mobile); }
    .pk-bills-head h1 { font-size: var(--text-h1-mobile); }
    .pk-bills-stats { flex-wrap: wrap; gap: 14px; }
    .pk-bill-grid { grid-template-columns: 1fr; gap: 16px; }
  }
"""


def render_bills_page(model: BillsPageModel, language: Language) -> str:
    """Render the full HTML document for the bills tracker page."""
    title = t(
        language,
        "Bills in the Dewan Rakyat — PolitikKu",
        "Rang Undang-Undang di Dewan Rakyat — PolitikKu",
    )
    description = t(
        language,
        "Track active and passed Bills before the Dewan Rakyat with verbatim summaries from Parliament's official PDFs.",
        "Jejak rang undang-undang di Dewan Rakyat dengan huraian asal daripada dokumen rasmi Parlimen.",
    )
    heading = t(
        language,
        "Bills in the Dewan Rakyat",
        "Rang Undang-Undang di Dewan Rakyat",
    )
    subhead = t(
        language,
        "Every Bill currently tracked before the 15th Parliament. Summaries are quoted verbatim from the "
        "Explanation (<em>Huraian</em>) section of Parliament's official Bills register without editorial paraphrasing.",
        "Setiap rang undang-undang yang dijejak di Parlimen ke-15. Huraian dipetik secara verbatim daripada "
        "bahagian <em>Huraian</em> dokumen rasmi Parlimen tanpa sebarang tafsiran editorial.",
    )
    stat_total = t(language, "Total Tracked", "Jumlah Dijejak")
    stat_passed = t(language, "Passed", "Lulus")
    stat_committee = t(language, "In Committee", "Dalam Jawatankuasa")

    cards = "\n".join(_bill_card(b, language) for b in model.bills)

    body_html = f"""
<style>{_BILLS_CSS}</style>
<div class="pk-bills-page">
  <section class="pk-bills-head">
    <h1>{heading}</h1>
    <p>{subhead}</p>
    <div class="pk-bills-stats">
      <div><strong>{model.total_bills}</strong> <span>{stat_total}</span></div>
      <div><strong>{model.passed_bills_count}</strong> <span>{stat_passed}</span></div>
      <div><strong>{model.committee_bills_count}</strong> <span>{stat_committee}</span></div>
    </div>
  </section>
  <section class="pk-bills-section">
    <div class="pk-bill-grid">{cards}</div>
  </section>
</div>
""".strip()

    return render_shell(
        title=title,
        description=description,
        active_nav="bills",
        language=language,
        page_path=PAGE_PATH,
        updated_at=model.updated_at,
        sources_count=model.sources_count,
        status=model.status,
        body_html=body_html,
    )


def build_and_write_bills_pages(
    engine: Engine,
    output_dir: Path | str = "public",
) -> tuple[int, int]:
    """Render and write both EN and BM versions of the bills page."""
    model = bills_page_model(engine)
    out = Path(output_dir)

    en_html = render_bills_page(model, Language.EN)
    en_path = out / PAGE_PATH
    en_path.parent.mkdir(parents=True, exist_ok=True)
    en_path.write_text(en_html, encoding="utf-8")

    ms_html = render_bills_page(model, Language.MS)
    ms_path = out / "ms" / PAGE_PATH
    ms_path.parent.mkdir(parents=True, exist_ok=True)
    ms_path.write_text(ms_html, encoding="utf-8")

    return len(en_html.encode("utf-8")), len(ms_html.encode("utf-8"))


def main() -> None:
    """CLI entry point to render the bills tracker page."""
    from lpa.storage import connect

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default="public",
        help="Directory to write output files (default: public)",
    )
    args = parser.parse_args()

    engine = connect()
    en_size, ms_size = build_and_write_bills_pages(engine, args.output_dir)
    print(
        f"Wrote {args.output_dir}/bills.html ({en_size:,} bytes) and {args.output_dir}/ms/bills.html ({ms_size:,} bytes)"
    )


if __name__ == "__main__":
    main()
