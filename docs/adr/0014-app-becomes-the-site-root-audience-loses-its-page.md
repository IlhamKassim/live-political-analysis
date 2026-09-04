# `/app/` becomes the site root; Audience loses its dedicated page

> **Amends [ADR 0012](0012-mypolitik-frontend-supersedes-the-print-register.md)** (which
> superseded the print register's visual language but explicitly left the
> `/app/` vs. site-root question as a separate, later decision) and
> **redefines the `Engaged Reader`/`Audience` split in `CONTEXT.md`**. This
> is not a visual-language change like ADR 0012 — it changes who the site's
> root page is actually for.

## Why

Once Step 4's new frontend views (seat projection, bill tracker, sentiment
digest) were built and verified in `/app/`, the maintainer wanted
`politikku.my/` itself to serve `/app/` instead of the old
`politikku_landing.py`-rendered page, so visitors get the merged
interactive site immediately rather than a secondary path.

A domain-modeling pass surfaced a real conflict before this shipped:
`CONTEXT.md`'s own glossary names two distinct readers. `Audience`
("younger Malaysians who first encounter this project's content
secondhand... not already politically engaged") is explicitly the group
`politikku_landing.py` was built for — the postcode lookup is that group's
on-ramp. `Engaged Reader` ("a reader who already follows Malaysian
politics... comes to this site by deliberate navigation") is `/app/`'s
actual fit: seat-code/name search, coalition jargon, a hemicycle chart —
nothing built for someone who doesn't already know political vocabulary.

Checking the code (not just the docs) surfaced the sharper version of this:
`telegram_post.py`'s `SITE_URL = "https://politikku.my/"` is exactly what
the automated Seat Call cards (#40) link back to — Audience's actual,
currently-running discovery channel. Swapping the root without addressing
this doesn't just leave Audience unserved in the abstract; it actively
routes the one channel built for Audience into content that no longer fits
them.

## Decision

**`/app/` becomes `politikku.my`'s root.** `politikku_landing.py`,
`politikku_homepage.py`, `politikku_bills.py`, and `politikku_mp_profile.py`
are retired together, not staggered one-at-a-time as the original Step 4
plan intended — that staggering existed to make sure a replacement existed
and was verified before a page was cut, and by this point all four have
real, verified `/app/` equivalents (bills tracker, sentiment digest,
projection, and the richer Politicians directory respectively).

**Old page URLs (`bills.html`, `home.html`, `mp/*.html`, and whatever
`politikku_landing.py` wrote) redirect to their `/app/#...` equivalents**,
so existing bookmarks, backlinks, and Google's already-indexed results
don't just 404.

**The old print-register design is deleted outright, not just
superseded.** ADR 0012 already retired it as the active direction; this
goes further and removes the design tokens/CSS in `politikku_shell.py`,
`docs/design/HANDOFF.md`, and any other trace of it, since nothing will
render it going forward.

**Seat Call cards keep linking to the new root, unchanged**, a deliberate
choice made with the consequence above already known — not an oversight.

**`Audience` currently has no dedicated served surface.** This is named
directly, not implied: postcode lookup does not exist in `/app/`, and
building it is explicitly future work, not part of this decision.
`CONTEXT.md`'s `Audience` and `Engaged Reader` entries are updated in the
same change as this ADR to state this plainly.

## What this does not do

It does not delete the underlying data or logic those four Python modules
read from (`page_model()`, `SentimentPageModel`, `data/bills.json`,
`data/mp_profiles.json` all stay exactly as load-bearing as before — only
the rendering/routing layer for the old pages is retired). It does not
change `/projection/`, which still serves Engaged Reader on its own
detail-page path per ADR 0011, untouched by this decision. It does not
build postcode lookup into `/app/` — that is a real, separate, currently
unscheduled piece of work, not something this ADR claims to have solved.

## Consequence

Anyone building the Audience-facing postcode-lookup work later should read
this ADR first: the gap it leaves is deliberate and already reasoned
through, not a bug to "discover" and quietly patch around. `CONTEXT.md`'s
`Audience`/`Engaged Reader` entries carry a pointer back to this ADR for
the same reason.
