# Landing page design spec (superseded)

> The `codex/observatory-landing` branch replaces this earlier bento-style
> landing-page design with the Observatory build in
> `scrollcraft/builds/observatory/`. This document remains as the design
> record for the previous landing page and its routing decisions.

Settled requirements for the landing page at `politikku.my/`, reached
through a full requirements-grilling session (routing, audience,
above/below-the-fold content, bilingual scope, and mobile constraints each
explicitly decided, not assumed — see the implementation plan for the full
decision trail). This document is the design contract; it does not
prescribe HTML/CSS. Implementation plan: `politikku-landing-plan` (kept
separately, not checked in — ask if you need the routing/`daily.yml`/test
detail this spec doesn't cover).

**Supersedes ADR 0014's root-routing decision** — a new ADR (0017) records
that formally; this spec covers the page's design, not the routing change.

## Audience & user goal

**Reader**: a general, undifferentiated first-time visitor. Not
specifically `Audience` (CONTEXT.md's secondhand-discovery,
not-politically-engaged reader — ADR 0014's still-unscheduled gap) and not
specifically `Engaged Reader` either — this page makes no assumption about
*how* someone arrived (search, a link, word of mouth, a shared Seat Call
card) or what they already know.

**The one thing this page must not assume**: that the reader knows what a
Seat, a Coalition, or a Majority is. CONTEXT.md's own `## Language` section
exists because these terms are not self-explanatory even to Malaysians who
follow politics casually — a first-time visitor gets no floor of assumed
vocabulary.

**User goal, in order of priority**:
1. Understand in under five seconds what this site is (a live, tracked
   projection of Malaysia's next election — not a poll aggregator, not a
   news outlet, not an opinion source).
2. See one concrete, current fact (the majority call) that proves the site
   is live and real, not a mockup or a stale demo.
3. Either go deeper immediately (the CTA into the interactive map) or
   orient further first (the glossary, the other views) before committing.

**What this page is explicitly not**: a marketing/conversion funnel in the
SaaS sense. There is no signup, no account, no email capture (CONTEXT.md's
`Return Trigger` entry is explicit that this site has no accounts and no
push — retention means "easy to return to," not a captured lead). Every
design decision below should be checked against that: does this element
help someone understand and enter the site, or does it exist to make the
page *feel* like a product landing page. The latter loses.

## Visual register & typography rules

**Register**: civic-data publication, not tech SaaS, not print-register
civic-formal. The closest real-world analogue is a well-designed live
election-night broadcast graphics package — dense, confident, quietly
serious, built to be trusted under scrutiny — not a startup's pricing
page.

**Design system**: this page uses `mypolitik`'s dark design system
exclusively (ADR 0015) — the *only* live visual language on this site.
There is no second design system to draw from. `design_handoff_politikku`
(navy `#14203a` / paper `#fbfaf7`, Newsreader/IBM Plex) is retired as a
visual reference and must not appear here in any form, including as an
"accent" or a light-mode variant — ADR 0015 retired it specifically
because two design systems coexisting silently broke three production
pages. Do not reintroduce a second one, even partially, even for this one
page.

**Color tokens** (`politikku_shell.py`'s `:root`, already live in
production — reuse verbatim, do not invent new hex values):

| Token | Value | Use |
|---|---|---|
| `--paper` | `#0b0e13` | Page background |
| `--paper-alt` | `#11151d` | Card/tile surface (`.bento-tile`) |
| `--ink` | `#e7edf4` | Primary text |
| `--ink-secondary` | `#93a1b3` | Secondary text |
| `--muted` | `#708096` | Tertiary/label text — the accessibility-audited AA replacement for `--ink-faint`, use this for any small text, never a lighter/dimmer improvisation |
| `--line` / `--line-soft` / `--line-strong` | `#1d2733` / `#161e28` / `#2a3645` | Borders, hairlines |
| `--accent` | `#4dd6c1` (teal) | Links, focus rings, the CTA, active-state rules |
| `--caution` | `#ffd166` (amber) | The NOT CALIBRATED / BELUM DITENTUKUR pill — reserved for that meaning, do not reuse amber decoratively elsewhere on this page |

**Typography** (already self-hosted, `@font-face` rules in
`politikku_shell.py`):
- **Space Grotesk** (`--sans`) — all UI text and body copy, including the
  glossary primer and link-tile descriptions.
- **Redaction 20** (`--font-display`) — headings only (`h1`, `h2`, hero
  headline, section headings). Never body copy, never the majority-call
  sentence itself (that is UI/data, not editorial prose — sans, not
  serif).
- **JetBrains Mono** (`--mono`) — any number or data value. The seat
  count, percentages, dates. The majority-call sentence's prose wrapper is
  sans; a bare number inside it (if one appears) is mono. This split is
  already established sitewide (`mypolitik-new-views-spec.md`'s own
  typography rule) — this page must not be the exception.
- Hero headline size: `--text-hero-desktop` (58px) / `--text-hero-mobile`
  (38px) — reuse the existing scale tokens, don't set a new size.
- No third typeface, no italic display serif, no letter-spaced
  all-caps hero headline (a common SaaS-landing tell — see Anti-Patterns).

**Radius & surface language**: `--radius-sm/md/lg` (3/4/5px) for controls
and buttons; 12–16px for card-level surfaces (`.bento-tile` uses 16px).
Nothing on this page should introduce a new radius value.

## Component breakdown

> **Revised after the first build.** The page as originally specced —
> headline, one majority sentence, three text link-tiles — read as an
> empty dashboard tab rather than a way into the site. The revision below
> replaces the single stat with real data anchors and makes the Seat
> lookup the primary action. The sections it supersedes are noted inline
> so the change is legible rather than silently rewritten.

### Shell: no app chrome

> **The landing page shows on every visit to `/`.** An earlier revision
> skipped it for returning visitors via a `localStorage` flag; that is
> removed (ADR 0017's revision note). The only client-side redirect left
> forwards a `/#<hash>` deep link to `/app/#<hash>`. Do not add a "seen"
> flag back without reading that note.

`render_shell(chrome=False)`. The sidebar and topbar are the *app's*
internal navigation; a first-time visitor has not entered the app yet, and
framing the landing page inside them is most of what made the first build read as
a dashboard tab. The page renders full-width with its own slim header —
wordmark and language toggle, nothing else.

Everything else still comes from the shell: the head (canonical, hreflang,
OG, JSON-LD), the design tokens, the methodology footer, and the lookup
bundle. `chrome=False` is a layout opt-out, not licence to fork a second
design system (ADR 0015).

### Hero

- **Kicker** (`.bento-kicker`: 10.5px, uppercase, `--muted`,
  letter-spacing) — one short line naming what the site does, not a
  tagline aiming for cleverness.
- **Headline** — one sentence, plain, no wordplay, no question-as-headline
  ("Ready to see the future of Malaysian politics?" is exactly the register
  to avoid). States what the tool is.
- **Deck** — one sentence of orientation under it, `--ink-secondary`,
  capped near 46ch. Says what is projected and from what.
- **Seat lookup — the primary action.** A labelled postcode/constituency
  field, a Search button, and "Use my location". Server-rendered markup
  only: behaviour is `public/lookup.js`'s, and this page renders the
  `data-pk-lookup-scope` / `-form` / `-input` / `data-pk-locate` /
  `-results` contract `ts/src/dom.ts` mounts onto. Do not invent a
  parallel implementation. The results area is the one part of this page
  Python never renders — style what `dom.ts` emits, don't pre-render it.
  - The hint under the field must say a postcode can straddle two Seats
    (ADR 0008). The index is genuinely many-to-one and the UI shows every
    candidate; promising one answer would be a lie about the data.
- **Map link** — a text link, not a second filled button. The lookup is
  the primary action; two competing filled CTAs above the fold is the
  anti-pattern below.

The wordmark moved to the page header and is no longer a hero element.

No hero illustration, no abstract gradient mesh, no photo.

### The Majority bar

One stacked bar across the full content width, every Coalition a segment,
Government Coalitions first and each side ordered by Seats descending —
the single safest-Government-to-safest-Non-government axis `CONTEXT.md`'s
`Non-government` entry describes. On the bar itself: a marker at the
Majority threshold, labelled. Under it: the two side totals in mono, and a
swatch legend.

- **Coalition colours are read from `frontend/public/lib.js`**
  (`politikku_politicians.load_coalition_colors()`), never restated. A
  second colour table is how this page and the map end up disagreeing
  about what colour PH is.
- **Government membership is read from `data/coalitions.json`**, same
  reason — a realignment must not need a code change here.
- The majority-call sentence sits above the bar with the **NOT
  CALIBRATED** / **BELUM DITENTUKUR** tag inline (`.pk-not-calibrated`,
  amber `--caution`) — never a page-level banner, per the FACT/MODEL rule.
- The threshold marker must not be clipped. Put `overflow: hidden` on an
  inner track, not on the bar that carries the marker and its label.

### Data preview panels

Two `.bento-tile` panels, replacing the three generic text link-tiles the
first build had:

1. **Seat projection** — the five Coalitions `CONTEXT.md` names as the
   ones that matter (PH, BN, PN, GPS, GRS), each a swatch, code, a bar
   proportional to the largest, and the count in mono. Carries the NOT
   CALIBRATED tag: every figure is modelled.
2. **Bill tracker** — the two most recent Bills by stage date, with
   Parliament's own `stage` label verbatim in a `.pill` (ADR 0010 — never
   an invented English gloss), the code and date in mono. Carries **no**
   tag: this is Parliament's own register, factual. Tagging it would be as
   wrong as leaving the projection untagged.

Both use `politikku_bills.bill_stage_style` for the stage pill, so the
teaser and `/bills/` cannot colour the same stage differently.

**Sentiment gets no panel**, only a link. There is no sentiment export to
build one from — the figures reach the SPA through `politikku_sentiment.py`
and Storage only (`mypolitik-new-views-spec.md` names this gap). A third
panel faked from nothing would be exactly the vanity metric the
anti-patterns forbid. When the export exists, it earns a panel.

A plain link row under the panels carries Sentiment, Dewan and
Politicians — the destinations that do not warrant a panel still have to
be reachable.

### Every section falls back independently

Each section renders only if its own data read succeeded, and renders
nothing at all otherwise. A day when `public_export` fails costs the
Majority bar and the projection panel — not the Bills panel, the Seat
lookup, the glossary, or the page. No section may render an apology, an
"unavailable", or a visibly empty frame; a first-time visitor must not be
able to tell a fallback is a fallback. With no Seat totals the
majority-call sentence survives on its own in a plain tile.

### Glossary primer

Unchanged from the first build. Seat / Coalition / Majority / Projection,
each with one plain-language sentence from `CONTEXT.md`'s own definitions,
in `.rows` (the ruled two-column pattern) — not four more tiles, which
would read as a feature grid rather than reference material.

English definitions carry `politikku_learn.py`'s `data-claim`/`data-cite`
attributes pointing at CONTEXT.md. **The Malay ones do not**: a
translation is not a verbatim claim against an English source, and
`lpa.citation_check` could only ever fail one. The citation follows the
claim it can actually verify.

### Footer

Reuse `politikku_shell.py`'s existing methodology footer verbatim — do not
design a new footer for this page alone. A visitor's first and fifth page
should feel like the same site.

## Layout grid & spacing constraints (375px → 1440px)

**No fixed 1440px container** — this site does not use a fluid full-bleed
layout at large widths. Existing pages cap content at `max-width: 1100px`
(wider sections) or `900px` (narrower reading content), centered with
`margin: 0 auto`. This page should pick one of those two, not a new value
— recommend **1100px** for the hero/link-tiles row (matches width-bearing
content elsewhere) and it's fine for the glossary `.rows` block to sit
inside the same 1100px column rather than narrowing further.

**Gutters**: `--gutter-desktop` (30px) / `--gutter-mobile` (18px) — reuse
these tokens for the page's outer horizontal padding, don't invent new
ones.

**Spacing scale**: `--space-unit` = 4px base. All vertical rhythm
(gaps between hero elements, section spacing) should be multiples of 4px,
matching the rest of the shell's spacing.

**Breakpoint**: `640px` is this shell's real structural breakpoint (sidebar
appears/disappears, topbar layout changes) — treat it as the primary
mobile/desktop split for this page too, rather than introducing a new one.
Secondary narrower breakpoints already exist in the CSS at `380px`/`430px`
for fine-tuning small-phone text sizing if the hero headline needs it —
use those rather than picking arbitrary new pixel values.

**375px hard constraint** (settled decision, non-negotiable): the **Seat
lookup** — its label, field, and Search button — must be visible with
**zero scrolling** on a 375×667 viewport (iPhone SE, the narrowest
viewport worth designing for explicitly). It is the page's primary action,
so it is what the constraint protects.

*Superseded:* the first build's version of this rule protected the
majority-call tile and the CTA. Once the lookup entered the hero, all
three could not fit together, and the lookup wins — the Majority bar sits
immediately below the fold, which is the right place for the thing a
reader scrolls to rather than acts on.

If kicker + headline + deck + lookup don't fit at that height, the
headline is what shrinks first (the existing 380px breakpoint steps it to
32px) — never the lookup's tap targets. The field and both buttons are
48px, above the 44px sitewide minimum (`.top-controls .seg.chip button`).
At ≤380px the buttons go full-width on their own row rather than
squeezing the field below a usable size.

**Below-the-fold layout at 375px**: the two data panels stack
single-column, full gutter width. Glossary rows stack full-width, no
forced two-column squeeze. The Majority bar keeps all its segments at
every width — it is one axis, and dropping minor Coalitions from it on
mobile would change what the graphic claims.

**At 1440px**: content column stays at 1100px max-width, centered — the
extra ~340px of viewport becomes side whitespace (`--paper` background),
not stretched content. With no sidebar (`chrome=False`) the column is
genuinely centred in the viewport rather than offset by 232px.

**Between 640px and 1100px** (tablet/laptop): the two data panels go
side-by-side via `repeat(auto-fit, minmax(320px, 1fr))`, which finds the
transition on its own rather than having a breakpoint guessed for it.

## Forbidden clichés / anti-patterns

Concrete, not generic — each of these is a specific trope to actively
design against, not a vague "keep it clean" note:

- **No gradient-mesh or abstract-blob hero background.** This is not a
  startup announcing a product; a dark solid `--paper` background with
  real typographic hierarchy carries more authority here than a decorative
  gradient would.
- **No stock photography or illustration of people** ("diverse group
  pointing at a laptop," a generic Parliament-building stock photo). If an
  image is ever warranted here, it is a real data visualization — nothing
  else.
- **No question-as-headline** ("Curious who'll win GE16?"). States, does
  not ask.
- **No countdown timer, no urgency language** ("Don't miss the latest
  update!") — this site has no scarcity and manufacturing any is
  dishonest to what it actually is (CONTEXT.md's own `Return Trigger`
  entry explicitly rejects "habit loop" framing).
- **No testimonials, no "as seen in" logo strip, no fake social proof.**
  Nothing here has been said about this project by anyone whose quote
  would belong on a landing page, and inventing the feeling of that is
  worse than omitting it.
- **No vanity-metric counters** ("X seats tracked," "Y articles analyzed
  today"). Every figure on this page must be a real tracked value a reader
  can go verify on the page it comes from — the Coalition Seat totals, the
  Majority threshold, a Bill's stage date. A number that exists to look
  impressive rather than to inform is the thing being banned, not numbers.
  *(The first build's version of this rule scoped the page to exactly one
  number. That is what made it read as empty; the test is provenance, not
  count.)*
- **No auto-advancing carousel or slideshow** for the below-fold sections.
  Two panels and a glossary fit in one static stack; a carousel exists to
  hide content that didn't fit, and everything here fits.

- **No interactive control that does nothing.** The Seat lookup works
  against a real index or it does not ship. `ts/src/dom.ts` deliberately
  omits the mock's "narrow down by street name" field for exactly this
  reason — this pilot has no street-level data, and a field that quietly
  does nothing claims a capability that does not exist.
- **No letter-spaced all-caps hero headline** — that register belongs to
  the small uppercase kickers/labels this system already uses (`.bento-
  kicker`), not to the primary headline; using it for both flattens the
  hierarchy.
- **No reintroducing any navy/paper (`#14203a`/`#fbfaf7`) value, Newsreader,
  or IBM Plex, anywhere, even as a single accent.** ADR 0015 exists
  because exactly this kind of one-off reintroduction, done in good faith
  on a single page, silently forked the site's design language before.
- **No second filled button competing with the primary action above the
  fold.** The Seat lookup's Search button is the only filled `--accent`
  control in the hero. "Use my location" is a bordered secondary; the map
  link is a text link. Nothing else in the hero may be a filled button.
- **No apologetic or hedging language around the fallback state**
  ("Sorry, live data isn't available right now"). The static fallback
  copy is written as if it were the primary content, not an
  error message in disguise — see Component Breakdown's hero section.
