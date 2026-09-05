"""The PolitikKu Politicians Directory page (#143).

Renders `/politicians/` (English) and `/ms/politicians/` (Bahasa Malaysia), tracking
all 222 parliamentary seats (MPs) and 600 state assembly seats (ADUNs) across
Malaysia, along with party and coalition aggregates.

Follows the `page_model()` / `render_*_body()` / `render_*_page()` shape:
- `politicians_page_model()` replicates `polList()`, `dualSeatMap()`, and `partyStatsList()`
  joins purely over flat JSON files with ZERO Storage/database access.
- `render_politicians_body()` emits markup matching `app.js`'s `#politicians-view`
  DOM contract (`.pol-dir`, `.pol-card`, `.pol-party-card`, `#pol-grid`, `#pol-search`, etc.).
- `render_politicians_page()` wraps in `render_shell()` with per-route meta/OG tags.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from lpa.domain import ElectionStatus
from lpa.politikku_shell import (
    Language,
    render_shell,
    t,
)

PAGE_PATH = "politicians/"

COALITION_ORDER: tuple[str, ...] = (
    "PH",
    "PN",
    "BN",
    "GPS",
    "GRS",
    "WARISAN",
    "KDM",
    "PBM",
    "STAR",
    "UPKO",
    "PSB",
    "BEBAS",
)

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

DUAL_CROSS_STATE: dict[str, str] = {
    "6_N.04": "P.024",  # Tuan Ibrahim Tuan Man: Kelantan MP + Pahang ADUN
}

_NAME_PARTICLES_RE = re.compile(
    r"\b(bin|binti|binte|bt|a/l|a/p|al|ap|anak|@|dato|datuk|seri|haji|hj|ir|dr|tan|sri|yb|yab)\b",
    re.IGNORECASE,
)
_ALPHANUM_RE = re.compile(r"[^a-z0-9]")
_MOHD_PREFIX_RE = re.compile(r"^(mohd|muhammad|mohammad|muhamad|md)+")
_WORD_3_PLUS_RE = re.compile(r"[a-z]{3,}")
_PARTICLES = {"bin", "binti", "binte", "bt", "al", "ap", "a/l", "a/p", "anak"}
_WORD_RE = re.compile(r"[^\s/]+")


@dataclass(frozen=True)
class AlsoDun:
    """State seat representation for dual-mandate MPs."""

    code: str
    dun_code: str
    seat_name: str


@dataclass(frozen=True)
class PoliticianCardModel:
    """A sitting representative (MP, ADUN, or dual-mandate holder)."""

    code: str
    name: str
    party: str
    coalition: str
    seat_name: str
    state: str
    dun_code: str | None = None
    ge15_coalition: str = ""
    divisions_count: int = 0
    bills_count: int = 0
    has_legislative: bool = False
    photo: str | None = None
    socials: Mapping[str, Any] | None = None
    socials_source: str | None = None
    vacated: bool = False
    also_dun: AlsoDun | None = None
    former: bool = False


@dataclass(frozen=True)
class RepresentativeSample:
    """Sample representative shown in a party rollup card."""

    name: str
    state: str
    seat: str
    tier: str


@dataclass(frozen=True)
class PartyStatsModel:
    """Rollup counts and top states for one political party or bloc."""

    party: str
    coalition: str
    total: int
    parliament: int
    dun: int
    top_states: tuple[tuple[str, int], ...]
    samples: tuple[RepresentativeSample, ...]


@dataclass(frozen=True)
class PoliticiansPageModel:
    """Full data model backing `/politicians/` and `/ms/politicians/`."""

    updated_at: date
    sources_count: int
    status: ElectionStatus
    all_politicians: tuple[PoliticianCardModel, ...]
    mps: tuple[PoliticianCardModel, ...]
    aduns: tuple[PoliticianCardModel, ...]
    parties: tuple[PartyStatsModel, ...]
    states: tuple[str, ...]
    coalitions: tuple[str, ...]


# ── String and Name Normalization ──────────────────────────────────────────


def norm_party_label(s: str | None) -> str:
    """Uppercase and strip party label for robust grouping."""
    return (s or "").strip().upper()


def namekey_loose(s: str | None) -> str:
    """Loose person-name key (drops bin/binti/a-l/a-p/titles)."""
    if not s:
        return ""
    cleaned = _NAME_PARTICLES_RE.sub(" ", s.lower())
    return _ALPHANUM_RE.sub("", cleaned)


def person_name_tokens(s: str | None) -> list[str]:
    """Extract significant name tokens (3+ chars, honorifics dropped)."""
    if not s:
        return []
    cleaned = _NAME_PARTICLES_RE.sub(" ", s.lower())
    return _WORD_3_PLUS_RE.findall(cleaned)


def names_likely_same_person(a: str, b: str) -> bool:
    """True when two display names refer to the same person (ballot vs common form)."""
    ak, bk = namekey_loose(a), namekey_loose(b)
    if not ak or not bk or len(ak) < 8 or len(bk) < 8:
        return False
    if ak == bk:
        return True
    ca = _MOHD_PREFIX_RE.sub("", ak)
    cb = _MOHD_PREFIX_RE.sub("", bk)
    if ca and cb and len(ca) >= 8 and ca == cb:
        return True
    lo, hi = (ak, bk) if len(ak) <= len(bk) else (bk, ak)
    return bool(hi.endswith(lo) and (len(lo) / len(hi)) >= 0.6)


def adun_photo_matches_person(adun_name: str, person_name: str) -> bool:
    """True when an aduns.json portrait is safe to attach to the seat's current winner."""
    if not adun_name or not person_name:
        return False
    ak, bk = namekey_loose(adun_name), namekey_loose(person_name)
    if not ak or not bk:
        return False
    if ak == bk:
        return True
    ca = _MOHD_PREFIX_RE.sub("", ak)
    cb = _MOHD_PREFIX_RE.sub("", bk)
    if ca and cb and ca == cb:
        return True
    if len(ca) >= 6 and len(cb) >= 6 and (cb in ca or ca in cb):
        return True
    if len(ca) >= 8 and len(cb) >= 8 and abs(len(ca) - len(cb)) <= 2 and ca[:6] == cb[:6]:
        return True
    if names_likely_same_person(adun_name, person_name):
        return True
    ta = person_name_tokens(adun_name)
    tb = person_name_tokens(person_name)
    if not ta or not tb:
        return False
    set_a, set_b = set(ta), set(tb)
    shared = [t for t in ta if t in set_b]
    if len(shared) >= 2:
        return True
    if len(shared) == 1 and len(shared[0]) >= 6:
        only_a = [t for t in ta if t not in set_b and len(t) >= 5]
        only_b = [t for t in tb if t not in set_a and len(t) >= 5]
        return not (only_a and only_b)
    shorter = ta if len(ta) <= len(tb) else tb
    longer_key = bk if len(ta) <= len(tb) else ak
    if len(shorter) >= 1 and all(len(t) >= 4 and t in longer_key for t in shorter):
        return any(len(t) >= 5 for t in shorter)
    return False


def title_case_name(s: str | None) -> str:
    """Title-case all-caps ballot names while preserving Malaysian particles."""
    if not s or s != s.upper():
        return s or ""

    def _repl(m: re.Match[str]) -> str:
        w = m.group(0)
        return w if w in _PARTICLES else w.capitalize()

    return _WORD_RE.sub(_repl, s.lower())


def monogram_color(name: str) -> str:
    """Deterministic background hue based on name characters."""
    h = 0
    for ch in name:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return f"hsl({h % 360} 42% 40%)"


def person_initials(name: str | None) -> str:
    """First and last initials for monogram badges."""
    parts = (name or "").strip().split()
    if not parts:
        return "?"
    first = parts[0][0] if parts[0] else ""
    last = parts[-1][0] if len(parts) > 1 and parts[-1] else ""
    return (first + last).upper()


def with_current_affiliation(
    result: Mapping[str, Any] | None,
    override: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Replicate lib.js withCurrentAffiliation."""
    base = dict(result or {})
    if not override or not isinstance(override, dict):
        return base
    res = dict(base)
    if "current_name" in override:
        res["name"] = override["current_name"]
    if "current_party" in override:
        res["party"] = override["current_party"]
    if "current_coalition" in override:
        res["coalition"] = override["current_coalition"]
    res["election_coalition"] = base.get("coalition")
    res["election_party"] = base.get("party")
    res["current_bloc"] = (
        override.get("current_bloc") or base.get("coalition") or base.get("party") or ""
    )
    res["vacant_since"] = override.get("vacant_since")
    res["affiliation_status"] = override.get("affiliation_status")
    return res


# ── Color & Swatch Helpers ────────────────────────────────────────────────


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


# ── Dual Seat and Party Stats Calculation ──────────────────────────────────


def dual_seat_map(
    mps: Sequence[PoliticianCardModel],
    aduns: Sequence[PoliticianCardModel],
) -> tuple[dict[str, PoliticianCardModel], set[str]]:
    """Compute dual mandates (people holding both a parliament and a state seat)."""
    mp_to_dun: dict[str, PoliticianCardModel] = {}
    matched_dun: set[str] = set()
    mp_hit: dict[str, int] = {}
    keyed_mps: list[tuple[PoliticianCardModel, str]] = [(m, namekey_loose(m.name)) for m in mps]

    for a in aduns:
        if a.code in DUAL_CROSS_STATE:
            target_mp_code = DUAL_CROSS_STATE[a.code]
            mp_to_dun[target_mp_code] = a
            matched_dun.add(a.code)
            continue
        ak = namekey_loose(a.name)
        if len(ak) < 8:
            continue
        hits = [
            m
            for m, k in keyed_mps
            if m.state == a.state and len(k) >= 8 and names_likely_same_person(m.name, a.name)
        ]
        if len(hits) != 1:
            continue
        mp = hits[0]
        mp_hit[mp.code] = mp_hit.get(mp.code, 0) + 1
        mp_to_dun[mp.code] = a
        matched_dun.add(a.code)

    for code, n in list(mp_hit.items()):
        if n > 1:
            mp_to_dun.pop(code, None)

    # Clean up matched_dun so only currently assigned ADUNs remain
    valid_adun_codes = {rep.code for rep in mp_to_dun.values()}
    matched_dun = {c for c in matched_dun if c in valid_adun_codes}

    return mp_to_dun, matched_dun


def party_stats_list(
    mps: Sequence[PoliticianCardModel],
    aduns: Sequence[PoliticianCardModel],
) -> list[PartyStatsModel]:
    """Aggregate seat counts, top states, and representative samples per party."""
    by_party: dict[str, dict[str, Any]] = {}

    def add(p: PoliticianCardModel, tier: str) -> None:
        if p.vacated:
            return
        party = norm_party_label(p.party or p.coalition) or "UNKNOWN"
        rec = by_party.setdefault(
            party,
            {
                "party": party,
                "coalition_counts": {},
                "parliament": 0,
                "dun": 0,
                "states": {},
                "reps": [],
            },
        )
        if tier == "parlimen":
            rec["parliament"] += 1
        else:
            rec["dun"] += 1
        if p.coalition:
            rec["coalition_counts"][p.coalition] = rec["coalition_counts"].get(p.coalition, 0) + 1
        if p.state:
            rec["states"][p.state] = rec["states"].get(p.state, 0) + 1
        seat_label = f"{p.dun_code} · {p.seat_name}" if p.dun_code else f"{p.code} · {p.seat_name}"
        rec["reps"].append(
            RepresentativeSample(
                name=p.name,
                state=p.state or "",
                seat=seat_label,
                tier=tier,
            )
        )

    for p in mps:
        add(p, "parlimen")
    for a in aduns:
        add(a, "dun")

    out: list[PartyStatsModel] = []
    for party, rec in by_party.items():
        c_counts = [item for item in rec["coalition_counts"].items() if item[0]]
        c_counts.sort(key=lambda x: (-x[1], x[0]))
        coalition = c_counts[0][0] if c_counts else party

        s_counts = list(rec["states"].items())
        s_counts.sort(key=lambda x: (-x[1], x[0]))
        top_states = tuple(s_counts[:3])

        samples = sorted(
            rec["reps"],
            key=lambda r: (
                0 if r.tier == "parlimen" else 1,
                unicodedata.normalize("NFKD", r.name).casefold(),
            ),
        )[:3]

        out.append(
            PartyStatsModel(
                party=party,
                coalition=coalition,
                total=rec["parliament"] + rec["dun"],
                parliament=rec["parliament"],
                dun=rec["dun"],
                top_states=top_states,
                samples=tuple(samples),
            )
        )

    out.sort(key=lambda p: (-p.total, p.party))
    return out


# ── Page Model Builder ────────────────────────────────────────────────────


def politicians_page_model(
    *,
    parlimen_seats: Sequence[Mapping[str, Any]],
    dun_seats: Sequence[Mapping[str, Any]],
    mp_profiles: Mapping[str, Any] | None = None,
    politicians_data: Mapping[str, Any] | None = None,
    current_affiliations: Mapping[str, Any] | None = None,
    results_dun: Mapping[str, Any] | None = None,
    prn16: Mapping[str, Any] | None = None,
    aduns: Mapping[str, Any] | None = None,
    status: ElectionStatus | None = None,
    updated_at: date | None = None,
    sources_count: int = 3,
) -> PoliticiansPageModel:
    """Build the Politicians Directory model purely from in-memory JSON data."""
    cur_aff = current_affiliations or {}
    parlimen_aff = cur_aff.get("parlimen", {})
    dun_aff = cur_aff.get("dun", {})
    dissolved = cur_aff.get("dissolved_assemblies", {})

    parlimen_by_code = {s["code"]: s for s in parlimen_seats}

    # Federal MP roster
    mps_raw = {}
    if mp_profiles and "mps" in mp_profiles:
        for c, v in mp_profiles["mps"].items():
            mps_raw[c] = v.get("bio", v)
    elif politicians_data and "mps" in politicians_data:
        mps_raw = politicians_data["mps"]

    mps_list: list[PoliticianCardModel] = []
    for code, m in mps_raw.items():
        seat = parlimen_by_code.get(code)
        current = with_current_affiliation(m, parlimen_aff.get(code))
        leg = mp_profiles.get("mps", {}).get(code, {}).get("legislative") if mp_profiles else None
        ge15_coal = norm_party_label(leg.get("coalition")) if leg and leg.get("coalition") else ""
        divs = len(leg.get("divisions", [])) if leg and leg.get("divisions") else 0
        bills = len(leg.get("bills_sponsored", [])) if leg and leg.get("bills_sponsored") else 0
        mps_list.append(
            PoliticianCardModel(
                code=code,
                name=current.get("name") or m.get("name", ""),
                party=norm_party_label(current.get("party"))
                or current.get("current_bloc")
                or current.get("party")
                or "",
                coalition=norm_party_label(current.get("coalition"))
                or current.get("current_bloc")
                or current.get("coalition")
                or "",
                ge15_coalition=ge15_coal,
                divisions_count=divs,
                bills_count=bills,
                has_legislative=bool(leg),
                photo=m.get("photo"),
                socials=m.get("socials"),
                socials_source=m.get("socials_source"),
                vacated=bool(m.get("vacated")) or bool(current.get("vacant_since")),
                seat_name=seat["name"] if seat else code,
                state=seat["state"] if seat else "",
            )
        )
    mps_list.sort(key=lambda a: unicodedata.normalize("NFKD", a.name).casefold())

    # State ADUN roster
    res_dun = results_dun or {}
    prn16_seats = (prn16 or {}).get("seats", {})
    aduns_dict = aduns or {}

    aduns_list: list[PoliticianCardModel] = []
    for seat in dun_seats:
        code = seat["code"]
        r = None
        own = res_dun.get(code)
        if own and own.get("name"):
            cur = with_current_affiliation(own, dun_aff.get(code))
            r = {
                "name": own["name"],
                "party": norm_party_label(cur.get("party"))
                or cur.get("current_bloc")
                or cur.get("party")
                or "",
                "coalition": norm_party_label(cur.get("coalition"))
                or cur.get("current_bloc")
                or cur.get("coalition")
                or "",
            }
        elif code in prn16_seats and prn16_seats[code].get("incumbent_2022"):
            e = prn16_seats[code]
            parts = str(e.get("incumbent_party_2022", "")).split("-")
            cur = with_current_affiliation(
                {
                    "name": e["incumbent_2022"],
                    "coalition": norm_party_label(parts[0] if parts else ""),
                    "party": norm_party_label(
                        parts[1] if len(parts) > 1 else (parts[0] if parts else "")
                    ),
                },
                dun_aff.get(code),
            )
            r = {
                "name": cur.get("name", ""),
                "party": norm_party_label(cur.get("party"))
                or cur.get("current_bloc")
                or cur.get("party")
                or "",
                "coalition": norm_party_label(cur.get("coalition"))
                or cur.get("current_bloc")
                or cur.get("coalition")
                or "",
            }
        if not r:
            continue

        ad = aduns_dict.get(code)
        winner_name = own.get("name") if own else None
        photo = None
        pretty_name = None
        if ad and (not winner_name or adun_photo_matches_person(ad.get("name", ""), winner_name)):
            photo = ad.get("photo")
            pretty_name = ad.get("name")
        elif winner_name:
            pretty_name = title_case_name(winner_name)

        aduns_list.append(
            PoliticianCardModel(
                code=code,
                dun_code=seat.get("dun_code"),
                name=pretty_name or title_case_name(r["name"]),
                party=r["party"],
                coalition=r["coalition"],
                photo=photo,
                seat_name=seat["name"],
                state=seat["state"],
                former=bool(dissolved.get(seat["state"])),
            )
        )
    aduns_list.sort(key=lambda a: unicodedata.normalize("NFKD", a.name).casefold())

    # Dual mandates & All list
    mp_to_dun, matched_dun = dual_seat_map(mps_list, aduns_list)
    all_list: list[PoliticianCardModel] = []
    for p in mps_list:
        dun_rep = mp_to_dun.get(p.code)
        if dun_rep:
            also = AlsoDun(
                code=dun_rep.code,
                dun_code=dun_rep.dun_code or "",
                seat_name=dun_rep.seat_name,
            )
            all_list.append(
                PoliticianCardModel(
                    code=p.code,
                    name=p.name,
                    party=p.party,
                    coalition=p.coalition,
                    seat_name=p.seat_name,
                    state=p.state,
                    dun_code=p.dun_code,
                    ge15_coalition=p.ge15_coalition,
                    divisions_count=p.divisions_count,
                    bills_count=p.bills_count,
                    has_legislative=p.has_legislative,
                    photo=p.photo,
                    socials=p.socials,
                    socials_source=p.socials_source,
                    vacated=p.vacated,
                    also_dun=also,
                    former=p.former,
                )
            )
        else:
            all_list.append(p)

    for a in aduns_list:
        if a.code not in matched_dun:
            all_list.append(a)

    all_list.sort(key=lambda a: unicodedata.normalize("NFKD", a.name).casefold())

    # Party rollups
    parties = party_stats_list(mps_list, aduns_list)

    # Unique filter options
    states = tuple(sorted({p.state for p in all_list if p.state}))
    unique_coals = {p.coalition for p in all_list if p.coalition}

    def _coal_sort_key(c: str) -> tuple[int, str]:
        idx = COALITION_ORDER.index(c) if c in COALITION_ORDER else 99
        return (idx, c)

    coalitions = tuple(sorted(unique_coals, key=_coal_sort_key))

    return PoliticiansPageModel(
        updated_at=updated_at or datetime.now(UTC).date(),
        sources_count=sources_count,
        status=status
        or ElectionStatus(constitutional_deadline=date(2028, 2, 17), source="default"),
        all_politicians=tuple(all_list),
        mps=tuple(mps_list),
        aduns=tuple(aduns_list),
        parties=tuple(parties),
        states=states,
        coalitions=coalitions,
    )


# ── HTML Rendering ─────────────────────────────────────────────────────────

_SOCIAL_ICONS: dict[str, str] = {
    "fb": '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M13.4 21v-8h2.7l.4-3.1h-3.1V7.9c0-.9.25-1.5 1.55-1.5h1.65V3.63c-.3-.04-1.3-.13-2.47-.13-2.45 0-4.13 1.5-4.13 4.24V9.9H7.5V13h2.5v8z"/></svg>',
    "ig": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" aria-hidden="true"><rect x="3.5" y="3.5" width="17" height="17" rx="5"/><circle cx="12" cy="12" r="3.8"/><circle cx="17.1" cy="6.9" r="1" fill="currentColor" stroke="none"/></svg>',
    "tw": '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M17.5 3h3.1l-6.77 7.73L21.75 21H15.5l-4.9-6.4L5 21H1.9l7.24-8.27L2 3h6.4l4.43 5.86zm-1.1 16.14h1.72L7.7 4.77H5.86z"/></svg>',
    "tiktok": '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M16.6 3c.32 2.05 1.46 3.4 3.4 3.55v2.72c-1.13.11-2.2-.26-3.4-.98v5.9c0 3.5-2.5 5.86-5.68 5.86-2.9 0-5.22-2.24-5.22-5.2 0-3.2 2.66-5.55 6.03-4.98v2.94c-.4-.13-.9-.2-1.34-.2-1.28 0-2.2.9-2.2 2.2 0 1.4 1.05 2.3 2.35 2.3 1.4 0 2.4-1 2.4-2.83V3z"/></svg>',
    "youtube": '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M22 8.2a2.6 2.6 0 0 0-1.82-1.84C18.57 6 12 6 12 6s-6.57 0-8.18.36A2.6 2.6 0 0 0 2 8.2 27 27 0 0 0 1.7 12 27 27 0 0 0 2 15.8a2.6 2.6 0 0 0 1.82 1.84C5.43 18 12 18 12 18s6.57 0 8.18-.36A2.6 2.6 0 0 0 22 15.8 27 27 0 0 0 22.3 12 27 27 0 0 0 22 8.2M10 15V9l5.2 3z"/></svg>',
    "telegram": '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M21.9 4.35 18.7 19.5c-.24 1.05-.87 1.3-1.76.8l-4.86-3.58-2.34 2.26c-.26.26-.48.48-.98.48l.35-4.94 9-8.13c.4-.35-.08-.54-.6-.2L6.7 13.06l-4.79-1.5c-1.04-.32-1.06-1.04.22-1.54l18.72-7.22c.87-.32 1.63.2 1.35 1.55z"/></svg>',
    "web": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.6 2.6 2.6 15.4 0 18M12 3c-2.6 2.6-2.6 15.4 0 18"/></svg>',
}

_SOCIAL_META: dict[str, tuple[str, Any]] = {
    "fb": ("Facebook", lambda v: f"https://facebook.com/{v}"),
    "ig": ("Instagram", lambda v: f"https://instagram.com/{v}"),
    "tw": ("X", lambda v: f"https://x.com/{v}"),
    "tiktok": ("TikTok", lambda v: f"https://tiktok.com/@{v}"),
    "youtube": ("YouTube", lambda v: f"https://youtube.com/channel/{v}"),
    "telegram": ("Telegram", lambda v: f"https://t.me/{v}"),
    "web": ("Website", lambda v: v if v.startswith(("http://", "https://")) else f"https://{v}"),
}

_SOCIAL_ORDER: tuple[str, ...] = ("fb", "ig", "tw", "tiktok", "youtube", "telegram", "web")


def person_photo_html(name: str, photo: str | None, cls: str = "") -> str:
    """Render photo thumbnail or deterministic monogram fallback."""
    esc_name = html.escape(name)
    esc_cls = html.escape(cls)
    if photo:
        return (
            f'<img class="pol-photo {esc_cls}" src="{html.escape(photo)}" '
            f'alt="{esc_name}" loading="lazy" decoding="async" width="72" height="72">'
        )
    color = monogram_color(name or "")
    initials = html.escape(person_initials(name))
    return (
        f'<span class="pol-photo pol-monogram {esc_cls}" style="background:{color}" '
        f'aria-hidden="true">{initials}</span>'
    )


def social_links_html(
    socials: Mapping[str, Any] | None,
    source: str | None = None,
    compact: bool = True,
    max_links: int = 4,
) -> str:
    """Render icon-only social links matching app.js socialLinksHTML."""
    if not socials:
        return ""

    def usable(v: Any) -> bool:
        return isinstance(v, str) and bool(v.strip()) and not bool(re.search(r"\s", v))

    keys = [k for k in _SOCIAL_ORDER if usable(socials.get(k))]
    extra = 0
    if max_links and len(keys) > max_links:
        extra = len(keys) - max_links
        keys = keys[:max_links]

    items = []
    for k in keys:
        label, to_url = _SOCIAL_META[k]
        url = to_url(socials[k])
        icon_svg = _SOCIAL_ICONS[k]
        items.append(
            f'<a class="pol-soc-icon" href="{html.escape(url)}" target="_blank" rel="noopener" '
            f'aria-label="{html.escape(label)}" title="{html.escape(label)}">{icon_svg}</a>'
        )
    if not items:
        return ""

    more = f'<span class="pol-soc-more" aria-hidden="true">+{extra}</span>' if extra else ""
    cls_str = "pol-socials"
    if compact:
        cls_str += " pol-socials-compact"
    if source == "community":
        cls_str += " pol-socials-unverified"

    return f'<div class="{cls_str}">{"".join(items)}{more}</div>'


def render_politician_card(p: PoliticianCardModel, language: Language) -> str:
    """Render one card in the politicians grid."""
    if p.also_dun:
        seat_line = f"{p.code} · {p.seat_name}  ﹢  {p.also_dun.dun_code} · {p.also_dun.seat_name}"
    else:
        seat_line = f"{p.dun_code or p.code} · {p.seat_name}"

    party_badge = norm_party_label(p.party or p.coalition) or p.party or p.coalition or ""
    vacant_str = t(language, "Seat vacant", "Kerusi kosong")

    aria_vacant = f", {vacant_str}" if p.vacated else ""
    aria_label = html.escape(f"{p.name}, {seat_line}{aria_vacant}")

    coal_diff = ""
    if p.ge15_coalition and p.coalition and p.ge15_coalition != p.coalition:
        note_text = t(
            language,
            f"GE15 ballot: {p.ge15_coalition} · Current: {p.coalition}",
            f"Undian GE15: {p.ge15_coalition} · Terkini: {p.coalition}",
        )
        coal_diff = (
            f'<div class="pol-card-coal-diff" title="{html.escape(note_text)}">'
            f"GE15: {html.escape(p.ge15_coalition)}</div>"
        )

    if p.has_legislative and (p.divisions_count > 0 or p.bills_count > 0):
        div_str = t(
            language,
            f"{p.divisions_count} votes",
            f"{p.divisions_count} undian",
        )
        bills_str = (
            " · "
            + t(
                language,
                f"{p.bills_count} bills",
                f"{p.bills_count} RUU",
            )
            if p.bills_count > 0
            else ""
        )
        leg_line = f'<div class="pol-card-leg">{html.escape(div_str + bills_str)}</div>'
    else:
        leg_line = '<div class="pol-card-leg-spacer"></div>'

    socials_html = (
        social_links_html(p.socials, p.socials_source, compact=True, max_links=4)
        if p.socials
        else '<div class="pol-card-socials-spacer"></div>'
    )

    vacant_badge = (
        f' <span class="pol-card-vacant">{html.escape(vacant_str)}</span>' if p.vacated else ""
    )

    badge_style = pill_style(party_color(p.coalition or p.party))
    photo_html = person_photo_html(p.name, p.photo)

    return f"""
<div class="pol-card" tabindex="0" role="button" data-pol-code="{html.escape(p.code)}" aria-label="{aria_label}">
  <div class="pol-card-photo">
    {photo_html}
    <span class="pol-card-badge pill" style="{badge_style}">{html.escape(party_badge)}</span>
  </div>
  <div class="pol-card-name">{html.escape(p.name)}{vacant_badge}</div>
  <div class="pol-card-seat" title="{html.escape(seat_line)}">{html.escape(seat_line)}</div>
  {coal_diff}
  {leg_line}
  {socials_html}
</div>""".strip()


def render_party_card(p: PartyStatsModel, language: Language) -> str:
    """Render one party/bloc rollup card in the parties grid."""
    state_none = t(language, "No state seats", "Tiada kerusi negeri")
    state_line = " · ".join(f"{s} {n}" for s, n in p.top_states) if p.top_states else state_none

    samples_html = "".join(
        f"<li><b>{html.escape(r.name)}</b><span>{html.escape(r.seat)}</span></li>"
        for r in p.samples
    )

    open_aria = t(
        language,
        f"View representatives for {p.party}",
        f"Lihat wakil untuk {p.party}",
    )
    total_lbl = t(language, "Total", "Jumlah")
    parl_lbl = t(language, "MP", "MP")
    state_lbl = t(language, "ADUN", "ADUN")
    top_states_lbl = t(language, "Strongest states", "Negeri terkuat")
    open_lbl = t(language, "View representatives →", "Lihat wakil →")

    coal_pill = ""
    if p.coalition and p.coalition != p.party:
        c_style = pill_style(party_color(p.coalition))
        coal_pill = f'<span class="pill" style="{c_style}">{html.escape(p.coalition)}</span>'

    party_style = pill_style(party_color(p.coalition or p.party))

    return f"""
<button type="button" class="pol-party-card" data-pol-party="{html.escape(p.party)}" aria-label="{html.escape(open_aria)}">
  <div class="pol-party-top">
    <span class="pol-party-mark" style="{party_style}">{html.escape(p.party)}</span>
    {coal_pill}
  </div>
  <div class="pol-party-stats">
    <span><small>{html.escape(total_lbl)}</small><b>{p.total}</b></span>
    <span><small>{html.escape(parl_lbl)}</small><b>{p.parliament}</b></span>
    <span><small>{html.escape(state_lbl)}</small><b>{p.dun}</b></span>
  </div>
  <div class="pol-party-meta"><span>{html.escape(top_states_lbl)}</span><b>{html.escape(state_line)}</b></div>
  <ul class="pol-party-samples">{samples_html}</ul>
  <span class="pol-party-open">{html.escape(open_lbl)}</span>
</button>""".strip()


def render_politicians_body(
    model: PoliticiansPageModel,
    language: Language = Language.EN,
    tier: str = "all",
) -> str:
    """Render the inner HTML of the politicians view matching app.js DOM contract."""
    back_lbl = t(language, "Back to map", "Kembali ke peta")
    title_lbl = t(language, "Politicians", "Ahli Politik")
    sub_lbl = t(
        language,
        "222 parliamentary seats (220 MPs, 2 vacant) and 600 state seats",
        "222 kerusi Parlimen (220 Ahli Parlimen, 2 kosong) dan 600 kerusi DUN",
    )

    tab_all = t(language, "All", "Semua")
    tab_mp = t(language, "Parliament · MP", "Parlimen · MP")
    tab_adun = t(language, "State · ADUN", "Negeri · ADUN")
    tab_parties = t(language, "Parties / blocs", "Parti / blok")

    party_mode = tier == "parties"

    search_ph = t(
        language,
        "Search a party or bloc…" if party_mode else "Search a politician…",
        "Cari parti atau blok…" if party_mode else "Cari ahli politik…",
    )
    all_states_lbl = t(language, "All states", "Semua negeri")
    all_coal_lbl = t(language, "All coalitions", "Semua gabungan")

    state_opts = "".join(
        f'<option value="{html.escape(s)}">{html.escape(s)}</option>' for s in model.states
    )
    coal_opts = "".join(
        f'<option value="{html.escape(c)}">{html.escape(c)}</option>' for c in model.coalitions
    )

    controls = f"""
      <div class="pol-dir-controls">
        <input id="pol-search" class="pol-dir-search" type="search" autocomplete="off" spellcheck="false"
          aria-label="{html.escape(search_ph)}" placeholder="{html.escape(search_ph)}" value="">
        <select id="pol-state" aria-label="{html.escape(all_states_lbl)}">
          <option value="">{html.escape(all_states_lbl)}</option>
          {state_opts}
        </select>
        <select id="pol-coal" aria-label="{html.escape(all_coal_lbl)}">
          <option value="">{html.escape(all_coal_lbl)}</option>
          {coal_opts}
        </select>
      </div>"""

    if tier == "parties":
        items_count = len(model.parties)
        count_text = t(
            language,
            f"{items_count} parties / blocs",
            f"{items_count} parti / blok",
        )
        grid_class = "pol-party-grid"
        cards_html = "\n".join(render_party_card(p, language) for p in model.parties)
        src_text = t(
            language,
            "Party counts are aggregated from the same MP and ADUN roster/result data. Some rows are coalition-level where the source roster does not split component parties.",
            "Kiraan parti dijana daripada data senarai MP dan ADUN/keputusan yang sama. Sesetengah baris berada pada tahap gabungan apabila sumber tidak memecahkan parti komponen.",
        )
    else:
        active_list = (
            model.mps
            if tier == "parlimen"
            else (model.aduns if tier == "dun" else model.all_politicians)
        )
        items_count = len(active_list)
        count_text = t(
            language,
            f"{items_count} politicians",
            f"{items_count} ahli politik",
        )
        grid_class = "pol-grid"
        cards_html = "\n".join(render_politician_card(p, language) for p in active_list)
        src_text = t(
            language,
            "Roster: SPR / DOSM · photos & bios: Wikidata, Wikimedia Commons, Wikipedia (CC BY-SA — see each credit)",
            "Senarai: SPR / DOSM · foto & bio: Wikidata, Wikimedia Commons, Wikipedia (CC BY-SA — lihat kredit)",
        )

    on_all = ' class="on"' if tier == "all" else ""
    sel_all = "true" if tier == "all" else "false"
    on_parl = ' class="on"' if tier == "parlimen" else ""
    sel_parl = "true" if tier == "parlimen" else "false"
    on_dun = ' class="on"' if tier == "dun" else ""
    sel_dun = "true" if tier == "dun" else "false"
    on_parties = ' class="on"' if tier == "parties" else ""
    sel_parties = "true" if tier == "parties" else "false"

    return f"""
    <div class="pol-dir">
      <div class="pol-dir-head">
        <button id="pol-back" class="pol-back" type="button">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 18l-6-6 6-6"/></svg>
          <span>{html.escape(back_lbl)}</span>
        </button>
        <h1>{html.escape(title_lbl)}</h1>
        <p class="pol-dir-sub">{html.escape(sub_lbl)}</p>
      </div>
      <div class="pol-dir-tabs-wrap">
        <div class="seg chip pol-dir-tabs" role="tablist">
          <button type="button" role="tab" data-pol-tier="all" aria-selected="{sel_all}"{on_all}>{html.escape(tab_all)}</button>
          <button type="button" role="tab" data-pol-tier="parlimen" aria-selected="{sel_parl}"{on_parl}>{html.escape(tab_mp)}</button>
          <button type="button" role="tab" data-pol-tier="dun" aria-selected="{sel_dun}"{on_dun}>{html.escape(tab_adun)}</button>
          <button type="button" role="tab" data-pol-tier="parties" aria-selected="{sel_parties}"{on_parties}>{html.escape(tab_parties)}</button>
        </div>
      </div>
      {controls}
      <div id="pol-count" class="pol-dir-count">{html.escape(count_text)}</div>
      <div id="pol-grid" class="{grid_class}">
        {cards_html}
      </div>
      <p class="pol-dir-src">{html.escape(src_text)}</p>
    </div>
""".strip()


def render_politicians_page(
    model: PoliticiansPageModel,
    *,
    language: Language = Language.EN,
) -> str:
    """Render full HTML page including persistent shell and meta/OG tags."""
    title = t(
        language,
        "Politicians — Dewan Rakyat & State Assemblies | PolitikKu",
        "Ahli Politik — Dewan Rakyat & Dewan Undangan Negeri | PolitikKu",
    )
    description = t(
        language,
        "Directory of 222 Members of Parliament and 600 State Assembly members (ADUNs) across Malaysia. Track party affiliations, voting records, and constituency representation.",
        "Direktori 222 Ahli Parlimen dan 600 Ahli Dewan Undangan Negeri (ADUN) di seluruh Malaysia. Semak parti politik, rekod undian, dan wakil kawasan.",
    )

    body_html = render_politicians_body(model, language=language, tier="all")

    page_html: str = render_shell(
        title=title,
        description=description,
        active_nav="politicians",
        language=language,
        page_path=PAGE_PATH,
        updated_at=model.updated_at,
        sources_count=model.sources_count,
        status=model.status,
        body_html=body_html,
    )
    return page_html


# ── File I/O & CLI ─────────────────────────────────────────────────────────


def load_politicians_data(base_path: Path = Path("frontend/public/data")) -> PoliticiansPageModel:
    """Load JSON files from static data directory and build PoliticiansPageModel."""

    def _read_json(filename: str) -> Any:
        file_path = base_path / filename
        if not file_path.exists():
            repo_file = Path("data") / filename
            if repo_file.exists():
                return json.loads(repo_file.read_text(encoding="utf-8"))
            return {}
        return json.loads(file_path.read_text(encoding="utf-8"))

    parlimen_seats = _read_json("seats-parlimen.json").get("seats", [])
    dun_seats = _read_json("seats-dun.json").get("seats", [])
    mp_profiles = _read_json("mp-profiles-merged.json")
    politicians_data = _read_json("politicians.json")
    current_affiliations = _read_json("current-affiliations.json")
    results_dun = _read_json("results-dun.json")
    prn16 = _read_json("prn16-johor.json")
    aduns = _read_json("aduns.json")

    from lpa.config import load_election_status

    status = load_election_status()

    return politicians_page_model(
        parlimen_seats=parlimen_seats,
        dun_seats=dun_seats,
        mp_profiles=mp_profiles,
        politicians_data=politicians_data,
        current_affiliations=current_affiliations,
        results_dun=results_dun,
        prn16=prn16,
        aduns=aduns,
        status=status,
    )


def build_and_write_politicians_pages(
    output_dir: Path = Path("public"),
    base_data_path: Path = Path("frontend/public/data"),
) -> tuple[int, int]:
    """Render and write `/politicians/index.html` and `/ms/politicians/index.html`."""
    model = load_politicians_data(base_data_path)

    en_html = render_politicians_page(model, language=Language.EN)
    ms_html = render_politicians_page(model, language=Language.MS)

    en_dir = output_dir / "politicians"
    ms_dir = output_dir / "ms" / "politicians"
    en_dir.mkdir(parents=True, exist_ok=True)
    ms_dir.mkdir(parents=True, exist_ok=True)

    en_target = en_dir / "index.html"
    ms_target = ms_dir / "index.html"

    en_bytes = en_html.encode("utf-8")
    ms_bytes = ms_html.encode("utf-8")

    en_target.write_bytes(en_bytes)
    ms_target.write_bytes(ms_bytes)

    return len(en_bytes), len(ms_bytes)


def main() -> None:
    """CLI entry point for rendering Politicians directory and per-Seat MP profiles."""
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

    en_len, ms_len = build_and_write_politicians_pages(
        output_dir=args.output_dir,
        base_data_path=args.data_dir,
    )
    print(
        f"Wrote politicians directory to {args.output_dir}/politicians/index.html ({en_len} bytes)"
    )
    print(
        f"Wrote politicians directory to {args.output_dir}/ms/politicians/index.html ({ms_len} bytes)"
    )

    # Also build per-seat MP profiles if available
    try:
        from lpa.politikku_mp_profile import build_and_write_mp_profile_pages

        mp_count = build_and_write_mp_profile_pages(
            output_dir=args.output_dir,
            base_data_path=args.data_dir,
        )
        print(f"Wrote {mp_count} MP profile pages")
    except (ImportError, OSError, ValueError, KeyError) as exc:
        print(f"Notice: MP profiles build not run from politicians main: {exc}")


if __name__ == "__main__":
    main()
