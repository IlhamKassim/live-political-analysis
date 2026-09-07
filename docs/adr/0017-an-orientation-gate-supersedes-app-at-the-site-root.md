# A landing page supersedes `/app/` at the site root

> **Revised 2026-09-07, the day this ADR shipped.** As first written this
> was an orientation *gate*: shown once, then skipped for returning
> visitors via a `pk-landing-seen` flag. That skip is removed — the landing
> page is the site's front door and shows on every visit to `/`. The
> sections it changed are marked inline rather than rewritten away, because
> the reasoning it replaced is the reasoning a future reader is most likely
> to want to re-open. Amended in place rather than superseded by an ADR
> 0018: this decision is hours old and never lived with, and two ADRs
> disagreeing about the same week would read worse than one that shows its
> own correction.

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

**~~A repeat visitor never sees the gate twice.~~ Every visit to `/` shows
the landing page.** *(Revised — see the note under the title.)* The original
decision was a `pk-landing-seen` flag in `localStorage`, set on load, that
`location.replace`d a returning visitor straight to `/app/`. It was offered
as the direct answer to "doesn't this just re-add the friction ADR 0014
removed".

It was removed for two reasons. The smaller one is that it cost a second
piece of client state to keep in step, and got that wrong on the first
attempt: the flag hijacked the language toggle, sending a reader who clicked
BM to the map instead of the Malay page, and needed a
`pk-landing-lang-switch` marker to counteract it. The larger one is that the
friction it was avoiding is a click, and the thing it was skipping is now a
working Seat lookup and live projection and Parliament data — a page worth
landing on rather than one to get past. A front door that hides itself from
everyone who has been here before is not a front door.

The honest consequence, stated plainly rather than argued away: **ADR 0014's
concern is now real and unmitigated.** An Engaged Reader going to
`politikku.my` gets the landing page every time and clicks once more to
reach the map. If that proves to be the wrong trade, the fix is a
preference the reader sets deliberately — not a flag set behind their back
on their first visit.

**Any `/` visit carrying a fragment forwards to `/app/<hash>` immediately**,
before the language check. Every existing SPA deep link was a root URL until
now; this is what keeps them working, and it is the only client-side
redirect the landing page still performs.

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

**~~The wordmark, the "Map" nav item, and the footer's "What is PolitikKu?"
link on every other page now land on the landing page.~~ Done — in-site
navigation goes to the map.** *(Revised, same day.)*

Removing the skip turned what had been a `location.replace` hop through to
`/app/` into a stop: anyone on a content page who clicked the wordmark
expecting the map got the landing page instead. The wordmark's own
accessible name is "Show the whole map", so it had stopped doing what it
said.

Fixed by pointing at `APP_URL` the things that mean *the map* — `NAV_LINKS`'
`map` entry, and the three brand links (`sb-brand`, `brand-home`,
`topbar-title`) — and by moving `home.html`'s redirect stub with them, since
its own comment already said the map view was its closest equivalent.

**`landing_url()` deliberately did NOT move**, contrary to what an earlier
draft of this note proposed. It backs the footer's "What is PolitikKu?"
link, and the landing page is the answer to that question. `/` is the
landing page and `/app/` is the map; they were the same URL before this ADR,
which is why so much of `politikku_shell.py` still reads as though "home"
and "the map" are one place. `APP_URL` now lives beside `LANDING_URL` in
that module so the distinction is stated once.

Net effect: a cold arrival at `politikku.my` gets the landing page; every
click inside the site that means "the map" goes straight to it.

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
