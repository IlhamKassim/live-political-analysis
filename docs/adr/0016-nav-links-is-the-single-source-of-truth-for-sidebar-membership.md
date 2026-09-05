# `NAV_LINKS` is the single source of truth for sidebar membership

## Why

The site has two sidebar renderers. `src/lpa/politikku_shell.py` renders the
navigation for content pages from its `NAV_LINKS` tuple, while
`frontend/public/index.html` contains hand-written navigation for the
interactive map SPA. They serve the same site, but nothing previously checked
that they offered the same destinations.

That gap produced a concrete bug. `NAV_LINKS` grew to ten entries while the
SPA sidebar remained at six. As a result, four of ten destinations —
`methodology`, `glossary`, `coalitions`, and `process` — were completely
unreachable from the map homepage. Both renderers continued to work in
isolation, so no existing test exposed the disagreement.

## Decision

**`NAV_LINKS` in `politikku_shell.py` is the single source of truth for which
navigation destinations exist across the site.** Both sidebars retain their
independently-written markup, but their destination-key sets must agree.

The contract test
`test_the_spa_sidebar_and_nav_links_agree_on_which_destinations_exist` in
`tests/test_politikku_site_links.py` compares every `NAV_LINKS` key with the
`sb-` IDs inside `frontend/public/index.html`'s `.sb-nav`. It deliberately
includes `en_only` links: the SPA uses one static HTML file for both languages
and changes text client-side rather than serving separate English and Malay
markup. The test fails with the symmetric difference whenever either sidebar
adds or removes a destination without updating the other.

## Rejected alternative: generate the SPA sidebar from Python

Generating `index.html`'s sidebar markup from `NAV_LINKS` at build time would
replace the two hand-written copies with one Python source of markup. We reject
that approach for three measured reasons.

First, the renderers are legitimately different rather than accidentally
duplicated. The SPA's Map item is a `<button>` calling `showWholeMap()` because
it changes in-app JavaScript state; the server-rendered shell uses a plain
`<a href="/">` because a full page load has no app state to preserve.
`#sb-states`, `#sb-state-hover-label`, and `#sb-share` exist only in the SPA,
while the server-rendered sidebar carries trust-strip and language-toggle
structure the SPA does not need. Shared generated markup would either require
a template branch for each difference — no simpler than two files — or remove
functionality from one surface.

Second, `frontend/dev-server.py` serves `frontend/public/index.html` directly.
There is no Python generation step in the frontend development loop. Making
that file depend on Python output would couple a currently direct frontend
workflow to the Python build pipeline.

Third, `docs/agents/model-effort.md` identifies hard-to-reverse choices as an
escalation trigger. Code generation is the harder-to-reverse choice here: a
generator can be deleted in one commit, but doing so quietly restores two
unsynchronised files with no warning. Removing a contract test is an obvious,
visible regression. The defect found here was not duplicated markup; it was
divergent destination membership. Testing that contract targets the defect
directly while preserving the sidebars' necessary differences.

## Consequence

Any destination added to or removed from `NAV_LINKS` must receive the matching
`sb-{key}` entry change in the SPA sidebar in the same integration sequence.
The markup and behavior of those entries remain owned by their respective
renderers; only membership is shared and enforced.
