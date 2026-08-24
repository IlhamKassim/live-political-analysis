"""PolitikKu bilingual copy (#81): the settled EN/BM key-pairs table plus the
shared vocabulary every page's own translation calls draw on.

`politikku_shell.py` owns `Language` and the `t(language, en, ms)` primitive
(every page's rendering function calls `t()` at each point bilingual text
appears — see that module). This module holds two things on top of that:

1. **The settled table**, `design_handoff_politikku/README.md`'s "2. Homepage"
   section (the bilingual key-pairs table given verbatim by #81's own ticket
   body) — one constant per row, so a page's rendering code imports the exact
   settled string rather than retyping it and risking a transcription slip.
2. **Shared vocabulary** — a handful of terms not given standalone by the
   settled table but derivable from it (the table only gives whole-phrase
   pairs, e.g. "GE16 Seat Projection" -> "Unjuran kerusi PRU16", not a
   per-word gloss) and then reused by more than one page. `CONTEXT.md`'s
   "## Language" section is explicit that its English vocabulary discipline
   ("never a synonym") matters *because* the same word means the same thing
   everywhere in this codebase; the same now has to hold in BM. Promoting
   these to one constant each is what makes that mechanically true — a page
   that needs "Government Coalition" imports `GOVERNMENT_COALITION` rather
   than writing its own "Gabungan Kerajaan" a second time that could drift.

None of the strings below are silently presented as more settled than they
are: the settled-table constants are exactly the ticket's own table, unedited;
the "derived" constants are noted as such in their own docstring, and the PR
description that shipped this module lists every one of them (plus all the
fully independent page copy that has no settled source at all) under
"New BM copy — no settled source, wants a native-BM sanity check before
merge," per this ticket's own honesty requirement. Do not add a new constant
here and call it settled unless it is copied verbatim from the table.
"""

from __future__ import annotations

from lpa.politikku_shell import Language, t

# ── the settled table, verbatim ──────────────────────────────────────────
# design_handoff_politikku/README.md, "2. Homepage" -> "Bilingual (1c)".
# Each pair is exactly the table's own English/BM cells, not paraphrased.

FIND_YOUR_MP_EN = "Find your MP"
FIND_YOUR_MP_MS = "Cari Ahli Parlimen anda"

CONSTITUENCY_LOOKUP_EN = "Constituency lookup"
CONSTITUENCY_LOOKUP_MS = "Carian kawasan"

POSTCODE_OR_CONSTITUENCY_EN = "Postcode or constituency"
POSTCODE_OR_CONSTITUENCY_MS = "Poskod atau nama kawasan"

USE_MY_LOCATION_EN = "Use my location"
USE_MY_LOCATION_MS = "Guna lokasi saya"

GE16_SEAT_PROJECTION_EN = "GE16 Seat Projection"
GE16_SEAT_PROJECTION_MS = "Unjuran kerusi PRU16"

NOT_CALIBRATED_EN = "NOT CALIBRATED"
NOT_CALIBRATED_MS = "BELUM DITENTUKUR"

GOVERNMENT_CLEAR_EN = "Government clear"
GOVERNMENT_CLEAR_MS = "Kerajaan jelas"
WITHIN_MODEL_NOISE_EN = "Within model noise"
WITHIN_MODEL_NOISE_MS = "Dalam ralat model"
NONGOVERNMENT_CLEAR_EN = "Non-government clear"
NONGOVERNMENT_CLEAR_MS = "Bukan kerajaan jelas"
"""The legend/hemicycle three-way split — the settled table's one row split
into its three `·`-free segments (the table itself gives them slash-
separated as one cell; this module's callers each need one at a time)."""

DEWAN_RAKYAT_THIS_WEEK_EN = "Dewan Rakyat this week"
DEWAN_RAKYAT_THIS_WEEK_MS = "Dewan Rakyat minggu ini"

METHODOLOGY_AND_SOURCES_EN = "Methodology & sources"
METHODOLOGY_AND_SOURCES_MS = "Metodologi & sumber"

SOURCES_EN = "Sources"
SOURCES_MS = "Sumber"

# "Passed · 2nd reading" -> "Lulus · bacaan kedua" is the settled table's
# remaining row. It has no direct call site: this repo's real bill-stage
# badge shows either `_stage_label(bill.stage)` (English, #74's own sourced
# gloss) or, in BM, the Bill's own `stage` field unchanged — "Lulus" is
# already Parliament's real Malay word for that stage, not a translation
# this codebase produces, so there is nothing here to route through `t()`
# for. Kept as a comment, not a constant, since defining an unused constant
# would claim a call site that does not exist.

# ── derived vocabulary (not standalone in the table — see module docstring) ─

GOVERNMENT_COALITION_EN = "Government Coalition"
GOVERNMENT_COALITION_MS = "Gabungan Kerajaan"
"""Substring of the settled `... to the Government Coalition` row, reused
standalone (the mp profile chip states it with no surrounding sentence)."""

NON_GOVERNMENT_EN = "Non-government"
NON_GOVERNMENT_MS = "Bukan kerajaan"
"""Substring of `NONGOVERNMENT_CLEAR_MS` above, reused standalone (the mp
profile chip has no "clear" to qualify)."""

MAJORITY_EN = "Majority"
MAJORITY_MS = "Majoriti"
"""From the settled `Majority 112` -> `Majoriti 112` row. Reused for both of
this codebase's two senses of the English word "majority" — the 112-seat
Majority threshold (`politikku_homepage`'s hemicycle label) and a single
Seat's GE15 winning majority (`politikku_mp_profile`'s stat caption) — since
BM does not distinguish the two any more than the English word does."""

GE16_EN = "GE16"
GE16_MS = "PRU16"
"""From the settled `GE16 Seat Projection` -> `Unjuran kerusi PRU16` row."""


def not_calibrated_tag(language: Language) -> str:
    """The `<span class="pk-tag-modelled">...</span>` tag, in whichever
    language — every page's own copy of this markup, unified here so the
    settled `NOT_CALIBRATED_MS` text can only ever be spelled one way.
    Trust rule 1 (`design_handoff_politikku/README.md`, "Trust rules") is
    unchanged by translation: this still only ever travels inline beside a
    modelled number, never as a banner — callers are responsible for that
    placement, same as before #81.
    """
    return (
        f'<span class="pk-tag-modelled">{t(language, NOT_CALIBRATED_EN, NOT_CALIBRATED_MS)}</span>'
    )
