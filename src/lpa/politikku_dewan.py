"""The PolitikKu Dewan Rakyat Activity page.

Renders `/dewan/` (English) and `/ms/dewan/` (Bahasa Malaysia), tracking sitting
attendance, speech turns, oral Q&A, and last spoken dates from the official
Dewan Rakyat Hansard.

Follows the `page_model()` / `render_*_body()` / `render_*_page()` shape:
- `dewan_page_model()` replicates `dewanRows()` join (Hansard x seat layer x MP roster)
  purely over flat JSON files with no database/Storage access.
- `render_dewan_body()` emits markup matching `app.js`'s `#dewan-view` element
  IDs and CSS classes exactly.
- `render_dewan_page()` wraps in `render_shell()` with per-route meta/OG tags.
"""

from __future__ import annotations

import argparse
import html
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from lpa.domain import ElectionStatus
from lpa.politikku_shell import (
    Language,
    render_shell,
    t,
)

PAGE_DIR = "dewan"

# Palette colors and contrast logic mirroring frontend/public/lib.js
COALITION_COLORS: dict[str, str] = {
    "PH": "#d7263d",
    "PN": "#15387c",
    "BN": "#1f9bd6",
    "GPS": "#b8332e",
    "GRS": "#e8772e",
    "WARISAN": "#16a085",
    "KDM": "#8e44ad",
    "PBM": "#6c7a89",
    "BEBAS": "#8a97a6",
    "STAR": "#b08a1f",
    "UPKO": "#2e8b57",
    "PSB": "#9b4d8a",
}


def party_color(p: str | None) -> str:
    """Map coalition or party name to swatch color."""
    return COALITION_COLORS.get((p or "").upper(), "#5d6b7d")


def _hex_to_rgb(hex_code: str) -> tuple[int, int, int] | None:
    s = hex_code.strip().removeprefix("#")
    if len(s) == 3:
        s = "".join(c + c for c in s)
    if len(s) != 6:
        return None
    try:
        n = int(s, 16)
        return ((n >> 16) & 255, (n >> 8) & 255, n & 255)
    except ValueError:
        return None


def _rel_lum(rgb: tuple[int, int, int]) -> float:
    channels = []
    for v in rgb:
        c = v / 255.0
        channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def _contrast_ratio(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    l1 = _rel_lum(a)
    l2 = _rel_lum(b)
    hi = max(l1, l2)
    lo = min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def swatch_text_color(bg: str) -> str:
    """Choose readable foreground text (#05070c or #fff) for background swatch."""
    rgb = _hex_to_rgb(bg)
    if not rgb:
        return "#fff"
    white = (255, 255, 255)
    ink = (5, 7, 12)
    return "#05070c" if _contrast_ratio(ink, rgb) >= _contrast_ratio(white, rgb) else "#fff"


def pill_style(bg: str, fg: str | None = None) -> str:
    """Generate CSS style attribute string for badge pills."""
    return f"background:{bg};color:{fg or swatch_text_color(bg)}"


def format_dewan_date(iso_date: str | None, language: Language = Language.EN) -> str:
    """Format an ISO date string (YYYY-MM-DD) into locale-aware short date."""
    if not iso_date:
        return ""
    try:
        d = date.fromisoformat(iso_date)
    except (ValueError, TypeError):
        return str(iso_date)
    if language is Language.MS:
        months_ms = (
            "Jan",
            "Feb",
            "Mac",
            "Apr",
            "Mei",
            "Jun",
            "Jul",
            "Ogo",
            "Sep",
            "Okt",
            "Nov",
            "Dis",
        )
        return f"{d.day} {months_ms[d.month - 1]} {d.year}"
    months_en = (
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    )
    return f"{d.day} {months_en[d.month - 1]} {d.year}"


@dataclass(frozen=True)
class DewanRow:
    """One constituency row in the Dewan activity table."""

    code: str
    seat_name: str
    state: str
    mp: str
    coalition: str
    turns: int
    qa: int
    sittings: int
    pct: int
    last: str


@dataclass(frozen=True)
class DewanPageModel:
    """Data model backing the Dewan activity page."""

    sittings_total: int
    from_date: str
    to_date: str
    top_mp: DewanRow | None
    median_turns: int
    coalitions: tuple[str, ...]
    rows: tuple[DewanRow, ...]
    all_rows: tuple[DewanRow, ...]


def dewan_page_model(
    seats_data: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None,
    hansard_data: Mapping[str, Any] | None,
    politicians_data: Mapping[str, Any] | None,
) -> DewanPageModel:
    """Pure, I/O-free model building replicating app.js:dewanRows().

    Joins seats x Hansard records x MP profiles purely over in-memory dictionaries.
    """
    if not seats_data or not hansard_data:
        return DewanPageModel(
            sittings_total=0,
            from_date="",
            to_date="",
            top_mp=None,
            median_turns=0,
            coalitions=(),
            rows=(),
            all_rows=(),
        )

    if isinstance(seats_data, Mapping) and "seats" in seats_data:
        raw_seats: Sequence[Mapping[str, Any]] = seats_data["seats"]
    elif isinstance(seats_data, Sequence):
        raw_seats = seats_data
    else:
        raw_seats = ()

    meta = hansard_data.get("meta") or {}
    total = meta.get("sittings", 0)
    hd_seats = hansard_data.get("seats") or {}
    mps = politicians_data.get("mps", {}) if politicians_data else {}

    all_rows_list: list[DewanRow] = []
    for seat in raw_seats:
        code = str(seat.get("code", ""))
        rec = hd_seats.get(code)
        mp_entry = mps.get(code) or {}

        turns = int(rec.get("turns", 0)) if rec else 0
        qa = int(rec.get("qa", 0)) if rec else 0
        sittings = int(rec.get("sittings", 0)) if rec else 0
        pct = round((sittings / total) * 100) if rec and total else 0
        last = str(rec.get("last", "")) if rec else ""

        mp_name = str(mp_entry.get("name", ""))
        coalition = str(mp_entry.get("coalition") or mp_entry.get("party") or "")

        all_rows_list.append(
            DewanRow(
                code=code,
                seat_name=str(seat.get("name", "")),
                state=str(seat.get("state", "")),
                mp=mp_name,
                coalition=coalition,
                turns=turns,
                qa=qa,
                sittings=sittings,
                pct=pct,
                last=last,
            )
        )

    all_rows = tuple(all_rows_list)

    # Initial sort in app.js defaults to turns descending
    sorted_rows = tuple(sorted(all_rows_list, key=lambda r: r.turns, reverse=True))
    top_mp = sorted_rows[0] if sorted_rows else None

    turn_values = sorted(r.turns for r in all_rows_list)
    median_turns = turn_values[len(turn_values) // 2] if turn_values else 0

    unique_coalitions = sorted({r.coalition for r in all_rows_list if r.coalition})

    return DewanPageModel(
        sittings_total=total,
        from_date=str(meta.get("from", "")),
        to_date=str(meta.get("to", "")),
        top_mp=top_mp,
        median_turns=median_turns,
        coalitions=tuple(unique_coalitions),
        rows=sorted_rows,
        all_rows=all_rows,
    )


def render_dewan_body(model: DewanPageModel, language: Language = Language.EN) -> str:
    """Render the inner body HTML matching app.js #dewan-view element IDs/classes."""
    back_label = t(language, "Back to map", "Kembali ke peta")
    page_title = t(language, "Dewan Rakyat activity", "Aktiviti Dewan Rakyat")

    from_str = format_dewan_date(model.from_date, language)
    to_str = format_dewan_date(model.to_date, language)
    page_sub = t(
        language,
        f"Who speaks in Parliament — every recorded speech turn in the official Hansard, "
        f"{from_str} – {to_str} ({model.sittings_total} sittings).",
        f"Siapa bersuara di Parlimen — setiap giliran ucapan yang direkodkan dalam Hansard rasmi, "
        f"{from_str} – {to_str} ({model.sittings_total} sidang).",
    )

    tile_sittings = t(language, "Sittings covered", "Sidang diliputi")
    tile_top = t(language, "Most active", "Paling aktif")
    tile_median = t(language, "Median turns", "Median giliran")

    top_mp_name = html.escape(model.top_mp.mp) if model.top_mp and model.top_mp.mp else "—"
    top_turns_str = (
        f'{model.top_mp.turns:,} {t(language, "turns", "giliran")}' if model.top_mp else ""
    )

    search_ph = t(language, "Search an MP, seat or state…", "Cari Ahli Parlimen, kerusi atau negeri…")
    all_coal = t(language, "All coalitions", "Semua gabungan")
    sort_aria = t(language, "Sort by", "Susun ikut")

    sort_turns = t(language, "Turns", "Giliran")
    sort_qa = t(language, "Q&A", "Soal jawab")
    sort_pct = t(language, "% Sittings", "% Sidang")
    sort_recent = t(language, "Recent", "Terkini")

    col_mp = t(language, "MP · seat", "Ahli Parlimen · kerusi")
    col_turns = t(language, "Turns", "Giliran")
    col_qa = t(language, "Q&A", "Soal jawab")
    col_pct = t(language, "Sittings", "Sidang")
    col_last = t(language, "Last spoke", "Terakhir")

    count_str = t(language, f"{len(model.rows)} seats", f"{len(model.rows)} kerusi")

    coalition_options = "".join(
        f'<option value="{html.escape(c)}">{html.escape(c)}</option>' for c in model.coalitions
    )

    if model.rows:
        rows_parts = []
        for i, r in enumerate(model.rows, start=1):
            view_title = t(
                language,
                f"View Parliament seat {r.code} on map →",
                f"Lihat kerusi Parlimen {r.code} di peta →",
            )
            mp_display = html.escape(r.mp) if r.mp else t(language, "Seat vacant", "Kerusi kosong")
            last_display = (
                html.escape(format_dewan_date(r.last, language)) if r.last else "—"
            )
            badge_color = party_color(r.coalition)
            badge_style = pill_style(badge_color)
            coalition_label = html.escape(r.coalition or "—")

            rows_parts.append(
                f"""    <button class="dewan-tr" type="button" data-dewan-seat="{html.escape(r.code)}" """
                f"""title="{html.escape(view_title)}">\n"""
                f"""      <span class="dewan-rank mono">{i}</span>\n"""
                f"""      <span class="dewan-mp">\n"""
                f"""        <b>{mp_display}</b>\n"""
                f"""        <span class="muted">{html.escape(r.code)} · {html.escape(r.seat_name)} · """
                f"""{html.escape(r.state)}</span>\n"""
                f"""      </span>\n"""
                f"""      <span class="dewan-coal"><span class="pill" style="{badge_style}">{coalition_label}</span></span>\n"""
                f"""      <span class="dewan-num mono">{r.turns:,}</span>\n"""
                f"""      <span class="dewan-num dewan-col-qa mono">{r.qa:,}</span>\n"""
                f"""      <span class="dewan-num mono">{r.pct}%</span>\n"""
                f"""      <span class="dewan-num dewan-col-last mono">{last_display}</span>\n"""
                f"""    </button>"""
            )
        rows_html = "\n".join(rows_parts)
    else:
        empty_msg = t(language, "No matching representatives", "Tiada wakil yang sepadan")
        rows_html = f'<p class="pol-dir-empty">{html.escape(empty_msg)}</p>'

    method_note = t(
        language,
        "Turns are recorded speech turns in the official transcript; presiding-chair procedure "
        "is excluded. Frequency is not quality — read the full Hansard from any seat's Parliament tab.",
        "Giliran ialah giliran ucapan yang direkodkan dalam transkrip rasmi; urusan pengerusi majlis "
        "dikecualikan. Kekerapan bukan ukuran kualiti — baca Hansard penuh melalui tab Dewan mana-mana kerusi.",
    )
    source_label = t(language, "Source: Official Hansard, Parliament of Malaysia.", "Sumber: Hansard rasmi Parlimen Malaysia.")
    coverage_label = t(
        language,
        f"Coverage: {from_str} – {to_str} · {model.sittings_total} Dewan Rakyat sittings, 15th Parliament.",
        f"Liputan: {from_str} – {to_str} · {model.sittings_total} persidangan Dewan Rakyat, Parlimen ke-15.",
    )

    return f"""<section id="dewan-view" aria-label="{html.escape(page_title)}">
    <div class="pol-dir dewan-page">
      <div class="pol-dir-head">
        <button class="pol-back" type="button" data-dewan-back>
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 18l-6-6 6-6"/></svg>
          <span>{html.escape(back_label)}</span>
        </button>
        <h1>{html.escape(page_title)}</h1>
        <p class="pol-dir-sub">{html.escape(page_sub)}</p>
      </div>
      <div class="dewan-tiles">
        <div class="dewan-tile"><span class="muted">{html.escape(tile_sittings)}</span><b class="mono">{model.sittings_total}</b></div>
        <div class="dewan-tile"><span class="muted">{html.escape(tile_top)}</span><b>{top_mp_name}</b><span class="muted mono">{top_turns_str}</span></div>
        <div class="dewan-tile"><span class="muted">{html.escape(tile_median)}</span><b class="mono">{model.median_turns:,}</b></div>
      </div>
      <div class="pol-dir-controls dewan-controls">
        <input id="dewan-search" class="pol-dir-search" type="search" autocomplete="off" spellcheck="false"
          placeholder="{html.escape(search_ph)}" />
        <select id="dewan-coal" class="pol-dir-select" aria-label="{html.escape(all_coal)}">
          <option value="">{html.escape(all_coal)}</option>
          {coalition_options}
        </select>
        <div class="seg chip dewan-sorts" role="group" aria-label="{html.escape(sort_aria)}">
          <button type="button" data-dewan-sort="turns" class="on">{html.escape(sort_turns)}</button>
          <button type="button" data-dewan-sort="qa" class="">{html.escape(sort_qa)}</button>
          <button type="button" data-dewan-sort="pct" class="">{html.escape(sort_pct)}</button>
          <button type="button" data-dewan-sort="recent" class="">{html.escape(sort_recent)}</button>
        </div>
      </div>
      <div id="dewan-count" class="pol-dir-count">{html.escape(count_str)}</div>
      <div class="dewan-table">
        <div class="dewan-tr dewan-th">
          <span class="dewan-rank">#</span>
          <span>{html.escape(col_mp)}</span>
          <span class="dewan-coal"></span>
          <span class="dewan-num">{html.escape(col_turns)}</span>
          <span class="dewan-num dewan-col-qa">{html.escape(col_qa)}</span>
          <span class="dewan-num">{html.escape(col_pct)}</span>
          <span class="dewan-num dewan-col-last">{html.escape(col_last)}</span>
        </div>
        <div id="dewan-rows">
{rows_html}
        </div>
      </div>
      <div class="note dewan-page-note">{html.escape(method_note)}</div>
      <p class="pol-dir-src">{html.escape(source_label)} · {html.escape(coverage_label)}</p>
    </div>
</section>"""


def render_dewan_page(
    model: DewanPageModel,
    *,
    language: Language = Language.EN,
    status: ElectionStatus | None = None,
    updated_at: date | None = None,
) -> str:
    """Render the full HTML document for the Dewan Rakyat activity page."""
    title = t(
        language,
        "Dewan Rakyat Activity — PolitikKu",
        "Aktiviti Dewan Rakyat — PolitikKu",
    )
    from_str = format_dewan_date(model.from_date, language)
    to_str = format_dewan_date(model.to_date, language)
    description = t(
        language,
        f"Who speaks in Parliament — every recorded speech turn in the official Hansard, "
        f"{from_str} – {to_str} ({model.sittings_total} sittings).",
        f"Siapa bersuara di Parlimen — setiap giliran ucapan yang direkodkan dalam Hansard rasmi, "
        f"{from_str} – {to_str} ({model.sittings_total} sidang).",
    )

    if status is None:
        from lpa.config import load_election_status
        status = load_election_status()

    if updated_at is None:
        if model.to_date:
            try:
                updated_at = date.fromisoformat(model.to_date)
            except (ValueError, TypeError):
                from lpa.pipeline import today_in_malaysia
                updated_at = today_in_malaysia()
        else:
            from lpa.pipeline import today_in_malaysia
            updated_at = today_in_malaysia()

    page_html: str = render_shell(
        title=title,
        description=description,
        active_nav="dewan",
        language=language,
        page_path=f"{PAGE_DIR}/",
        updated_at=updated_at,
        sources_count=1,
        status=status,
        body_html=render_dewan_body(model, language),
    )
    return page_html


def load_dewan_data(
    data_dir: Path | str = "frontend/public/data",
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Read Dewan page input files directly from the public data directory."""
    d = Path(data_dir)
    seats_path = d / "seats-parlimen.json"
    hansard_path = d / "hansard-dewan.json"
    politicians_path = d / "politicians.json"

    seats_data = json.loads(seats_path.read_text(encoding="utf-8"))
    hansard_data = json.loads(hansard_path.read_text(encoding="utf-8"))
    politicians_data = json.loads(politicians_path.read_text(encoding="utf-8"))

    return seats_data, hansard_data, politicians_data


def build_and_write_dewan_pages(
    output_dir: Path | str = "public",
    data_dir: Path | str = "frontend/public/data",
) -> tuple[int, int]:
    """Render and write both EN and BM versions of the Dewan activity page."""
    seats_data, hansard_data, politicians_data = load_dewan_data(data_dir)
    model = dewan_page_model(seats_data, hansard_data, politicians_data)

    out = Path(output_dir)
    en_dir = out / PAGE_DIR
    ms_dir = out / "ms" / PAGE_DIR
    en_dir.mkdir(parents=True, exist_ok=True)
    ms_dir.mkdir(parents=True, exist_ok=True)

    en_page = render_dewan_page(model, language=Language.EN)
    ms_page = render_dewan_page(model, language=Language.MS)

    en_bytes = en_page.encode("utf-8")
    ms_bytes = ms_page.encode("utf-8")

    en_file = en_dir / "index.html"
    ms_file = ms_dir / "index.html"

    en_file.write_bytes(en_bytes)
    ms_file.write_bytes(ms_bytes)

    return len(en_bytes), len(ms_bytes)


def main() -> None:
    """CLI entry point to render the Dewan Rakyat activity pages."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("public"),
        help="Root public directory to write public/dewan/index.html and public/ms/dewan/index.html",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("frontend/public/data"),
        help="Directory containing seats-parlimen.json, hansard-dewan.json, politicians.json",
    )
    args = parser.parse_args()

    en_len, ms_len = build_and_write_dewan_pages(args.output_dir, args.data_dir)
    print(f"Wrote Dewan pages: EN={en_len} bytes, MS={ms_len} bytes")


if __name__ == "__main__":
    main()
