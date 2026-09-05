"""The PolitikKu Parliamentary Bills Tracker page (#143).

Renders `/bills/` (English) and `/ms/bills/` (Bahasa Malaysia), tracking all
Bills before the 15th Parliament with verbatim explanatory summaries from
Parliament's official PDFs (ADR 0010) and recorded Division voting results
(ADR 0009).

Recovered from git history (`2bf8e68^:src/lpa/politikku_bills.py`, retired by
ADR 0014) and rebuilt against #143's two decisions: the model reads
`frontend/public/data/bills.json` directly — the exact file `app.js` already
fetches for the client-rendered `#bills-view` — rather than recomputing
anything from Storage, so the Python and JS renderings of this page can never
silently disagree; and the markup matches `app.js`'s CURRENT `#bills-view`
DOM contract (`pol-dir dewan-page bills-page`, `bill-expandable`,
`#bills-rows`/`#bills-search`/`#bills-stage`) rather than this file's own
retired `pk-bill-*` print-register classes, so `app.js`'s existing
`renderBillsRows()`/`billsRows()` can hydrate onto this server-rendered
markup without modification (see `frontend/public/app.js` around lines
4803-5001).
"""

from __future__ import annotations

import argparse
import html
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from lpa.bill_tracker import Bill
from lpa.config import load_bills
from lpa.domain import ElectionStatus
from lpa.politikku_shell import (
    Language,
    render_shell,
    t,
)

PAGE_PATH = "bills/"
"""Passed to `render_shell` as `page_path` with the default `POLITIKKU_PREFIX`
("/"), so `route()` computes `/bills/` (EN) and `/ms/bills/` (BM) — the
directory-with-`index.html` shape #143 settled on, matching `/projection/`
rather than the retired flat `bills.html` file this page used to be."""

FRONTEND_BILLS_JSON = Path("frontend/public/data/bills.json")
"""The one file this page's model reads — the same path `app.js`'s
`openBillsPage()` fetches (`data/bills.json`, relative to `frontend/public/`).
Reading this instead of Storage is the drift fix #143 calls out: today
`politikku_sentiment.py` and the SPA's sentiment view compute independently
from Storage with no diff ever run between them, and this renderer is built
so it cannot repeat that mistake for Bills."""


@dataclass(frozen=True)
class BillsPageModel:
    """The data backing `/bills/` and `/ms/bills/`."""

    bills: Sequence[Bill]
    updated_at: date
    status: ElectionStatus
    sources_count: int = 0
    """`render_shell`'s trust strip always states "N news sources read" —
    a Sentiment-page concept this page has no equivalent of. The retired
    renderer borrowed the *Sentiment* page's own source count here, which
    read as a real number for the wrong page. Zero is the honest value:
    Bills tracks Parliament's own register, not news coverage."""

    @property
    def total_bills(self) -> int:
        return len(self.bills)

    @property
    def passed_bills_count(self) -> int:
        return sum(1 for b in self.bills if "lulus" in b.stage.lower())

    @property
    def divisions_count(self) -> int:
        return sum(1 for b in self.bills if b.division is not None)

    @property
    def stages(self) -> tuple[str, ...]:
        """Every distinct stage label present, sorted — backs `#bills-stage`'s
        options the same way `billsRows()`'s `[...new Set(...)]` does."""
        return tuple(sorted({b.stage for b in self.bills if b.stage}))


def _load_bills_and_retrieved(path: Path) -> tuple[Mapping[str, Bill], date | None]:
    """`load_bills()`'s parsed records, plus `_source.retrieved` from the
    same file — the one piece of "when was this current" metadata
    `bills.json` itself carries, used in place of a Storage-derived
    `updated_at` (see the module docstring's drift-avoidance rationale)."""
    bills = load_bills(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    retrieved_str = raw.get("_source", {}).get("retrieved")
    retrieved = date.fromisoformat(retrieved_str) if retrieved_str else None
    return bills, retrieved


def bills_page_model(
    bills: Mapping[str, Bill] | None = None,
    retrieved: date | None = None,
    status: ElectionStatus | None = None,
) -> BillsPageModel:
    """Build the model for the bills tracker page.

    Every argument defaults to a real read (`bills`/`retrieved` from
    `frontend/public/data/bills.json`, `status` from
    `data/election_status.json`) so `main()` can call this with none of
    them; tests pass all three explicitly and this function then touches no
    file, matching `sentiment_page_model`'s shape.
    """
    from lpa.config import load_election_status
    from lpa.pipeline import today_in_malaysia

    if bills is None or retrieved is None:
        loaded_bills, loaded_retrieved = _load_bills_and_retrieved(FRONTEND_BILLS_JSON)
        if bills is None:
            bills = loaded_bills
        if retrieved is None:
            retrieved = loaded_retrieved

    if status is None:
        status = load_election_status()

    sorted_bills = tuple(sorted(bills.values(), key=lambda b: (b.stage_date, b.code), reverse=True))

    updated_at = retrieved if retrieved is not None else today_in_malaysia()

    return BillsPageModel(
        bills=sorted_bills,
        updated_at=updated_at,
        status=status,
    )


# ── Rendering ─────────────────────────────────────────────────────────────


def _swatch_text_color(bg_hex: str) -> str:
    """Readable foreground for a stage/division pill's background colour.

    A faithful, standalone port of `lib.js`'s `swatchTextColor` (WCAG
    contrast of near-black vs. white against the background, picking
    whichever wins) — kept tiny and dependency-free rather than shelling
    out to Node, since this page needs exactly six fixed colours' worth of
    it and the algorithm is this short."""
    h = bg_hex.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))

    def _channel(v: int) -> float:
        c = v / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    def _rel_lum(rgb: tuple[int, int, int]) -> float:
        cr, cg, cb = (_channel(v) for v in rgb)
        return 0.2126 * cr + 0.7152 * cg + 0.0722 * cb

    def _contrast(a: tuple[int, int, int], bg: tuple[int, int, int]) -> float:
        la, lb = _rel_lum(a), _rel_lum(bg)
        hi, lo = max(la, lb), min(la, lb)
        return (hi + 0.05) / (lo + 0.05)

    rgb = (r, g, b)
    ink = (5, 7, 12)
    white = (255, 255, 255)
    return "#05070c" if _contrast(ink, rgb) >= _contrast(white, rgb) else "#fff"


def _pill_style(bg_hex: str) -> str:
    return f"background:{bg_hex};color:{_swatch_text_color(bg_hex)}"


def _bill_stage_color(stage: str) -> str:
    """Faithful port of `app.js`'s `billStageColor()`."""
    s = stage.lower()
    if "lulus" in s:
        return "#16a34a"
    if "jkpk" in s or "jawatankuasa" in s:
        return "#d97706"
    if "bacaan" in s:
        return "#2563eb"
    if "tidak mendapat undi" in s or "tolak" in s:
        return "#dc2626"
    if "tarik" in s:
        return "#64748b"
    return "#64748b"


_DIVISION_PILL_COLOR = "#4338ca"


def _bill_row(bill: Bill, language: Language) -> str:
    """One `<dt>`/`<dd>` pair, matching `renderBillsRows()`'s markup exactly
    so `app.js` can re-render on top of this without a DOM shape change."""
    stage_pill = (
        f'<span class="pill" style="{_pill_style(_bill_stage_color(bill.stage))}">'
        f"{html.escape(bill.stage)}</span>"
    )
    division_pill = (
        f'<span class="pill" style="{_pill_style(_DIVISION_PILL_COLOR)}">'
        f"{html.escape(t(language, 'Division vote', 'Undian belah bahagian'))}</span>"
        if bill.division is not None
        else ""
    )
    source_link = (
        f'<p class="bill-source-p"><a href="{html.escape(bill.summary_source_url)}" '
        f'target="_blank" rel="noopener noreferrer">'
        f"{html.escape(t(language, 'View source PDF', 'Lihat PDF sumber'))} ↗</a></p>"
        if bill.summary_source_url
        else ""
    )
    if bill.division is not None:
        d = bill.division
        votes = t(
            language,
            f"{d.ayes} aye · {d.noes} no · {d.abstentions} abstain · {d.absent} absent",
            f"{d.ayes} setuju · {d.noes} tidak · {d.abstentions} berkecuali · {d.absent} tidak hadir",
        )
        hansard_link = (
            f"<dt>{html.escape(t(language, 'Hansard record', 'Rekod Hansard'))}</dt>"
            f'<dd><a href="{html.escape(d.hansard_url)}" target="_blank" rel="noopener noreferrer">'
            f"{html.escape(t(language, 'Hansard record', 'Rekod Hansard'))} ↗</a></dd>"
            if d.hansard_url
            else ""
        )
        division_box_body = f"""
                  <dl class="rows bill-division-rows">
                    <dt>{html.escape(t(language, "Stage", "Peringkat"))}</dt><dd>{html.escape(d.outcome or bill.stage)}</dd>
                    <dt>{html.escape(t(language, "Date", "Tarikh"))}</dt><dd class="mono">{html.escape(d.sitting_date.isoformat())}</dd>
                    <dt>{html.escape(t(language, "Division votes", "Undian belah bahagian"))}</dt><dd class="mono">{html.escape(votes)}</dd>
                    {hansard_link}
                  </dl>"""
    else:
        voice_vote_note = t(
            language,
            "No recorded Division — passed on voice vote "
            "(Hansard records a decision with no individual roll-call).",
            "Tiada undian belah bahagian direkodkan — diluluskan melalui undian "
            "suara (Hansard merekodkan keputusan tanpa senarai undi individu).",
        )
        division_box_body = (
            f'<p class="bill-voice-vote-note muted">{html.escape(voice_vote_note)}</p>'
        )

    return f"""
        <dt class="bill-col-meta">
          <span class="bill-code mono">{html.escape(bill.code)}</span>
          <span class="bill-stage">{stage_pill}</span>
          <span class="bill-date mono muted">{html.escape(bill.stage_date.isoformat())}</span>
          {division_pill}
        </dt>
        <dd class="bill-col-content">
          <details class="bill-expandable">
            <summary class="bill-summary-trigger">
              <span class="bill-title-text">{html.escape(bill.title)}</span>
              <span class="bill-toggle-indicator" aria-hidden="true">▾</span>
            </summary>
            <div class="bill-expanded-content">
              <div class="bill-huraian">
                <p class="bill-huraian-p">{html.escape(bill.summary)}</p>
                {source_link}
              </div>
              <div class="bill-division-box">
                <div class="bill-division-label">{html.escape(t(language, "Division vote", "Undian belah bahagian"))}</div>
                {division_box_body}
              </div>
            </div>
          </details>
        </dd>"""


def render_bills_rows(model: BillsPageModel, language: Language) -> str:
    """The `#bills-rows` contents — every Bill, in the model's sort order
    (date descending), with no query/stage filter applied. `app.js`'s
    `renderBillsRows()` re-derives and re-sorts this client-side once it
    loads `data/bills.json`; this is the crawler- and no-JS-visible version,
    not a cache of the client behaviour."""
    if not model.bills:
        return f'<p class="pol-dir-empty">{html.escape(t(language, "No bills match your search or filter.", "Tiada RUU yang sepadan dengan carian atau penapis."))}</p>'
    rows = "".join(_bill_row(b, language) for b in model.bills)
    return f'<dl class="rows bills-table">{rows}</dl>'


_BILLS_CSS = """
  .bills-page .dewan-tiles { margin: 18px 0; }
"""


def render_bills_body(model: BillsPageModel, language: Language = Language.EN) -> str:
    """The bills tracker page's body HTML without the outer shell — the
    `#bills-view` contract `app.js` hydrates onto."""
    stage_options = "".join(
        f'<option value="{html.escape(s)}">{html.escape(s)}</option>' for s in model.stages
    )
    sort_labels = {
        "date": t(language, "Date", "Tarikh"),
        "code": t(language, "Code", "Kod"),
        "division": t(language, "Division", "Undian"),
    }
    sort_buttons = "".join(
        f'<button type="button" data-bills-sort="{key}" class="{"on" if key == "date" else ""}">'
        f"{html.escape(label)}</button>"
        for key, label in sort_labels.items()
    )
    count_text = t(language, f"{model.total_bills} bills", f"{model.total_bills} RUU")
    retrieved_text = t(
        language,
        f"Retrieved {model.updated_at.isoformat()}",
        f"Diambil {model.updated_at.isoformat()}",
    )

    return f"""
<style>{_BILLS_CSS}</style>
<div id="bills-view">
  <div class="pol-dir dewan-page bills-page">
    <div class="pol-dir-head">
      <h1>{html.escape(t(language, "Bill tracker", "Penjejak Rang Undang-Undang"))}</h1>
      <p class="pol-dir-sub">{
        html.escape(
            t(
                language,
                "All Bills before the 15th Parliament with verbatim explanatory statements and division votes.",
                "Semua Rang Undang-Undang di hadapan Parlimen ke-15 berserta pernyataan penjelasan verbatim dan undian belah bahagian.",
            )
        )
    }</p>
    </div>
    <div class="dewan-tiles">
      <div class="dewan-tile"><span class="muted">{
        html.escape(t(language, "Total Bills", "Jumlah RUU"))
    }</span><b class="mono">{model.total_bills}</b></div>
      <div class="dewan-tile"><span class="muted">{
        html.escape(t(language, "Passed", "Lulus"))
    }</span><b class="mono">{model.passed_bills_count}</b></div>
      <div class="dewan-tile"><span class="muted">{
        html.escape(t(language, "Recorded Divisions", "Undian Belah Bahagian"))
    }</span><b class="mono">{model.divisions_count}</b></div>
    </div>
    <div class="pol-dir-controls dewan-controls bills-controls">
      <input id="bills-search" class="pol-dir-search" type="search" autocomplete="off" spellcheck="false"
        placeholder="{
        html.escape(
            t(language, "Search bill code, title or excerpt…", "Cari kod, tajuk atau petikan RUU…")
        )
    }" />
      <select id="bills-stage" class="pol-dir-select" aria-label="{
        html.escape(t(language, "All stages", "Semua peringkat"))
    }">
        <option value="">{html.escape(t(language, "All stages", "Semua peringkat"))}</option>
        {stage_options}
      </select>
      <div class="seg chip dewan-sorts bills-sorts" role="group" aria-label="{
        html.escape(t(language, "Sort bills", "Susun RUU"))
    }">
        {sort_buttons}
      </div>
    </div>
    <div id="bills-count" class="pol-dir-count">{html.escape(count_text)}</div>
    <div id="bills-rows">{render_bills_rows(model, language)}</div>
    <div class="note dewan-page-note">{
        html.escape(
            t(
                language,
                "Bills tracked from the official Dewan Rakyat register. Summaries are verbatim excerpts of each Bill's own explanatory statement (ADR 0010).",
                "RUU dijejak daripada daftar rasmi Dewan Rakyat. Huraian adalah petikan verbatim daripada pernyataan penjelasan setiap RUU (ADR 0010).",
            )
        )
    }</div>
    <p class="pol-dir-src">{
        html.escape(
            t(
                language,
                "Source: Parlimen Malaysia — Rang Undang-Undang register",
                "Sumber: Parlimen Malaysia — Daftar Rang Undang-Undang",
            )
        )
    } · {html.escape(retrieved_text)}</p>
  </div>
</div>
""".strip()


def render_bills_page(model: BillsPageModel, language: Language = Language.EN) -> str:
    """Render the full HTML document for `/bills/` / `/ms/bills/`."""
    title = t(
        language,
        "Bills in the Dewan Rakyat — PolitikKu",
        "Rang Undang-Undang di Dewan Rakyat — PolitikKu",
    )
    description = t(
        language,
        "Track active and passed Bills before the Dewan Rakyat with verbatim summaries from "
        "Parliament's official PDFs and recorded Division votes.",
        "Jejak rang undang-undang di Dewan Rakyat dengan huraian asal daripada dokumen rasmi "
        "Parlimen dan rekod undian belah bahagian.",
    )
    return render_shell(
        title=title,
        description=description,
        active_nav="bills",
        language=language,
        page_path=PAGE_PATH,
        updated_at=model.updated_at,
        sources_count=model.sources_count,
        status=model.status,
        body_html=render_bills_body(model, language),
    )


def build_and_write_bills_pages(output_dir: Path | str = "public") -> tuple[int, int]:
    """Render and write both EN and BM versions of the bills tracker page,
    each as a directory with an `index.html` (`public/bills/index.html`,
    `public/ms/bills/index.html`) — matching `/projection/`'s shape rather
    than the retired flat `bills.html` file."""
    model = bills_page_model()
    out = Path(output_dir)

    en_html = render_bills_page(model, Language.EN)
    en_path = out / "bills" / "index.html"
    en_path.parent.mkdir(parents=True, exist_ok=True)
    en_path.write_text(en_html, encoding="utf-8")

    ms_html = render_bills_page(model, Language.MS)
    ms_path = out / "ms" / "bills" / "index.html"
    ms_path.parent.mkdir(parents=True, exist_ok=True)
    ms_path.write_text(ms_html, encoding="utf-8")

    return len(en_html.encode("utf-8")), len(ms_html.encode("utf-8"))


def main() -> None:
    """CLI entry point to render the bills tracker page."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default="public",
        help="Directory to write output files (default: public)",
    )
    args = parser.parse_args()

    en_size, ms_size = build_and_write_bills_pages(args.output_dir)
    print(
        f"Wrote {args.output_dir}/bills/index.html ({en_size:,} bytes) and "
        f"{args.output_dir}/ms/bills/index.html ({ms_size:,} bytes)"
    )


if __name__ == "__main__":
    main()
