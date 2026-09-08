# Build-time prerendering unifies the interactive app and public pages

> **Amends [ADR 0011](0011-politikku-becomes-the-site-old-dashboard-moves-to-projection.md)**
> (which ported the dashboard to a standalone Python-rendered page at `/projection/`)
> and **reconciles [ADR 0014](0014-app-becomes-the-site-root-audience-loses-its-page.md)
> and [ADR 0017](0017-an-orientation-gate-supersedes-app-at-the-site-root.md)**.
> This unifies the interactive application and the public content pages into a single
> implementation, replacing roughly 4,800 lines of duplicate Python page renderers with
> build-time snapshots of the interactive app.

## Why

Since the `mypolitik` frontend merge (ADR 0012/0013), the site has maintained two
independent implementations of the exact same content views:

1. **Six Python page renderers** (`src/lpa/politikku_dewan.py`, `politikku_bills.py`,
   `politikku_politicians.py`, `politikku_sentiment.py`, `politikku_projection.py`,
   and `politikku_mp_profile.py`) spanning ~4,800 lines. These wrote static HTML files
   at `/dewan/`, `/bills/`, `/politicians/`, `/sentiment/`, `/projection/`, and
   `/mp/<code>/` (plus `/ms/...` variants).
2. **The interactive SPA** (`frontend/public/app.js`), a single vanilla-JS application
   rendering the same data joins at `/app/#dewan`, `/app/#bills`, etc.

Having two separate codebases for the same views had real costs:
- **Silent drift**: When calculations, filters, or formatting were updated in one, the
  other lagged behind or produced slightly different results from the same data.
- **Visual discrepancies**: As documented in ADR 0015 (#149), the Python renderers
  emitted CSS classes that were styled only in `frontend/public/styles.css` and not in
  `politikku_shell.py`, resulting in unstyled or inconsistently styled components.
- **Maintenance overhead**: Every feature or correction had to be implemented and tested
  twice — once in Python and once in JavaScript.

Yet the site could not simply discard the public pages and become a pure client-side SPA:
- **Search-engine indexing**: Google, sitemaps, `hreflang`, and structured JSON-LD
  (`Dataset`, `Person`, `WebSite`) require server-delivered HTML, not an empty shell.
- **Link previews**: Social sharing (WhatsApp, Telegram, X/Twitter) reads Open Graph and
  Twitter card meta tags from the delivered HTML and ignores URL fragments (`#hash`).
- **Zero-JS accessibility**: Readers on low-end devices or non-JS environments must still
  receive the full content on first load.

The site needs **one implementation**, not two, with both instant full-content delivery
and rich client-side interactivity.

## Decision

**Prerender the interactive app at build time; do not rewrite it.**

Instead of introducing a complex, heavy meta-framework (such as Next.js or Remix) which
would violate the project's zero-cost and minimal-dependency stack (ADR 0002 / ADR 0007),
we prerender the existing vanilla-JS application into static HTML at build time:

1. **Convert internal routing from hash-based to real directory paths.**
   `app.js` replaces hash-based navigation (`#dewan`, `#bills`, `#politicians`,
   `#projection`, `#sentiment`, `#mp/<code>`) with real paths using the browser History
   API (`/dewan/`, `/bills/`, `/politicians/`, `/projection/`, `/sentiment/`,
   `/mp/<code>/`, and their `/ms/...` equivalents). Deep-links are now standard URLs,
   while existing hash bookmarks continue to be parsed and cleanly upgraded via
   `history.replaceState`.

2. **Add a build-time prerendering step in the deployment pipeline.**
   After data files are exported and folded into `public/app/`, a prerender runner
   (`src/lpa/politikku_prerender.py`) launches headless Chromium via Playwright, loads the
   app, visits all content routes (the 6 core sections plus 184 MP profiles across English
   and Bahasa Malaysia = 380 pages), waits for an explicit `data-render-complete` ready
   signal, and writes the resulting static HTML directly to disk at the exact paths GitHub
   Pages serves (e.g. `public/dewan/index.html`, `public/ms/dewan/index.html`).

3. **Preserve full SEO, Open Graph, and JSON-LD parity.**
   Every prerendered page receives the exact `<title>`, meta description, canonical link,
   bilingual `hreflang` tags, Open Graph card tags, and JSON-LD structured data
   (`@type: "Dataset"` for Projection with data downloads, `@type: "Person"` for MP
   profiles, `@type: "WebSite"` overall) previously produced by the Python renderers.

4. **Retire the six duplicate Python page renderers.**
   `politikku_dewan.py`, `politikku_bills.py`, `politikku_politicians.py`,
   `politikku_sentiment.py`, `politikku_projection.py`, and `politikku_mp_profile.py` are
   deleted. Shared data helpers (`bill_stage_style`, `party_color`, `load_coalition_colors`,
   and `SentimentPageModel`) are extracted to dedicated shared modules so the daily pipeline
   (`sentiment_export.py`, `politikku_landing.py`) continues uninterrupted.

5. **Archive dated permalinks from the snapshot.**
   The Projection snapshot is copied to `public/projection/<year>/<month>/<day>.html` (and
   `/ms/...`), ensuring #55's citation permalinks continue to be archived without change.

## What this does not do

- It does not touch `src/lpa/politikku_landing.py` or the `/` and `/ms/` routes. Per ADR
  0017, the landing page remains the server-rendered orientation gate for first-time
  visitors.
- It does not introduce any paid external APIs or persistent hosted server infrastructure.
  Prerendering runs during the existing GitHub Actions workflow on GitHub's free runners.
- It does not break existing bookmarks or links: redirect stubs in `politikku_redirects.py`
  and client-side hash upgrades keep old URLs operational.

## Consequences

- **Single source of truth**: The presentation logic and styling live solely in the frontend
  codebase (`frontend/public/`). There is no second renderer to keep in sync.
- **Consistent design**: All content views inherit the official `mypolitik` design tokens
  and responsive layouts from `styles.css` identically.
- **Build time**: Prerendering 380 pages takes only ~3–5 seconds in CI because headless
  Chromium switches views in-memory within a single session rather than launching 380
  separate browser processes.
- **Fast first paint**: Visitors receive pre-baked, fully-rendered HTML immediately on plain
  HTTP fetch, with `app.js` hydrating seamlessly to provide client-side interactions.
