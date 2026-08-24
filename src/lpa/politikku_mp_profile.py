"""PolitikKu MP profile page: the resolved state of the constituency lookup
(issue #79) — who represents this Seat, what they've done, how safe it is.

Full layout spec: `design_handoff_politikku/README.md`, "3. Constituency
lookup result". As with `#74`/`#75`, the mock's *structure* is given
verbatim; several of its sample *values* are not this repo's real data, and
checking each one against `data/mp_profiles.json` (Bangi/Syahredzan Johan,
the pilot's one real profile, #78/ADR 0009) found real gaps rather than
just wrong numbers — decided with the user rather than guessed:

- **"Record this term"** shows attendance and an "interventions" stat.
  Bangi's `attendance` is `None`, explained in `MPProfile.unverified`
  (Parliament's attendance page 500s). Kept, stated honestly as "not
  published". "Interventions" names no field anywhere in the domain model —
  there is no source to compute it from for *any* MP, not just Bangi's gap —
  so the card is dropped rather than invented or stubbed.
- **"Who lives here"** shows DOSM census figures per Seat. Checked
  `SeatBaseline.demographics`: its own docstring says "Read by nothing" — no
  per-Seat census data has been ingested for any Seat. The section heading
  is kept with an honest one-line note explaining the gap, rather than
  fabricated ethnicity/age/income figures or a silently dropped section.
- **Portrait**: no photo field exists anywhere in `MPProfile` (the licensing
  question is #71, still open) — every profile renders the no-photo
  fallback; there is no per-profile branch to take here yet.
- **The header's "matched location" pill** (the mock's "43650 Bandar Baru
  Bangi") is a live search result from the interactive lookup — #77's job,
  not built yet, and this page is generated statically at build time with no
  search query to echo. Swapped for the Seat's own name/code as the "you're
  in the right place" confirmation instead; #77 can still deep-link straight
  to this page once it exists, matching #79's own routing note below.

Routing: one static page per Seat, at `/politikku/mp/<code>.html` (English)
and `/politikku/ms/mp/<code>.html` (BM) — the seat code is the identifier
`#42`'s own chamber-page deep links already key on (`data-seat`/
`id="seat-<code>"`), so this reuses that identifier rather than inventing a
second scheme; nothing about #42's per-page anchors themselves is reused
verbatim since this is a separate page, not an anchor within the chamber.

Follows `public_page.py`/`politikku_homepage.py`/`politikku_landing.py`'s
seam: `mp_profile_page_model` computes every number and sentence the page
states; `render_mp_profile_page` decides nothing; `build_mp_profile_page`/
`main` is the one place that touches Storage.
"""

from __future__ import annotations

import html
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

from sqlalchemy.engine import Engine

from lpa.domain import Coalition, ElectionStatus, SeatBaseline, SeatCall
from lpa.mp_profile import ABSENT, AYE, NO, Division, MPProfile
from lpa.politikku_shell import Language, render_shell, short_date
from lpa.public_page import PageModel
from lpa.seat_call_card import card_model

DIVISIONS_SHOWN = 4
""""Voting record · last 4 divisions" — the mock's own count."""

_MODELLED_TAG = '<span class="pk-tag-modelled">NOT CALIBRATED</span>'

_VOTE_PILL_LABEL: Mapping[str, str] = {AYE: "AYE", NO: "NO", ABSENT: "ABSENT"}
"""`ABSTAIN` has no colour in the mock's own vote-pill table (only
AYE/NO/ABSENT are given) — it falls back to the ABSENT pill's neutral
styling in `_vote_pill` with its own real label, rather than a colour this
ticket would have to invent."""


@dataclass(frozen=True)
class ContactAction:
    """One of the profile's up-to-two primary contact buttons."""

    label: str
    href: str


@dataclass(frozen=True)
class DivisionRow:
    """One row of "Voting record" — this Member's own position in one
    Division, already the shape the page prints (pill label, bill/date/
    outcome), computed once here rather than in the template string."""

    subject: str
    sitting_date_text: str
    outcome: str
    vote: str
    pill_label: str
    hansard_url: str


@dataclass(frozen=True)
class SeatProjection:
    """ "This Seat in the GE16 projection" — arithmetic against the Seat's
    GE15 result, the same figures `seat_call_card.card_model` computes for
    the shareable card (#23), reused rather than re-derived. Coloured by
    Government/Non-government (the page's one certainty axis, matching the
    hemicycle) rather than by Coalition ink, since PolitikKu carries no
    party colours (README, Design Tokens)."""

    headline: str
    """"<Coalition> hold" / "<Coalition> gain" — hold when the call agrees
    with the Seat's actual GE15 winner, gain otherwise."""
    note: str
    """The plain-language margin sentence (`card_model`'s own `note`)."""
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
    attendance_note: str | None
    """Set (and `attendance_pct` `None`) when Parliament publishes no
    attendance figure — `MPProfile.unverified["attendance"]`'s own reason,
    stated to the reader rather than shown as a blank."""
    divisions: tuple[DivisionRow, ...]
    bills_sponsored: tuple[str, ...]
    bills_sponsored_note: str | None
    """Set (and `bills_sponsored` empty) when the Member has sponsored
    nothing this term — a real finding (`MPProfile.unverified
    ["bills_sponsored"]`), not a missing read."""
    contact_address: str | None
    contact_opening_hours_note: str | None
    contact_actions: tuple[ContactAction, ...]
    profile_url: str | None
    who_lives_here_note: str
    projection: SeatProjection


def mp_profile_page_model(
    page: PageModel,
    profile: MPProfile,
    baseline: SeatBaseline,
    call: SeatCall,
    names: Mapping[Coalition, str],
) -> MPProfilePageModel:
    """Build the MP profile page's model for one Seat.

    `baseline`/`call` are looked up by the caller (`build_mp_profile_page`)
    from Storage by `profile.seat_code`, the same way `landing_model` is
    handed its own `MPProfile` rather than reading Storage itself — this
    function does no I/O so what it computes can be tested without a
    database.
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
    government = profile.coalition in page.government_coalitions

    attendance_pct = None
    attendance_note = None
    if profile.attendance is None:
        attendance_note = profile.unverified.get(
            "attendance", "Not published by any source this pipeline checked."
        )
    else:
        attendance_pct = profile.attendance * 100

    bills_sponsored = tuple(profile.bills_sponsored)
    bills_sponsored_note = None
    if not bills_sponsored:
        bills_sponsored_note = profile.unverified.get(
            "bills_sponsored", "No Bill or motion sponsorship found for this Member this term."
        )

    opening_hours_note = None
    if profile.contact.opening_hours is None:
        opening_hours_note = profile.unverified.get(
            "contact.opening_hours", "Not published by Parliament for any Member."
        )

    contact_actions: list[ContactAction] = []
    if profile.contact.email:
        contact_actions.append(ContactAction("Email MP", f"mailto:{profile.contact.email}"))
    if profile.contact.phone:
        contact_actions.append(ContactAction("Call service centre", f"tel:{profile.contact.phone}"))

    return MPProfilePageModel(
        updated_at=page.computed_at,
        sources_count=len(page.sources),
        status=page.status,
        seat_code=baseline.code,
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
        attendance_note=attendance_note,
        divisions=tuple(_division_row(d) for d in profile.divisions[:DIVISIONS_SHOWN]),
        bills_sponsored=bills_sponsored,
        bills_sponsored_note=bills_sponsored_note,
        contact_address=profile.contact.address,
        contact_opening_hours_note=opening_hours_note,
        contact_actions=tuple(contact_actions),
        profile_url=profile.contact.profile_url,
        who_lives_here_note=(
            "Census profile not yet ingested for this Seat — DOSM publishes "
            "no per-Seat breakdown this pipeline currently reads."
        ),
        projection=_seat_projection(call, baseline, page, names),
    )


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
    call: SeatCall, baseline: SeatBaseline, page: PageModel, names: Mapping[Coalition, str]
) -> SeatProjection:
    model = card_model(call, baseline, names)
    holds = call.coalition == model.incumbent
    verb = "hold" if holds else "gain"
    headline = f"{names.get(call.coalition, call.coalition)} {verb}"

    # The card's own three-part track (incumbent / margin gap / opponent)
    # is right for the shareable SVG card, but the mock's per-Seat bar here
    # is a plain two-segment 100% split with no gap drawn — so the two
    # shares are renormalised over just themselves, dropping the gap.
    two_way = model.left_w + model.right_w
    left_pct = 100 * model.left_w / two_way if two_way else 0.0
    right_pct = 100 * model.right_w / two_way if two_way else 0.0
    left_coalition = model.incumbent
    right_coalition = model.opponent
    return SeatProjection(
        headline=headline,
        note=model.note,
        left_pct=left_pct,
        right_pct=right_pct,
        left_government=left_coalition in page.government_coalitions,
        right_government=right_coalition in page.government_coalitions,
        left_label=names.get(left_coalition, left_coalition),
        right_label=names.get(right_coalition, right_coalition),
    )


# ── rendering ─────────────────────────────────────────────────────────────


def _chip_row(model: MPProfilePageModel) -> str:
    chips = []
    if model.party:
        chips.append(f'<span class="pk-mp-chip">{html.escape(model.party)}</span>')
    chips.append(f'<span class="pk-mp-chip">{html.escape(model.coalition_name)}</span>')
    gov_label = "Government Coalition" if model.government else "Non-government"
    chips.append(f'<span class="pk-mp-chip pk-mp-chip-gov">{html.escape(gov_label)}</span>')
    return "".join(chips)


def _identity_band(model: MPProfilePageModel) -> str:
    return f"""
<section class="pk-mp-identity">
  <div class="pk-eyebrow">YOUR SEAT</div>
  <div class="pk-mp-identity-row">
    <div class="pk-mp-portrait" role="img" aria-label="No portrait available">{html.escape(model.mp_name[:1])}</div>
    <div class="pk-mp-identity-text">
      <div class="pk-mp-seat-code">{html.escape(model.seat_code)}</div>
      <h1>{html.escape(model.seat_name)}</h1>
      <div class="pk-mp-state">{html.escape(model.seat_state)}</div>
      <div class="pk-mp-name">{html.escape(model.mp_name)}</div>
      <div class="pk-mp-chips">{_chip_row(model)}</div>
      <div class="pk-mp-tenure">Member since {model.term_start_text}</div>
    </div>
  </div>
  {_mobile_primary_actions(model)}
  <div class="pk-mp-stat-grid">
    <div><div class="pk-mp-stat">{model.majority:,}</div><div class="pk-mp-stat-cap">GE15 majority</div></div>
    <div><div class="pk-mp-stat">{model.vote_share_pct:.2f}%</div><div class="pk-mp-stat-cap">Vote share</div></div>
    <div><div class="pk-mp-stat">{model.turnout_pct:.1f}%</div><div class="pk-mp-stat-cap">Turnout</div></div>
    <div><div class="pk-mp-stat">{model.electors:,}</div><div class="pk-mp-stat-cap">Electors</div></div>
  </div>
</section>
""".strip()


def _contact_buttons(actions: tuple[ContactAction, ...]) -> str:
    return "".join(
        f'<a class="pk-mp-contact-btn" href="{html.escape(a.href)}">{html.escape(a.label)}</a>'
        for a in actions
    )


def _mobile_primary_actions(model: MPProfilePageModel) -> str:
    """Mobile-only duplicate of the Contact card's two buttons — README's
    mobile spec puts "identity and the two primary actions... first, above
    the fold", ahead of the GE15 stat grid, while the full Contact &
    service centre card (address, hours, these same buttons) stays in its
    desktop reading position further down. `_CSS` shows exactly one of the
    two copies at a time per breakpoint, never both."""
    if not model.contact_actions:
        return ""
    return f'<div class="pk-mp-mobile-actions">{_contact_buttons(model.contact_actions)}</div>'


def _record_this_term(model: MPProfilePageModel) -> str:
    if model.attendance_pct is not None:
        card = f"""
<div class="pk-mp-card">
  <h3>Attendance</h3>
  <div class="pk-mp-progress"><div class="pk-mp-progress-fill" style="width:{model.attendance_pct:.1f}%"></div></div>
  <div class="pk-mp-source">{model.attendance_pct:.0f}% of sitting days · Dewan Rakyat Hansard</div>
</div>
""".strip()
    else:
        card = f"""
<div class="pk-mp-card">
  <h3>Attendance</h3>
  <p class="pk-mp-gap-note">Not published. {html.escape(model.attendance_note or "")}</p>
</div>
""".strip()
    return f"""
<section class="pk-mp-record pk-mp-col-left">
  <div class="pk-eyebrow">Record this term</div>
  {card}
</section>
""".strip()


def _vote_pill(vote: str, label: str) -> str:
    cls = {AYE: "pk-vote-aye", NO: "pk-vote-no"}.get(vote, "pk-vote-absent")
    return f'<span class="pk-vote-pill {cls}">{html.escape(label)}</span>'


def _voting_record(model: MPProfilePageModel) -> str:
    if not model.divisions:
        rows = '<p class="pk-mp-gap-note">No Division recorded for this Member this term.</p>'
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
    return f"""
<section class="pk-mp-voting pk-mp-col-left">
  <h3>Voting record · last {DIVISIONS_SHOWN} divisions</h3>
  <div class="pk-mp-division-list">{rows}</div>
</section>
""".strip()


def _bills_sponsored(model: MPProfilePageModel) -> str:
    if not model.bills_sponsored:
        body = f'<p class="pk-mp-gap-note">{html.escape(model.bills_sponsored_note or "")}</p>'
    else:
        body = "".join(
            f'<div class="pk-mp-bill-card">{html.escape(title)}</div>'
            for title in model.bills_sponsored
        )
    return f"""
<section class="pk-mp-bills pk-mp-col-left">
  <h3>Bills and motions sponsored</h3>
  {body}
</section>
""".strip()


def _contact_card(model: MPProfilePageModel) -> str:
    address = (
        f"<div>{html.escape(model.contact_address)}</div>"
        if model.contact_address
        else '<p class="pk-mp-gap-note">No correspondence address published.</p>'
    )
    hours = (
        f'<p class="pk-mp-gap-note">{html.escape(model.contact_opening_hours_note)}</p>'
        if model.contact_opening_hours_note
        else ""
    )
    buttons = _contact_buttons(model.contact_actions)
    profile_link = (
        f'<a class="pk-mp-parliament-link" href="{html.escape(model.profile_url)}">'
        "Parliament's own profile →</a>"
        if model.profile_url
        else ""
    )
    return f"""
<div class="pk-mp-card pk-mp-col-right pk-mp-contact">
  <h3>Contact &amp; service centre</h3>
  {address}
  {hours}
  <div class="pk-mp-contact-actions">{buttons}</div>
  {profile_link}
</div>
""".strip()


def _who_lives_here(model: MPProfilePageModel) -> str:
    return f"""
<div class="pk-mp-card pk-mp-col-right pk-mp-who-lives-here">
  <h3>Who lives here</h3>
  <p class="pk-mp-gap-note">{html.escape(model.who_lives_here_note)}</p>
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


def _seat_projection_section(model: MPProfilePageModel) -> str:
    p = model.projection
    return f"""
<div class="pk-mp-card pk-mp-col-right pk-mp-projection">
  <h3>This Seat in the GE16 projection</h3>
  <div class="pk-mp-projection-headline">{html.escape(p.headline)} {_MODELLED_TAG}</div>
  <p class="pk-mp-projection-note">{html.escape(p.note)}</p>
  {_projection_bar(p)}
</div>
""".strip()


def _source_footer() -> str:
    return (
        '<p class="pk-mp-footer-note pk-mp-col-right">Facts on this page — the MP, GE15 '
        "result, demographics — come from SPR, DOSM and parlimen.gov.my. "
        "Only the projection is modelled.</p>"
    )


def render_mp_profile_body(model: MPProfilePageModel) -> str:
    """The profile page's `body_html`, without the persistent shell.

    Every left/right-column section is a direct child of `.pk-mp-body`
    (not nested inside a left/right wrapper) so `_CSS`'s mobile media query
    can give the Seat's projection its own `order`, ahead of the sections
    that follow it in the two-column desktop reading order — README's
    mobile spec ("record; then the Seat's projection; then the source
    footer") is a strict sequence, not just the desktop column order
    collapsed. `pk-mp-col-left`/`pk-mp-col-right` place each section in its
    desktop column via `grid-column`; DOM order (unchanged from the
    desktop reading order below) governs each column's own stacking there,
    since nothing here sets `order` outside the mobile media query.
    """
    sections = (
        _record_this_term(model)
        + _voting_record(model)
        + _bills_sponsored(model)
        + _contact_card(model)
        + _who_lives_here(model)
        + _seat_projection_section(model)
        + _source_footer()
    )
    return f'<style>{_CSS}</style>{_identity_band(model)}<div class="pk-mp-body">{sections}</div>'


def render_mp_profile(model: MPProfilePageModel, *, language: Language = Language.EN) -> str:
    """The profile page as one full HTML document, shell included."""
    return render_shell(
        title=f"{model.mp_name} — {model.seat_name} | PolitikKu",
        active_nav="home",
        language=language,
        page_path=f"mp/{model.seat_code}.html",
        updated_at=model.updated_at,
        sources_count=model.sources_count,
        status=model.status,
        body_html=render_mp_profile_body(model),
    )


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

  /* Mobile-only duplicate of the Contact card's buttons (README's mobile
     spec: identity + primary actions above the fold) — hidden on desktop,
     where the Contact card's own copy (further down the page) is the only
     one shown. */
  .pk-mp-mobile-actions { display: none; }

  .pk-mp-body { display: grid; grid-template-columns: 1.5fr 1fr; }
  /* Every section is a direct grid child (see `render_mp_profile_body`'s
     docstring) rather than nested in a left/right wrapper, so the mobile
     media query below can give `.pk-mp-projection` its own `order` ahead
     of sections that sit after it in the desktop column. `grid-column`
     places each in its desktop column; each section also gets an explicit
     `grid-row` (not left to auto-placement) because the DOM groups every
     left-column section before any right-column one — row-major auto
     placement would otherwise push the whole right column down to
     wherever the left column's cursor already is, rather than starting
     both columns at row 1. The mobile query resets both to `auto` and
     lets `order` govern the single-column sequence instead. */
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
  /* Vote-pill colours — README's own "Vote pills" table gives exact hex for
     each, none of which reuse a Design Tokens value (NO's bg/border match
     no named token at all; AYE and ABSENT's border/text happen to match
     existing tokens but their backgrounds don't) — so these three are
     literal, not `var(--...)`, to stay exactly on the spec rather than the
     nearest named colour. */
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

    /* README's mobile spec is a strict sequence — "record; then the
       Seat's projection; then the source footer" — not the desktop
       column order collapsed. Only the sections whose position actually
       moves need an explicit order; the rest keep DOM order (5). */
    .pk-mp-record { order: 1; grid-row: auto; }
    .pk-mp-projection { order: 2; grid-row: auto; }
    .pk-mp-voting { order: 3; grid-row: auto; }
    .pk-mp-bills { order: 4; grid-row: auto; }
    .pk-mp-contact { order: 5; grid-row: auto; }
    .pk-mp-who-lives-here { order: 6; grid-row: auto; }
    .pk-mp-footer-note { order: 7; grid-row: auto; }
  }
"""


# ── I/O ───────────────────────────────────────────────────────────────────


def build_mp_profile_page(engine: Engine, seat_code: str) -> tuple[str, date]:
    """Read Storage and render one Seat's MP profile page. The whole I/O half."""
    from lpa.config import (
        coalition_names,
        load_coalition_config,
        load_election_status,
        load_mp_profiles,
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
    baselines = load_seat_baselines(engine)
    if not baselines:
        raise SystemExit("No Seat Baseline in Storage. Run `python -m lpa.baseline_loader` first.")

    profiles = load_mp_profiles()
    if seat_code not in profiles:
        raise SystemExit(f"No MP Profile for {seat_code!r} in data/mp_profiles.json.")
    profile = profiles[seat_code]

    baseline_by_code = {s.code: s for s in baselines}
    if seat_code not in baseline_by_code:
        raise SystemExit(f"No Seat Baseline for {seat_code!r}.")
    baseline = baseline_by_code[seat_code]

    calls_by_code = {c.code: c for c in projections[-1].seat_calls}
    if seat_code not in calls_by_code:
        raise SystemExit(f"No Seat Call for {seat_code!r} in the latest Projection.")
    call = calls_by_code[seat_code]

    config = load_coalition_config()
    names = coalition_names(config)
    snapshots = load_sentiment_snapshots(engine)
    latest_sentiment = snapshots[-1].sentiment if snapshots else None
    page = page_model(
        projection=projections[-1],
        baseline=baselines,
        status=load_election_status(),
        config=swing_model_config(config),
        names=names,
        sentiment=latest_sentiment,
        state_election_signals=load_state_election_signals(),
        total_seats=config["total_seats"],
        state_swing=load_state_swing(engine, projections[-1].computed_at),
    )
    model = mp_profile_page_model(page, profile, baseline, call, names)
    return render_mp_profile(model), model.updated_at


def build_all_mp_profile_pages(engine: Engine) -> list[tuple[str, str]]:
    """Render one page per MP Profile in `data/mp_profiles.json`, as
    `(seat_code, html)` pairs — currently just Bangi's pilot slice (#78)."""
    from lpa.config import load_mp_profiles

    return [(code, build_mp_profile_page(engine, code)[0]) for code in load_mp_profiles()]


def main() -> None:
    """Render every MP profile page from Storage and write them to disk."""
    import argparse
    from pathlib import Path

    from lpa.storage import connect

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("public/politikku/mp"),
        help="directory to write one <seat-code>.html per MP Profile",
    )
    args = parser.parse_args()

    engine = connect()
    pages = build_all_mp_profile_pages(engine)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for code, page in pages:
        target = args.output_dir / f"{code}.html"
        target.write_text(page, encoding="utf-8")
    print(f"Wrote {len(pages)} MP profile page(s) to {args.output_dir}")


if __name__ == "__main__":
    main()
