"""PolitikKu MP profile page: the resolved state of the constituency lookup
(issue #79, #143) — who represents this Seat, what they've done, how safe it is.

Static site generator recovering `mp_profile_page_model()` and rendering
per-Seat MP profile pages at directory paths:
`/mp/<code>/index.html` (English) and `/ms/mp/<code>/index.html` (Bahasa Malaysia).

Reads exclusively from static JSON files (`frontend/public/data/*.json` and `data/*.json`),
with ZERO database or Storage access.
"""

from __future__ import annotations

import argparse
import html
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from lpa.domain import Coalition, ElectionStatus, SeatBaseline, SeatCall
from lpa.mp_profile import ABSENT, AYE, NO, Division, MPProfile
from lpa.politikku_i18n import (
    GOVERNMENT_COALITION_EN,
    GOVERNMENT_COALITION_MS,
    MAJORITY_EN,
    MAJORITY_MS,
    NON_GOVERNMENT_EN,
    NON_GOVERNMENT_MS,
    not_calibrated_tag,
)
from lpa.politikku_shell import Language, render_shell, short_date, t
from lpa.seat_call_card import card_model

DIVISIONS_SHOWN = 4
""""Voting record · last 4 divisions" — the mock's own count."""

_VOTE_PILL_LABEL: Mapping[str, str] = {AYE: "AYE", NO: "NO", ABSENT: "ABSENT"}
"""`ABSTAIN` has no colour in the mock's own vote-pill table (only
AYE/NO/ABSENT are given) — it falls back to the ABSENT pill's neutral
styling in `_vote_pill` with its own real label."""


@dataclass(frozen=True)
class ContactAction:
    """One of the profile's up-to-two primary contact buttons."""

    label: str
    label_ms: str
    href: str


@dataclass(frozen=True)
class DivisionRow:
    """One row of "Voting record" — this Member's own position in one
    Division, already the shape the page prints."""

    subject: str
    sitting_date_text: str
    outcome: str
    vote: str
    pill_label: str
    hansard_url: str


@dataclass(frozen=True)
class SeatProjection:
    """This Seat in the GE16 projection — arithmetic against the Seat's GE15 result."""

    winner_name: str
    holds: bool
    margin_points: str
    left_pct: float
    right_pct: float
    left_government: bool
    right_government: bool
    left_label: str
    right_label: str


@dataclass(frozen=True)
class MPProfilePageModel:
    """Every number, sentence and honest gap the profile page states."""

    updated_at: date
    sources_count: int
    status: ElectionStatus
    seat_code: str
    seat_name: str
    seat_state: str
    mp_name: str
    coalition: Coalition
    coalition_name: str
    government: bool
    party: str | None
    term_start_text: str
    majority: int
    vote_share_pct: float
    turnout_pct: float
    electors: int
    attendance_pct: float | None
    attendance_note_en: str | None
    attendance_note_ms: str | None
    divisions: tuple[DivisionRow, ...]
    bills_sponsored: tuple[str, ...]
    bills_sponsored_note_en: str | None
    bills_sponsored_note_ms: str | None
    contact_address: str | None
    contact_opening_hours_note_en: str | None
    contact_opening_hours_note_ms: str | None
    contact_actions: tuple[ContactAction, ...]
    profile_url: str | None
    who_lives_here_note_en: str
    who_lives_here_note_ms: str
    projection: SeatProjection


def mp_profile_page_model(
    page: Any,
    profile: MPProfile,
    baseline: SeatBaseline,
    call: SeatCall,
    names: Mapping[Coalition, str],
) -> MPProfilePageModel:
    """Build the MP profile page's model for one Seat.

    Pure calculation: takes page context, profile, baseline, and call.
    Performs ZERO I/O.
    """
    if baseline.code != profile.seat_code:
        raise ValueError(
            f"Seat Baseline {baseline.code!r} does not match "
            f"MP Profile {profile.seat_code!r} — mismatched arguments."
        )
    if call.code != profile.seat_code:
        raise ValueError(
            f"Seat Call {call.code!r} does not match "
            f"MP Profile {profile.seat_code!r} — mismatched arguments."
        )

    coalition_name = names.get(profile.coalition, profile.coalition)
    gov_coalitions: frozenset[Coalition] | Sequence[Coalition] = getattr(
        page, "government_coalitions", frozenset()
    )
    government = profile.coalition in gov_coalitions

    attendance_pct = None
    attendance_note_en = attendance_note_ms = None
    if profile.attendance is None:
        attendance_note_en, attendance_note_ms = _gap_note(
            profile.unverified,
            "attendance",
            "Not published by any source this pipeline checked.",
            "Tidak diterbitkan oleh mana-mana sumber yang disemak oleh saluran paip ini.",
        )
    else:
        attendance_pct = profile.attendance * 100

    bills_sponsored = tuple(profile.bills_sponsored)
    bills_sponsored_note_en = bills_sponsored_note_ms = None
    if not bills_sponsored:
        bills_sponsored_note_en, bills_sponsored_note_ms = _gap_note(
            profile.unverified,
            "bills_sponsored",
            "No Bill or motion sponsorship found for this Member this term.",
            "Tiada penajaan rang undang-undang atau usul dijumpai bagi Ahli ini pada penggal ini.",
        )

    opening_hours_note_en = opening_hours_note_ms = None
    if profile.contact.opening_hours is None:
        opening_hours_note_en, opening_hours_note_ms = _gap_note(
            profile.unverified,
            "contact.opening_hours",
            "Not published by Parliament for any Member.",
            "Tidak diterbitkan oleh Parlimen bagi mana-mana Ahli.",
        )

    contact_actions: list[ContactAction] = []
    if profile.contact.email:
        contact_actions.append(
            ContactAction("Email MP", "E-mel Ahli Parlimen", f"mailto:{profile.contact.email}")
        )
    if profile.contact.phone:
        contact_actions.append(
            ContactAction(
                f"Call ({profile.contact.phone})",
                f"Hubungi ({profile.contact.phone})",
                f"tel:{profile.contact.phone}",
            )
        )

    page_updated_at = getattr(page, "updated_at", datetime.now(UTC).date())
    page_sources_count = getattr(page, "sources_count", 1)
    page_status = getattr(
        page,
        "status",
        ElectionStatus(constitutional_deadline=date(2028, 2, 17), source="default"),
    )

    return MPProfilePageModel(
        updated_at=page_updated_at,
        sources_count=page_sources_count,
        status=page_status,
        seat_code=profile.seat_code,
        seat_name=baseline.name,
        seat_state=baseline.state,
        mp_name=profile.name,
        coalition=profile.coalition,
        coalition_name=coalition_name,
        government=government,
        party=profile.party,
        term_start_text=short_date(profile.term_start),
        majority=profile.ge15.majority,
        vote_share_pct=profile.ge15.vote_share * 100,
        turnout_pct=profile.ge15.turnout * 100,
        electors=profile.ge15.electors,
        attendance_pct=attendance_pct,
        attendance_note_en=attendance_note_en,
        attendance_note_ms=attendance_note_ms,
        divisions=tuple(_division_row(d) for d in profile.divisions[:DIVISIONS_SHOWN]),
        bills_sponsored=bills_sponsored,
        bills_sponsored_note_en=bills_sponsored_note_en,
        bills_sponsored_note_ms=bills_sponsored_note_ms,
        contact_address=profile.contact.address,
        contact_opening_hours_note_en=opening_hours_note_en,
        contact_opening_hours_note_ms=opening_hours_note_ms,
        contact_actions=tuple(contact_actions),
        profile_url=profile.contact.profile_url,
        who_lives_here_note_en=(
            "Census profile not yet ingested for this Seat — DOSM publishes "
            "no per-Seat breakdown this pipeline currently reads."
        ),
        who_lives_here_note_ms=(
            "Profil banci belum dimasukkan bagi kerusi ini — DOSM tidak menerbitkan "
            "pecahan mengikut kerusi yang dibaca oleh saluran paip ini buat masa ini."
        ),
        projection=_seat_projection(call, baseline, page, names),
    )


def _gap_note(
    unverified: Mapping[str, str], key: str, fallback_en: str, fallback_ms: str
) -> tuple[str, str]:
    """An honest 'why this field is empty' note, in both languages."""
    if key in unverified:
        reason = unverified[key]
        return reason, reason
    return fallback_en, fallback_ms


def _division_row(d: Division) -> DivisionRow:
    return DivisionRow(
        subject=d.subject,
        sitting_date_text=short_date(d.sitting_date),
        outcome=d.outcome,
        vote=d.vote,
        pill_label=_VOTE_PILL_LABEL.get(d.vote, d.vote.upper()),
        hansard_url=d.hansard_url,
    )


def _seat_projection(
    call: SeatCall,
    baseline: SeatBaseline,
    page: Any,
    names: Mapping[Coalition, str],
) -> SeatProjection:
    model = card_model(call, baseline, names)
    holds = call.coalition == model.incumbent

    two_way = model.left_w + model.right_w
    left_pct = 100 * model.left_w / two_way if two_way else 0.0
    right_pct = 100 * model.right_w / two_way if two_way else 0.0
    left_coalition = model.incumbent
    right_coalition = model.opponent
    gov_coalitions: frozenset[Coalition] | Sequence[Coalition] = getattr(
        page, "government_coalitions", frozenset()
    )
    return SeatProjection(
        winner_name=names.get(call.coalition, call.coalition),
        holds=holds,
        margin_points=model.margin_points,
        left_pct=left_pct,
        right_pct=right_pct,
        left_government=left_coalition in gov_coalitions,
        right_government=right_coalition in gov_coalitions,
        left_label=names.get(left_coalition, left_coalition),
        right_label=names.get(right_coalition, right_coalition),
    )


# ── Rendering ─────────────────────────────────────────────────────────────


def _chip_row(model: MPProfilePageModel, language: Language) -> str:
    chips = []
    if model.party:
        chips.append(f'<span class="pk-mp-chip">{html.escape(model.party)}</span>')
    chips.append(f'<span class="pk-mp-chip">{html.escape(model.coalition_name)}</span>')
    gov_label = (
        t(language, GOVERNMENT_COALITION_EN, GOVERNMENT_COALITION_MS)
        if model.government
        else t(language, NON_GOVERNMENT_EN, NON_GOVERNMENT_MS)
    )
    chips.append(f'<span class="pk-mp-chip pk-mp-chip-gov">{html.escape(gov_label)}</span>')
    return "".join(chips)


def _identity_band(model: MPProfilePageModel, language: Language) -> str:
    eyebrow = t(language, "YOUR SEAT", "KERUSI ANDA")
    no_portrait = t(language, "No portrait available", "Tiada potret tersedia")
    member_since = t(language, "Member since", "Ahli sejak")
    ge15_majority = t(language, f"GE15 {MAJORITY_EN.lower()}", f"{MAJORITY_MS} PRU15")
    vote_share = t(language, "Vote share", "Peratusan undi")
    turnout = t(language, "Turnout", "Peratusan keluar mengundi")
    electors = t(language, "Electors", "Pemilih berdaftar")
    return f"""
<section class="pk-mp-identity">
  <div class="pk-eyebrow">{eyebrow}</div>
  <div class="pk-mp-identity-row">
    <div class="pk-mp-portrait" role="img" aria-label="{no_portrait}">{html.escape(model.mp_name[:1])}</div>
    <div class="pk-mp-identity-text">
      <div class="pk-mp-seat-code">{html.escape(model.seat_code)}</div>
      <h1>{html.escape(model.seat_name)}</h1>
      <div class="pk-mp-state">{html.escape(model.seat_state)}</div>
      <div class="pk-mp-name">{html.escape(model.mp_name)}</div>
      <div class="pk-mp-chips">{_chip_row(model, language)}</div>
      <div class="pk-mp-tenure">{member_since} {model.term_start_text}</div>
    </div>
  </div>
  {_mobile_primary_actions(model, language)}
  <div class="pk-mp-stat-grid">
    <div><div class="pk-mp-stat">{model.majority:,}</div><div class="pk-mp-stat-cap">{ge15_majority}</div></div>
    <div><div class="pk-mp-stat">{model.vote_share_pct:.2f}%</div><div class="pk-mp-stat-cap">{vote_share}</div></div>
    <div><div class="pk-mp-stat">{model.turnout_pct:.1f}%</div><div class="pk-mp-stat-cap">{turnout}</div></div>
    <div><div class="pk-mp-stat">{model.electors:,}</div><div class="pk-mp-stat-cap">{electors}</div></div>
  </div>
</section>
""".strip()


def _contact_buttons(actions: tuple[ContactAction, ...], language: Language) -> str:
    return "".join(
        f'<a class="pk-mp-contact-btn" href="{html.escape(a.href)}">'
        f"{html.escape(t(language, a.label, a.label_ms))}</a>"
        for a in actions
    )


def _mobile_primary_actions(model: MPProfilePageModel, language: Language) -> str:
    if not model.contact_actions:
        return ""
    buttons = _contact_buttons(model.contact_actions, language)
    return f'<div class="pk-mp-mobile-actions">{buttons}</div>'


def _record_this_term(model: MPProfilePageModel, language: Language) -> str:
    heading = t(language, "Attendance", "Kehadiran")
    if model.attendance_pct is not None:
        source = t(
            language,
            f"{model.attendance_pct:.0f}% of sitting days · Dewan Rakyat Hansard",
            f"{model.attendance_pct:.0f}% daripada hari persidangan · Hansard Dewan Rakyat",
        )
        card = f"""
<div class="pk-mp-card">
  <h3>{heading}</h3>
  <div class="pk-mp-progress"><div class="pk-mp-progress-fill" style="width:{model.attendance_pct:.1f}%"></div></div>
  <div class="pk-mp-source">{source}</div>
</div>
""".strip()
    else:
        not_published = t(language, "Not published.", "Tidak diterbitkan.")
        note = html.escape(
            t(language, model.attendance_note_en or "", model.attendance_note_ms or "")
        )
        card = f"""
<div class="pk-mp-card">
  <h3>{heading}</h3>
  <p class="pk-mp-gap-note">{not_published} {note}</p>
</div>
""".strip()
    eyebrow = t(language, "Record this term", "Rekod penggal ini")
    return f"""
<section class="pk-mp-record pk-mp-col-left">
  <div class="pk-eyebrow">{eyebrow}</div>
  {card}
</section>
""".strip()


def _vote_pill(vote: str, label: str) -> str:
    cls = {AYE: "pk-vote-aye", NO: "pk-vote-no"}.get(vote, "pk-vote-absent")
    return f'<span class="pk-vote-pill {cls}">{html.escape(label)}</span>'


def _voting_record(model: MPProfilePageModel, language: Language) -> str:
    if not model.divisions:
        no_division = t(
            language,
            "No Division recorded for this Member this term.",
            "Tiada undian direkodkan bagi Ahli ini pada penggal ini.",
        )
        rows = f'<p class="pk-mp-gap-note">{no_division}</p>'
    else:
        rows = "".join(
            f"""
<div class="pk-mp-division-row">
  <div><a href="{html.escape(d.hansard_url)}">{html.escape(d.subject)}</a>
    <div class="pk-mp-division-meta">{html.escape(d.sitting_date_text)} · {html.escape(d.outcome)}</div></div>
  {_vote_pill(d.vote, d.pill_label)}
</div>
""".strip()
            for d in model.divisions
        )
    heading = t(
        language,
        f"Voting record · last {DIVISIONS_SHOWN} divisions",
        f"Rekod pengundian · {DIVISIONS_SHOWN} undian terakhir",
    )
    return f"""
<section class="pk-mp-voting pk-mp-col-left">
  <h3>{heading}</h3>
  <div class="pk-mp-division-list">{rows}</div>
</section>
""".strip()


def _bills_sponsored(model: MPProfilePageModel, language: Language) -> str:
    if not model.bills_sponsored:
        note = html.escape(
            t(language, model.bills_sponsored_note_en or "", model.bills_sponsored_note_ms or "")
        )
        body = f'<p class="pk-mp-gap-note">{note}</p>'
    else:
        body = "".join(
            f'<div class="pk-mp-bill-card">{html.escape(title)}</div>'
            for title in model.bills_sponsored
        )
    heading = t(
        language, "Bills and motions sponsored", "Rang undang-undang dan usul yang dicadangkan"
    )
    return f"""
<section class="pk-mp-bills pk-mp-col-left">
  <h3>{heading}</h3>
  {body}
</section>
""".strip()


def _contact_card(model: MPProfilePageModel, language: Language) -> str:
    no_address = t(
        language, "No correspondence address published.", "Tiada alamat surat-menyurat diterbitkan."
    )
    address = (
        f"<div>{html.escape(model.contact_address)}</div>"
        if model.contact_address
        else f'<p class="pk-mp-gap-note">{no_address}</p>'
    )
    hours = ""
    if model.contact_opening_hours_note_en is not None:
        note = t(
            language,
            model.contact_opening_hours_note_en,
            model.contact_opening_hours_note_ms or "",
        )
        hours = f'<p class="pk-mp-gap-note">{html.escape(note)}</p>'
    buttons = _contact_buttons(model.contact_actions, language)
    parliament_profile = t(language, "Parliament's own profile →", "Profil rasmi Parlimen →")
    profile_link = (
        f'<a class="pk-mp-parliament-link" href="{html.escape(model.profile_url)}">'
        f"{parliament_profile}</a>"
        if model.profile_url
        else ""
    )
    heading = t(language, "Contact &amp; service centre", "Hubungi &amp; pusat khidmat")
    return f"""
<div class="pk-mp-card pk-mp-col-right pk-mp-contact">
  <h3>{heading}</h3>
  {address}
  {hours}
  <div class="pk-mp-contact-actions">{buttons}</div>
  {profile_link}
</div>
""".strip()


def _who_lives_here(model: MPProfilePageModel, language: Language) -> str:
    heading = t(language, "Who lives here", "Siapa yang tinggal di sini")
    note = html.escape(t(language, model.who_lives_here_note_en, model.who_lives_here_note_ms))
    return f"""
<div class="pk-mp-card pk-mp-col-right pk-mp-who-lives-here">
  <h3>{heading}</h3>
  <p class="pk-mp-gap-note">{note}</p>
</div>
""".strip()


def _projection_bar(p: SeatProjection) -> str:
    left_cls = "pk-mp-bar-gov" if p.left_government else "pk-mp-bar-nongov"
    right_cls = "pk-mp-bar-gov" if p.right_government else "pk-mp-bar-nongov"
    return f"""
<div class="pk-mp-projection-bar">
  <div class="{left_cls}" style="width:{p.left_pct:.2f}%"></div>
  <div class="{right_cls}" style="width:{p.right_pct:.2f}%"></div>
</div>
<div class="pk-mp-projection-labels">
  <span>{html.escape(p.left_label)} {p.left_pct:.0f}%</span>
  <span>{html.escape(p.right_label)} {p.right_pct:.0f}%</span>
</div>
""".strip()


def _seat_projection_section(model: MPProfilePageModel, language: Language) -> str:
    p = model.projection
    heading = t(language, "This Seat in the GE16 projection", "Kerusi ini dalam unjuran PRU16")
    verb = t(language, "hold" if p.holds else "gain", "kekal" if p.holds else "rampas")
    headline = html.escape(f"{p.winner_name} {verb}")
    note = t(
        language,
        f"The projection puts {model.seat_name} with {p.winner_name}, ahead by {p.margin_points} points.",
        f"Unjuran meletakkan {model.seat_name} bersama {p.winner_name}, mendahului dengan "
        f"{p.margin_points} mata.",
    )
    return f"""
<div class="pk-mp-card pk-mp-col-right pk-mp-projection">
  <h3>{heading}</h3>
  <div class="pk-mp-projection-headline">{headline} {not_calibrated_tag(language)}</div>
  <p class="pk-mp-projection-note">{html.escape(note)}</p>
  {_projection_bar(p)}
</div>
""".strip()


def _source_footer(language: Language) -> str:
    text = t(
        language,
        "Facts on this page — the MP, GE15 result, demographics — come from SPR, DOSM and "
        "parlimen.gov.my. Only the projection is modelled.",
        "Fakta pada halaman ini — Ahli Parlimen, keputusan PRU15, demografi — datang daripada "
        "SPR, DOSM dan parlimen.gov.my. Hanya unjuran adalah berdasarkan model.",
    )
    return f'<p class="pk-mp-footer-note pk-mp-col-right">{text}</p>'


def render_mp_profile_body(model: MPProfilePageModel, language: Language = Language.EN) -> str:
    """The profile page's body_html without the persistent shell."""
    sections = (
        _record_this_term(model, language)
        + _voting_record(model, language)
        + _bills_sponsored(model, language)
        + _contact_card(model, language)
        + _who_lives_here(model, language)
        + _seat_projection_section(model, language)
        + _source_footer(language)
    )
    identity = _identity_band(model, language)
    return f'<style>{_CSS}</style>{identity}<div class="pk-mp-body">{sections}</div>'


def render_mp_profile(model: MPProfilePageModel, *, language: Language = Language.EN) -> str:
    """The profile page as one full HTML document, shell included."""
    description = t(
        language,
        f"{model.mp_name}, {model.coalition_name} — the Member of Parliament for "
        f"{model.seat_name}, {model.seat_state}. Voting record, attendance, and contact "
        "details.",
        f"{model.mp_name}, {model.coalition_name} — Ahli Parlimen bagi {model.seat_name}, "
        f"{model.seat_state}. Rekod undi, kehadiran, dan butiran hubungan.",
    )

    person_ld = json.dumps(
        {
            "@context": "https://schema.org",
            "@type": "Person",
            "name": model.mp_name,
            "jobTitle": "Member of Parliament",
            "worksFor": {"@type": "Organization", "name": "Dewan Rakyat"},
            "description": f"MP for {model.seat_name} ({model.seat_code})",
        }
    )
    ld_script = f'<script type="application/ld+json">\n{person_ld}\n</script>'

    page_html: str = render_shell(
        title=f"{model.mp_name} — {model.seat_name} | PolitikKu",
        description=description,
        active_nav="politicians",
        language=language,
        page_path=f"mp/{model.seat_code}/",
        updated_at=model.updated_at,
        sources_count=model.sources_count,
        status=model.status,
        body_html=render_mp_profile_body(model, language) + ld_script,
    )
    return page_html


_CSS = """
  .pk-mp-identity { background: var(--paper-alt); padding: 30px 30px 26px; }
  .pk-mp-identity-row { display: flex; gap: 20px; align-items: flex-start; }
  .pk-mp-portrait {
    width: 112px; height: 140px; flex-shrink: 0; background: #e0dbd0; border: 1px solid #cfc9bc;
    border-radius: var(--radius-lg); display: flex; align-items: center; justify-content: center;
    font-family: var(--serif); font-size: 40px; color: var(--muted);
  }
  .pk-mp-seat-code { font-family: var(--mono); font-size: 13px; color: var(--muted); }
  .pk-mp-identity-text h1 {
    font-family: var(--serif); font-weight: 500; font-size: 40px; line-height: 1.1;
    color: var(--ink); margin: 2px 0 0;
  }
  .pk-mp-state { font-size: 13px; color: var(--ink-secondary); margin-top: 2px; }
  .pk-mp-name { font-size: 20px; font-weight: 500; color: var(--ink); margin-top: 10px; }
  .pk-mp-chips { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; }
  .pk-mp-chip {
    font-family: var(--mono); font-size: 10.5px; letter-spacing: .05em; text-transform: uppercase;
    padding: 4px 9px; border-radius: var(--radius-sm); border: 1px solid var(--line-strong);
    color: var(--ink-secondary); background: var(--white);
  }
  .pk-mp-chip-gov { background: var(--ink); color: var(--paper); border-color: var(--ink); }
  .pk-mp-tenure { font-size: 12.5px; color: var(--muted); margin-top: 8px; }
  .pk-mp-stat-grid {
    display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-top: 24px;
    padding-top: 16px; border-top: 1px solid var(--line);
  }
  .pk-mp-stat { font-family: var(--serif); font-size: 26px; color: var(--ink); }
  .pk-mp-stat-cap { font-size: 11.5px; color: var(--muted); margin-top: 2px; }

  .pk-mp-mobile-actions { display: none; }

  .pk-mp-body { display: grid; grid-template-columns: 1.5fr 1fr; }
  .pk-mp-col-left { grid-column: 1; background: var(--paper); padding: 20px 30px; margin: 0; }
  .pk-mp-col-right { grid-column: 2; background: var(--paper-alt); padding: 20px 30px; margin: 0; }
  .pk-mp-record { grid-row: 1; }
  .pk-mp-voting { grid-row: 2; }
  .pk-mp-bills { grid-row: 3; }
  .pk-mp-contact { grid-row: 1; }
  .pk-mp-who-lives-here { grid-row: 2; }
  .pk-mp-projection { grid-row: 3; }
  .pk-mp-footer-note { grid-row: 4; }
  .pk-mp-record h3, .pk-mp-voting h3, .pk-mp-bills h3, .pk-mp-card h3 {
    font-family: var(--serif); font-weight: 500; font-size: 19px; color: var(--ink); margin: 0 0 12px;
  }
  .pk-mp-card {
    background: var(--white); border: 1px solid var(--line); border-radius: var(--radius-lg);
    padding: 18px 20px;
  }
  .pk-mp-progress { height: 6px; background: var(--line-soft); border-radius: 3px; overflow: hidden; }
  .pk-mp-progress-fill { height: 100%; background: var(--ink); }
  .pk-mp-source { font-family: var(--mono); font-size: 10.5px; color: var(--muted); margin-top: 8px; }
  .pk-mp-gap-note { font-size: 13px; color: var(--ink-secondary); margin: 0; }

  .pk-mp-division-list { border: 1px solid var(--line); border-radius: var(--radius-lg); overflow: hidden; }
  .pk-mp-division-row {
    display: flex; justify-content: space-between; align-items: center; gap: 12px;
    padding: 12px 16px; font-size: 13.5px; border-bottom: 1px solid var(--line-soft);
  }
  .pk-mp-division-row:last-child { border-bottom: none; }
  .pk-mp-division-meta { font-family: var(--mono); font-size: 11px; color: var(--muted); margin-top: 2px; }
  .pk-vote-pill {
    font-family: var(--mono); font-size: 10px; letter-spacing: .06em; text-transform: uppercase;
    padding: 3px 8px; border-radius: var(--radius-sm); white-space: nowrap;
  }
  .pk-vote-aye { background: #eef3f0; border: 1px solid #cfe0da; color: #1f5c58; }
  .pk-vote-no { background: #f6f0e4; border: 1px solid #e6dcc4; color: #8a6a2f; }
  .pk-vote-absent { background: #f1efea; border: 1px solid #dcd8cf; color: #8a9099; }

  .pk-mp-bill-card {
    background: var(--white); border: 1px solid var(--line); border-radius: var(--radius-lg);
    padding: 14px 18px; font-size: 13.5px; margin-bottom: 10px;
  }

  .pk-mp-contact-actions { display: flex; gap: 10px; margin-top: 14px; flex-wrap: wrap; }
  .pk-mp-contact-btn {
    height: 42px; padding: 0 18px; display: inline-flex; align-items: center;
    border-radius: var(--radius-md); background: var(--ink); color: var(--paper); font-size: 13.5px;
  }
  .pk-mp-parliament-link { display: inline-block; margin-top: 12px; font-size: 12.5px; }

  .pk-mp-projection-headline {
    font-family: var(--serif); font-size: 24px; color: var(--ink); display: flex;
    align-items: center; gap: 8px; flex-wrap: wrap;
  }
  .pk-mp-projection-note { font-size: 13px; color: var(--ink-secondary); margin: 8px 0 14px; }
  .pk-mp-projection-bar {
    height: 6px; border-radius: 3px; overflow: hidden; display: flex; background: var(--line-soft);
  }
  .pk-mp-bar-gov { background: var(--data-government); }
  .pk-mp-bar-nongov { background: var(--data-nongovernment); }
  .pk-mp-projection-labels {
    display: flex; justify-content: space-between; font-family: var(--mono); font-size: 10.5px;
    color: var(--muted); margin-top: 6px;
  }

  .pk-mp-footer-note { font-size: 11.5px; color: var(--muted); margin: 0; }

  @media (max-width: 900px) {
    .pk-mp-identity { padding: 22px var(--gutter-mobile); }
    .pk-mp-identity-row { align-items: center; }
    .pk-mp-portrait { width: 84px; height: 104px; font-size: 30px; }
    .pk-mp-identity-text h1 { font-size: 30px; }
    .pk-mp-stat-grid { grid-template-columns: repeat(2, 1fr); }
    .pk-mp-body { grid-template-columns: 1fr; }
    .pk-mp-col-left, .pk-mp-col-right { grid-column: 1; padding: 18px var(--gutter-mobile); }
    .pk-mp-mobile-actions { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 14px; }
    .pk-mp-card .pk-mp-contact-actions { display: none; }

    .pk-mp-record { order: 1; grid-row: auto; }
    .pk-mp-projection { order: 2; grid-row: auto; }
    .pk-mp-voting { order: 3; grid-row: auto; }
    .pk-mp-bills { order: 4; grid-row: auto; }
    .pk-mp-contact { order: 5; grid-row: auto; }
    .pk-mp-who-lives-here { order: 6; grid-row: auto; }
    .pk-mp-footer-note { order: 7; grid-row: auto; }
  }
"""


# ── Static Data Loading (Zero Storage/DB Access) ──────────────────────────


@dataclass(frozen=True)
class _MPProfileContext:
    updated_at: date
    sources_count: int
    status: ElectionStatus
    government_coalitions: frozenset[Coalition]


def load_all_mp_profile_data(
    base_data_path: Path = Path("frontend/public/data"),
) -> tuple[
    _MPProfileContext,
    Mapping[str, MPProfile],
    Mapping[str, SeatBaseline],
    Mapping[str, SeatCall],
    Mapping[Coalition, str],
]:
    """Load JSON files to build MP profiles, baselines, and calls without Storage."""
    from lpa.config import (
        coalition_names,
        load_coalition_config,
        load_election_status,
        load_mp_profiles,
    )

    profiles = load_mp_profiles()

    def _read_json(name: str) -> Any:
        p = base_data_path / name
        if not p.exists():
            fallback = Path("data") / name
            if fallback.exists():
                return json.loads(fallback.read_text(encoding="utf-8"))
            return {}
        return json.loads(p.read_text(encoding="utf-8"))

    projection_data = _read_json("projection.json")
    candidates_data = _read_json("candidates-ge15.json")
    seats_parlimen = _read_json("seats-parlimen.json").get("seats", [])
    seat_meta = {s["code"]: (s["name"], s["state"]) for s in seats_parlimen}

    config = load_coalition_config()
    names = coalition_names(config)
    gov_coalitions = frozenset(config.get("government_coalitions", ()))
    status = load_election_status()

    computed_str = projection_data.get("computed_at")
    computed_at = date.fromisoformat(computed_str) if computed_str else datetime.now(UTC).date()

    context = _MPProfileContext(
        updated_at=computed_at,
        sources_count=len(projection_data.get("seats", [])),
        status=status,
        government_coalitions=gov_coalitions,
    )

    # Build SeatBaselines
    baselines: dict[str, SeatBaseline] = {}
    for code, data in candidates_data.items():
        name, state = seat_meta.get(code, (code, ""))
        cands = data.get("candidates", [])
        total_votes = sum(c.get("votes", 0) for c in cands)
        vote_shares: dict[Coalition, float] = {}
        for c in cands:
            coal = c.get("coalition", "")
            if coal:
                vote_shares[coal] = vote_shares.get(coal, 0.0) + (
                    c.get("votes", 0) / total_votes if total_votes > 0 else 0.0
                )
        sorted_shares = sorted(vote_shares.values(), reverse=True)
        margin = (
            (sorted_shares[0] - sorted_shares[1])
            if len(sorted_shares) > 1
            else (sorted_shares[0] if sorted_shares else 0.0)
        )
        baselines[code] = SeatBaseline(
            code=code,
            name=name,
            state=state,
            vote_share=vote_shares,
            margin=margin,
        )

    # Build SeatCalls from projection.json
    calls: dict[str, SeatCall] = {}
    for s in projection_data.get("seats", []):
        code = s["code"]
        calls[code] = SeatCall(
            code=code,
            coalition=s.get("coalition", ""),
            margin=float(s.get("margin", 0.0)),
        )

    return context, profiles, baselines, calls, names


def build_all_mp_profile_pages(
    base_data_path: Path = Path("frontend/public/data"),
) -> list[tuple[str, Language, str]]:
    """Render one page per MP Profile in both languages."""
    context, profiles, baselines, calls, names = load_all_mp_profile_data(base_data_path)

    pages: list[tuple[str, Language, str]] = []
    for code, profile in profiles.items():
        if code not in baselines or code not in calls:
            continue
        baseline = baselines[code]
        call = calls[code]
        model = mp_profile_page_model(context, profile, baseline, call, names)

        for language in Language:
            pages.append((code, language, render_mp_profile(model, language=language)))

    return pages


def build_and_write_mp_profile_pages(
    output_dir: Path = Path("public"),
    base_data_path: Path = Path("frontend/public/data"),
) -> int:
    """Render and write `/mp/<code>/index.html` and `/ms/mp/<code>/index.html` files."""
    pages = build_all_mp_profile_pages(base_data_path)

    for code, language, page_content in pages:
        if language is Language.EN:
            target_dir = output_dir / "mp" / code
        else:
            target_dir = output_dir / "ms" / "mp" / code
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file = target_dir / "index.html"
        target_file.write_text(page_content, encoding="utf-8")

    return len(pages)


def main() -> None:
    """CLI entry point for rendering all MP profile pages."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("public"),
        help="Root public directory (default: public/)",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("frontend/public/data"),
        help="Static data directory (default: frontend/public/data)",
    )
    args = parser.parse_args()

    count = build_and_write_mp_profile_pages(
        output_dir=args.output_dir,
        base_data_path=args.data_dir,
    )
    print(f"Wrote {count} MP profile pages to {args.output_dir}/mp/ and {args.output_dir}/ms/mp/")


if __name__ == "__main__":
    main()
