# An orientation gate supersedes `/app/` at the site root

> **Supersedes [ADR 0014](0014-app-becomes-the-site-root-audience-loses-its-page.md)'s
> root-routing decision.** ADR 0014 put the `mypolitik` SPA at `/` so a
> visitor got the interactive tool immediately rather than through a
> secondary path. That is reversed here: `/` becomes a server-rendered
> orientation page, and the SPA moves to `/app/`. Everything else ADR 0014
> decided — the four retired renderers, the old-URL redirect stubs, the
> untouched `/projection/` detail page, the unchanged Seat Call card
> links — stands unchanged.

## Why

ADR 0014's own "Consequence" section names the cost it accepted: PolitikKu's
homepage was the general on-ramp, and putting the SPA at the root removed it.
A visitor arriving cold at `politikku.my` landed in a map built for
`Engaged Reader`, with no statement of what the site is and no floor of
assumed vocabulary — `CONTEXT.md`'s `## Language` section exists precisely
because Seat, Coalition and Majority are not self-explanatory.

That gap was accepted on the reasoning that closing it meant building
`Audience`'s postcode lookup, which was and remains unscheduled. That
reasoning contained an error worth naming, because it is what kept the gap
open for as long as it stayed open: the postcode lookup was already built
(#74/#77, ADR 0008, `ts/src/` shipping on every page). What ADR 0014 removed
was its last *surface*, not the capability. Restoring a surface is a much
smaller piece of work than building the thing, and it is most of what this
ADR does.

What a first-time visitor needs is a plain sentence saying what this is,
something concrete proving it is live rather than a mockup, and a way in
that starts from something they already know about themselves — their own
postcode.

The cost ADR 0014 was avoiding — a second click between the visitor and the
tool — is real, and is why this is a *gate*, not a homepage: it is shown
once. See the mechanisms in the Decision below.

### A drift found on the way in

`daily.yml`'s fold-in step carried a comment claiming it copied
`frontend/public/` to **both** `public/` and `public/app/`. The `run:` block
underneath it only ever had the one `cp` to `public/`. `/app/` has never been
a real path on this site; ADR 0014's and `CONTEXT.md`'s references to it are
shorthand for "`frontend/`'s content, now at `/`", which
`politikku_redirects.py`'s own docstring states correctly. The sitemap
ordering comment immediately below already anticipates `public/app/index.html`
existing — evidence this migration was planned once and left half-done.

This ADR is not the cause of that drift, and fixes it as a side effect: it is
recorded here so a future reader does not mistake the corrected step for new
breakage.

## Decision

**`/` and `/ms/` are rendered by `lpa.politikku_landing`, a server-rendered
shell page.** Design contract: `docs/design/landing-page-spec.md`. Above the
fold: a kicker, one plain headline, a one-sentence deck, and the **Seat
lookup** as the primary action. Below: the Majority bar, a Seat-projection
panel and a Bill-tracker panel, and a four-term glossary primer quoting
`CONTEXT.md`. Every modelled figure carries the `NOT CALIBRATED` /
`BELUM DITENTUKUR` tag inline; the Bills panel, being Parliament's own
record, carries none.

**The page renders outside the app's chrome** — `render_shell(chrome=False)`,
no sidebar, no topbar, its own slim header instead. A visitor who has not
entered the app should not be framed by the app's internal navigation; with
it the gate reads as an empty dashboard tab rather than a way in. The head,
the design tokens and the methodology footer still come from `render_shell`,
so this is a layout opt-out and not a second design system (ADR 0015).

**The Seat lookup is the existing one, surfaced — not a new one.**
`public/lookup.js` (built from `ts/src/`) already ships on every page and
already fetches `public/data/lookup-index.json`; this page renders the
`data-pk-lookup-*` markup contract `ts/src/dom.ts` mounts onto and nothing
more. See "What this does not do" for what that does and does not settle.

**`/app/` becomes a real path for the first time**, and is the fold-in step's
only target. `public/fonts/` gets its own explicit copy in the same step: the
shell's six `@font-face` rules are used by *every* server-rendered page and
reached `public/fonts/` only as a side effect of the old wholesale root copy.
Retargeting without that second copy would have 404'd them site-wide, silently
— pages still render, just with fallback typography. The smoke-check now
asserts a font file, since no test exercises the fold-in.

**A repeat visitor never sees the gate twice.** An inline head script, running
before first paint, sets `pk-landing-seen` in `localStorage` on gate *load*
and `location.replace`s straight to `/app/` on any later bare visit. This is
the direct answer to "doesn't this just re-add the friction ADR 0014 removed":
the second visit onward costs nothing.

**Any `/` visit carrying a fragment forwards to `/app/<hash>` immediately**,
before the language check and regardless of `pk-landing-seen`. Every existing
SPA deep link was a root URL until now; this is what keeps them working.

**Every figure is baked in at build time** — `public/projection.json` for
the Seat totals, `frontend/public/data/bills.json` for the Bills — read
during the render, not fetched in the browser. That removes a first-paint
fetch race from the one page a first-time visitor sees first, and makes the
fallbacks free: **each section renders only if its own data read succeeded,
and renders nothing at all otherwise.** A failed export costs the Majority
bar and the projection panel, not the Bills panel, the Seat lookup, the
glossary, or the page. No section renders an error state, a "data
unavailable", or a visibly empty frame — a visitor must not be able to
identify a fallback as one.

**Coalition colours and Government membership are read, never restated** —
colours from `frontend/public/lib.js` (the table the SPA draws the map
with), membership from `data/coalitions.json`. A second copy in the
rendering layer is how this page and the map end up disagreeing about what
colour PH is, or about who is in government after a realignment.

**Both languages, from the start**, on the same `Language`/`t()`/`/ms/`
route/hreflang machinery as every other shell page. `/ms/` is a real page for
the first time.

**Seat Call card links are unchanged.** `telegram_post.py`'s `SITE_URL` still
points at the root, so a card click lands on the gate like any other
first-time visit — the same deliberate choice ADR 0014 made, re-affirmed here
now that the root's content has changed.

## What this does not do

It does not **build** postcode lookup — that shipped long before this ADR
(#74/#77, ADR 0008) and merely lost its last surface when ADR 0014 retired
the page that hosted it. This ADR gives it one again.

That closes the specific mechanical loss ADR 0014 named — "a card click now
lands Audience on Engaged-Reader content with no postcode lookup" is no
longer true, and `CONTEXT.md`'s `Audience` entry is corrected in the same
change. **It does not close the `Audience` gap itself.** That gap is about
the secondhand-discovery, not-politically-engaged reader as a whole, and its
remaining work — #22's site-literacy content and #23's shareable cards — is
still unscheduled. This page is built for a general, undifferentiated
first-time visitor and assumes nothing about how they arrived; that a
postcode field now exists on it is a by-product, not the Audience answer. A
future reader must not conclude from this ADR that the `Audience` question
is settled.

It does not add a Sentiment data panel. There is no sentiment export to
build one from (`mypolitik-new-views-spec.md`'s own View 3 prerequisite);
Sentiment stays a link until one exists, rather than a panel faked from
nothing.

It does not change `/app/`'s content, routing, or view model — only the path
it is served from. It does not add a `NAV_LINKS` entry: `landing_url()`
already resolves to `/`, and is already wired into the wordmark and the
methodology footer on every page. It does not introduce a second design
system: the page is built entirely from `politikku_shell.py`'s existing
tokens (ADR 0015). The components it does add — a filled primary button, the
Majority bar, and CSS for the states `ts/src/dom.ts` renders — had no
precedent in the shell because the pages that used to carry them were
retired by ADR 0014 along with their CSS.

## Consequence

**The wordmark, the "Map" nav item, and the footer's "What is PolitikKu?"
link on every other page now transit the gate.** All three point at `/`. For a
repeat visitor that is one `location.replace` hop to `/app/` rather than a
direct landing. This is inherent to putting a gate at the root, not a bug, and
is named here so a reviewer does not have to rediscover it. If the hop ever
proves to be worth removing, the fix is to repoint `NAV_LINKS`' `map` entry
and `landing_url()` at `/app/` — a deliberate, separate change.

**`public/data/` is no longer populated by the fold-in.** The frontend's data
files now land at `public/app/data/`, which is where the SPA fetches them from
(every fetch in `app.js` is relative). `public/data/lookup-index.json` is
unaffected — its own render step writes it, and `ts/src/index-data.ts` fetches
it by absolute path.

**`tests/test_politikku_site_links.py`'s exclusion of `/` and `/ms/` is no
longer true.** Its docstring excluded them because "nothing renders them to
check". Something does now, and the sweep covers them.

**A latent BM 404 in `ts/src/dom.ts` became reachable and is fixed here.**
The lookup's no-match state offered "Browse all 222 Seats" at
`/projection/ms/` in BM; the real path is `/ms/projection/` (`_ms_route`
puts the ms segment first). Harmless while the only lookup lived on a
retired page — a real broken link the moment one sits on the site root.

**`politikku_bills._bill_stage_style` is now public** as
`bill_stage_style`, because the Bills panel renders the same stage pills.
One function means the teaser and `/bills/` cannot colour a stage
differently.

Anyone reversing this decision should reverse it whole: putting the SPA back
at the root means restoring the wholesale `cp` *and* keeping the explicit
fonts copy, or the font 404 described above returns.
