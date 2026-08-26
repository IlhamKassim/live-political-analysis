"""PolitikKu MP profile page: the resolved state of the constituency lookup
(issue #79) — who represents this Seat, what they've done, how safe it is.

Full layout spec: `design_handoff_politikku/README.md`, "3. Constituency
lookup result". As with `#74`/`#75`, the mock's *structure* is given
verbatim; several of its sample *values* are not this repo's real data, and
checking each one against `data/mp_profiles.json` (Bangi/Syahredzan Johan,
then the only real profile, #78/ADR 0009; #105 built most of the House on
the same schema) found real gaps rather than just wrong numbers — decided
with the user rather than guessed:

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
- **Portrait**: no photo field exists anywhere in `MPProfile` — #71 confirmed
  official Dewan Rakyat portraits aren't usable without written permission
  this project doesn't have, so the no-photo fallback is permanent, not a
  placeholder; every profile renders it, with no per-profile branch to take.
- **The header's "matched location" pill** (the mock's "43650 Bandar Baru
  Bangi") is a live search result from the interactive lookup — #77's job,
  not built yet, and this page is generated statically at build time with no
  search query to echo. Swapped for the Seat's own name/code as the "you're
  in the right place" confirmation instead; #77 can still deep-link straight
  to this page once it exists, matching #79's own routing note below.

Routing: one static page per Seat, at `/mp/<code>.html` (English)
and `/ms/mp/<code>.html` (BM) — `politikku_shell.MP_PROFILE_DIR` under
`POLITIKKU_PREFIX`, which #104's cutover moved to the site root — the seat
code is the identifier
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
from lpa.politikku_i18n import (
    GOVERNMENT_COALITION_EN,
    GOVERNMENT_COALITION_MS,
    MAJORITY_EN,
    MAJORITY_MS,
    NON_GOVERNMENT_EN,
    NON_GOVERNMENT_MS,
    not_calibrated_tag,
)
from lpa.politikku_shell import MP_PROFILE_DIR, Language, render_shell, short_date, t
from lpa.public_page import PageModel
from lpa.seat_call_card import card_model

DIVISIONS_SHOWN = 4
""""Voting record · last 4 divisions" — the mock's own count."""

_VOTE_PILL_LABEL: Mapping[str, str] = {AYE: "AYE", NO: "NO", ABSENT: "ABSENT"}
"""`ABSTAIN` has no colour in the mock's own vote-pill table (only
AYE/NO/ABSENT are given) — it falls back to the ABSENT pill's neutral
styling in `_vote_pill` with its own real label, rather than a colour this
ticket would have to invent."""


@dataclass(frozen=True)
class ContactAction:
    """One of the profile's up-to-two primary contact buttons."""

    label: str
    label_ms: str
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

    winner_name: str
    """The Coalition names the projection ("<Coalition> hold"/"gain")."""
    holds: bool
    """`True` when the call agrees with the Seat's actual GE15 winner
    ("hold"), `False` when it flips the Seat ("gain") — the raw fact
    `headline`'s EN/BM verb is built from at render time (#81), rather than
    baking one language's verb into this dataclass."""
    margin_points: str
    """`card_model`'s own `margin_points` (already formatted to one decimal
    place, e.g. `"6.2"`) — the figure the plain-language margin sentence
    (built at render time in #81, one sentence per language from this same
    string) states."""
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
    """Set (and `attendance_pct` `None`) when Parliament publishes no
    attendance figure — `MPProfile.unverified["attendance"]`'s own reason,
    stated to the reader rather than shown as a blank. `_en`/`_ms` are
    identical (untranslated) when the reason came from `unverified` (real,
    per-profile free text this codebase has no BM translation of); they
    differ only for this module's own fallback wording, which #81 does
    translate — see `_gap_note`."""
    divisions: tuple[DivisionRow, ...]
    bills_sponsored: tuple[str, ...]
    bills_sponsored_note_en: str | None
    bills_sponsored_note_ms: str | None
    """Set (and `bills_sponsored` empty) when the Member has sponsored
    nothing this term — a real finding (`MPProfile.unverified
    ["bills_sponsored"]`), not a missing read. Same `_en`/`_ms` split as
    `attendance_note_en`/`_ms` above."""
    contact_address: str | None
    contact_opening_hours_note_en: str | None
    contact_opening_hours_note_ms: str | None
    contact_actions: tuple[ContactAction, ...]
    profile_url: str | None
    who_lives_here_note_en: str
    who_lives_here_note_ms: str
    """This module's own authored sentence (no per-profile data behind it),
    so #81 gives it a real BM translation rather than the `_gap_note`
    untranslated-fallback split above."""
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
                "Call service centre", "Hubungi pusat khidmat", f"tel:{profile.contact.phone}"
            )
        )

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
    """An honest "why this field is empty" note, in both languages.

    When `unverified[key]` exists it is a real, per-profile reason
    (`MPProfile.unverified`'s own docstring) — left identical in both
    languages rather than guessed at, since this codebase carries no BM
    translation of arbitrary free text entered per-profile (an honest,
    named gap, listed in #81's PR description rather than silently
    papered over with an invented translation). Only this module's own
    fallback wording, used when no per-profile reason was recorded, gets a
    real `fallback_ms` translation.
    """
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
    call: SeatCall, baseline: SeatBaseline, page: PageModel, names: Mapping[Coalition, str]
) -> SeatProjection:
    model = card_model(call, baseline, names)
    holds = call.coalition == model.incumbent

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
        winner_name=names.get(call.coalition, call.coalition),
        holds=holds,
        margin_points=model.margin_points,
        left_pct=left_pct,
        right_pct=right_pct,
        left_government=left_coalition in page.government_coalitions,
        right_government=right_coalition in page.government_coalitions,
        left_label=names.get(left_coalition, left_coalition),
        right_label=names.get(right_coalition, right_coalition),
    )


# ── rendering ─────────────────────────────────────────────────────────────


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
    """Mobile-only duplicate of the Contact card's two buttons — README's
    mobile spec puts "identity and the two primary actions... first, above
    the fold", ahead of the GE15 stat grid, while the full Contact &
    service centre card (address, hours, these same buttons) stays in its
    desktop reading position further down. `_CSS` shows exactly one of the
    two copies at a time per breakpoint, never both."""
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
    return render_shell(
        title=f"{model.mp_name} — {model.seat_name} | PolitikKu",
        description=description,
        active_nav="home",
        language=language,
        page_path=f"{MP_PROFILE_DIR}/{model.seat_code}.html",
        updated_at=model.updated_at,
        sources_count=model.sources_count,
        status=model.status,
        body_html=render_mp_profile_body(model, language),
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


def build_mp_profile_page(
    engine: Engine, seat_code: str, *, language: Language = Language.EN
) -> tuple[str, date]:
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
    return render_mp_profile(model, language=language), model.updated_at


def build_all_mp_profile_pages(engine: Engine) -> list[tuple[str, Language, str]]:
    """Render one page per MP Profile in `data/mp_profiles.json`, in both
    languages, as `(seat_code, language, html)` triples.

    One Seat when #78 shipped, most of the House since #105, and doubled to
    EN + BM by #81 — so this is now several hundred pages per build rather
    than two. Driven off the file's own keys throughout: a Seat in its
    `_skipped` block gets no page, which is what `has_profile` in the lookup
    index exists to degrade to.
    """
    from lpa.config import load_mp_profiles

    return [
        (code, language, build_mp_profile_page(engine, code, language=language)[0])
        for code in load_mp_profiles()
        for language in Language
    ]


def main() -> None:
    """Render every MP profile page, in both languages, from Storage and
    write them to disk."""
    import argparse
    from pathlib import Path

    from lpa.storage import connect

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("public") / MP_PROFILE_DIR,
        help="directory to write one English <seat-code>.html per MP Profile "
        "(default: public/mp); the BM variant is "
        "written alongside it at <output-dir>/ms/<seat-code>.html, matching "
        "`politikku_shell._ms_route`'s own path convention",
    )
    args = parser.parse_args()

    engine = connect()
    pages = build_all_mp_profile_pages(engine)
    en_dir = args.output_dir
    ms_dir = args.output_dir.parent / "ms" / args.output_dir.name
    en_dir.mkdir(parents=True, exist_ok=True)
    ms_dir.mkdir(parents=True, exist_ok=True)
    for code, language, page in pages:
        target = (en_dir if language is Language.EN else ms_dir) / f"{code}.html"
        target.write_text(page, encoding="utf-8")
    print(f"Wrote {len(pages)} MP profile page(s) to {en_dir} and {ms_dir}")


if __name__ == "__main__":
    main()
