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
        dot_class = "pk-bill-dot-pass"
    elif "jkpk" in stage_lower or "jawatankuasa" in stage_lower:
        dot_class = "pk-bill-dot-committee"
    else:
        dot_class = "pk-bill-dot-progress"

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
  <div class="pk-bill-status"><span class="{dot_class}"></span>
    <span class="pk-bill-stage">{html.escape(stage_text)}</span></div>
  <h3><a href="{html.escape(bill.summary_source_url)}" target="_blank" rel="noopener noreferrer">{html.escape(bill.title)}</a></h3>
  <p class="pk-bill-summary" lang="ms">{html.escape(bill.summary)}</p>
  <div class="pk-bill-note">{bill_note}</div>
  <div class="pk-bill-footer">
    <span>{html.escape(short_date(bill.stage_date))}</span>
    <span>{html.escape(footer)}</span>
  </div>
</article>
""".strip()


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
<main class="pk-container">
  <section class="pk-section-head" style="margin-top:2rem;margin-bottom:1.5rem">
    <h1 style="font-size:2rem;font-weight:700;margin:0 0 0.5rem 0">{heading}</h1>
    <p style="color:var(--pk-text-muted, #555);max-width:720px;line-height:1.6;margin:0">{subhead}</p>
    <div style="display:flex;gap:1.5rem;margin-top:1.25rem;font-size:0.95rem">
      <div><strong>{model.total_bills}</strong> <span style="color:var(--pk-text-muted, #666)">{stat_total}</span></div>
      <div><strong>{model.passed_bills_count}</strong> <span style="color:var(--pk-text-muted, #666)">{stat_passed}</span></div>
      <div><strong>{model.committee_bills_count}</strong> <span style="color:var(--pk-text-muted, #666)">{stat_committee}</span></div>
    </div>
  </section>
  <section class="pk-bills" style="margin-top:1rem;margin-bottom:3rem">
    <div class="pk-bill-grid">{cards}</div>
  </section>
</main>
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
