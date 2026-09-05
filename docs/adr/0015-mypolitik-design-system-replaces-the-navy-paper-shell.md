# `mypolitik`'s design system replaces PolitikKu's navy/paper shell

> **Completes [ADR 0012](0012-mypolitik-frontend-supersedes-the-print-register.md).**
> ADR 0012 named `mypolitik`'s visual language the surviving frontend design
> system, but retired only one of the two design systems it beat. The print
> register (`docs/design/HANDOFF.md`) was retired explicitly; PolitikKu's
> navy/paper shell — built five days earlier from a different handoff — was
> never mentioned, and so stayed standing as apparently-live direction. This
> ADR retires it, on the same reasoning ADR 0012 already gave.

## Why

Three design systems existed in this repo at once. ADR 0012 settled which one
wins and closed out one loser. It did not close out the other, and the cost of
that omission came due.

The sequence:

| Date | Event |
| --- | --- |
| 2026-08-24 | `b491550` (#83) builds `politikku_shell.py`'s navy/paper tokens, self-hosted Newsreader/IBM Plex, header + trust strip + methodology footer, "matching `design_handoff_politikku`'s palette/type/spacing tables exactly" |
| 2026-08-29 | The `mypolitik` merge decision |
| 2026-09-04 | ADR 0012: `mypolitik`'s visual language is the surviving design system; `docs/design/HANDOFF.md`'s print register is retired |
| 2026-09-05 | ADR 0014: `/app/` becomes the site root |
| 2026-09-05 | `48d4384` (#148) restyles the map's own sidebar and topbar **into** navy/paper — 242 lines of `styles.css` |

ADR 0012 mentions `docs/design/HANDOFF.md` and
`docs/design/mypolitik-new-views-spec.md`. It does not mention
`design_handoff_politikku`, `politikku_shell.py`, or the navy/paper tokens
anywhere. A grep across every ADR confirms it: no ADR before this one names
that system at all.

So a session picking the repo up after ADR 0012 found two design references
that both read as current — `mypolitik-new-views-spec.md` (blessed by 0012)
and `design_handoff_politikku` (blessed by #83's commit message, unmentioned by
any ADR since). It reconciled the site's split identity by moving the map
toward the navy/paper shell. That is the exact opposite of what ADR 0012
decided, and nothing in the written record contradicted it at the time.

The reasoning that made ADR 0012 right has not changed and is not re-argued
here: rebuilding `mypolitik`'s working, already-interactive SPA — map, search,
live election mode, thousands of lines — into a design language written for a
handful of static pages is a large cost for no functional gain. The pull is in
the cheap direction: the static pages adopt the SPA's system.

What the omission additionally cost is measurable. `politikku_bills.py`,
`politikku_dewan.py` and `politikku_politicians.py` emit 75 CSS class names, of
which 71 are defined only in `frontend/public/styles.css` and none in
`politikku_shell.py` — they were written as fragments for the SPA to hydrate,
then promoted to standalone pages at `/bills/`, `/dewan/` and `/politicians/`
under a shell that could not style them. Those three pages have been serving
unstyled HTML in production. Two design systems that each believed they owned
the page chrome is how a page ends up owned by neither. See #149.

## Decision

**`mypolitik`'s design system is the site's only design system**, on every
surface: the map at `/`, and every server-rendered page under
`politikku_shell.py`.

**PolitikKu's navy/paper system is retired.** `#14203a` navy, `#fbfaf7` /
`#f4f2ec` paper, Newsreader and IBM Plex leave the codebase. The absence of
those five strings from `src/lpa/` and `frontend/public/` is the completion
test.

**`politikku_shell.py`'s `:root` keeps its semantic token names and changes
their values.** This is what makes the cutover cheap rather than a rewrite:
`politikku_projection.py` (102 `var()` references, zero raw hexes),
`politikku_sentiment.py` (54, zero) and `politikku_learn.py` (52, zero) are
already fully tokenised and recolour with no edits of their own. The token
table lives in #149, not duplicated here.

One token does not survive as a rename. `--ink` was doing two jobs in a light
system — primary text on paper, and the background of the navy bands. Those
roles separate on a dark ground and must be audited per use site, not
find-and-replaced.

**The map's sidebar and topbar become the chrome for every page.**
`render_header`, `render_trust_strip` and `render_methodology_footer` are
replaced. This is not only a visual decision: the site has been carrying two
navigation menus that disagree about what the site contains — `Politicians` and
`Dewan` unreachable from any static page, `Methodology` and the three Learn
pages unreachable from the homepage. One chrome makes one nav, and the
disagreement cannot recur.

**`48d4384` (#148) is reverted.** It was a good-faith reading of a record this
ADR is fixing, not a mistake to be attributed to whoever made it.

**`design_handoff_politikku` is retired as a *visual* reference and kept as a
*content* reference.** What a bill card carries, what an MP profile shows, the
FACT/MODEL trust distinction, the postcode-ambiguity states — that work stands
and is not re-derived. Its colours, typography and spacing tables do not apply.
Its README's own framing supports the split: it describes itself as "a design
reference created in HTML… not production code to copy."

## What this does not do

It does not delete or retroactively invalidate `design_handoff_politikku`, any
more than ADR 0012 deleted `HANDOFF.md`. Both remain the record of real,
considered design passes. It does not promote `mypolitik`'s CSS to
"do-not-relitigate" status — ADR 0012 declined to do that and this ADR
inherits the refusal.

It does not touch the map canvas itself: seat colours, projection rendering,
interaction. Only the chrome around it.

It does not build the lookup-first homepage from `design_handoff_politikku`
(postcode search, "Find your MP"), and it does not close ADR 0014's Audience
gap. Both remain open and unscheduled. Retiring that handoff's *visual*
direction does not retire the reader it was built for.

It does not deduplicate the page primitives that now exist in both
`frontend/public/styles.css` and `politikku_shell.py`. That duplication is
deliberate and temporary — the SPA still uses its copies — and is a later
cleanup, not a condition of this decision.

## Consequence

**Typography regresses a decision unless it is fixed in the same push.**
`b491550` self-hosted Newsreader and IBM Plex as four `woff2` files
(~133 KB in `public/fonts/`) rather than using Google's CDN, citing the
handoff's Malaysian-mobile-data callout. `frontend/public/index.html:22–24`
loads Space Grotesk and JetBrains Mono from `fonts.googleapis.com` with two
`preconnect`s — a render-blocking third-party request on every page. Space
Grotesk is *already* self-hosted in `frontend/public/fonts/` and declared at
`styles.css:449`, so that CDN link is partly redundant today. Adopting
`mypolitik`'s typography site-wide therefore means: self-host JetBrains Mono,
drop the Google Fonts link and both preconnects, and delete the four now-unused
Newsreader/IBM Plex files. Doing so keeps `b491550`'s reasoning intact and
removes a render-blocking dependency the current Lighthouse run already flags
(`network-dependency-tree-insight: 0`, `document-latency-insight: 0.5`). Not
doing so silently trades a considered decision for an unconsidered one.

**The stale pointers are in code, not in the domain docs.** `CONTEXT.md` names
no design system at all, and ADR 0014's only mention of removing tokens from
`politikku_shell.py` refers to the print register's, not these — both are
accurate as written and need no edit. What does mislead is
`politikku_shell.py` itself: its module docstring (line 24, "Every value below
is taken from `design_handoff_politikku/README.md`") and its `:root` comment
(line 721, "Design tokens — `design_handoff_politikku/README.md`"). Those two
lines are the entire live blessing that handoff has, and they sit in the file
being rewritten, so they are corrected as part of the same work.

`politikku_i18n.py`'s three references to the same handoff (lines 8, 38, 116)
**stay**, and must not be swept up by a grep. They cite its BM translation
table and its trust rules — content, which this ADR explicitly keeps — not its
palette or type.

**A single dark palette is now the accessibility baseline for the whole site.**
The SPA's `--ink-faint` `#5d6b7d` scores 3.56:1 on `--bg` — below AA for body
text, and the existing Lighthouse `color-contrast` failure. It stays available
for large text and decorative rules; small text on a server-rendered page uses
`#708096`, the nearest value on the same hue clearing 4.5:1 on all three
surfaces. Measurements are in #149.

**Anyone reconciling this site's visual identity in future should read this ADR
and ADR 0012 together.** The direction is settled twice over; a third session
finding two design references and picking the wrong one is the specific failure
this ADR exists to prevent. If a design reference in this repo is not named as
live by an ADR, it is not live.
