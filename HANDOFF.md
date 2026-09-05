# Handoff: PolitikKu, 2026-09-05 — remaining work after Waves 1 and 2

**Repo:** `/Users/hamboii/code/live-political-analysis` (`IlhamKassim/live-political-analysis`)
**Branch:** `main`, pushed directly, no PRs
**Live:** https://politikku.my — deploys via `.github/workflows/daily.yml`
(hourly cron at `:07`, plus `gh workflow run daily.yml --ref main`; **there is
no `push:` trigger**, so a push alone does not deploy)

**Model/effort for everything below: Sonnet, high effort.** Not medium. See
"Why high effort" at the end — it is not a formality.

---

## What is already done and live

| Wave | Ticket | Result |
| --- | --- | --- |
| 1 | #149 Tracks A+B | PolitikMY dark design site-wide; `/bills/`, `/dewan/`, `/politicians/` no longer serve unstyled HTML |
| 2 | #150 | In-app views restored — nav no longer leaves the map app; `COALITION_COLORS` restored |
| — | #151 (part) | Redaction 20 display serif restored; Space Grotesk + Redaction self-hosted; `.bento-tile` adopted |

Settled and **not** to be relitigated:

- **ADR 0015** — PolitikMY's dark system is the site's only design system. The
  navy/paper system from `design_handoff_politikku` is retired as a *visual*
  reference but **kept as a content reference** (bill card fields, FACT/MODEL
  pattern, and `politikku_i18n.py`'s BM translation table, which cites it
  legitimately — do not sweep those citations).
- **ADR 0012** — `COALITION_COLORS` is reused verbatim from
  `frontend/public/lib.js`. Never redefine the colour map in Python.
- Typography is a **three-font** split (`docs/design/mypolitik-new-views-spec.md`
  lines 50-60): `--sans` Space Grotesk (body), `--font-display` Redaction 20
  (headings), `--mono` JetBrains Mono (numbers).

---

## Task 1 — chrome seam (issue #151). Decision already made; implement it.

### The decision (do not re-open)

**`politikku_shell.NAV_LINKS` is the single source of truth for nav
membership. A contract test enforces it. The markup stays duplicated on
purpose.**

Rejected alternative: generating `index.html`'s chrome from Python at build
time. Rejected for three measured reasons:

1. The two chromes are legitimately different and must stay so. Measured:
   SPA sidebar 3,997 bytes / 5 anchors / 7 buttons; SSR sidebar 5,503 bytes /
   14 anchors / 1 button. `Map` is a `<button>` in-app (calls
   `showWholeMap()`) but an `<a href="/">` statically. `#sb-states`,
   `#sb-state-hover-label`, `#sb-share` are map-only. The SSR topbar carries a
   trust strip. One markup would break one surface.
2. `frontend/dev-server.py` serves `index.html` with no Python pipeline.
   Build-time generation couples the frontend dev loop to the Python build.
3. `docs/agents/model-effort.md` trigger 4 — generation is hard to reverse, a
   test is deleted in one commit. Duplication of markup was never the harm;
   divergence of destinations was.

### The live bug this exists to fix

`NAV_LINKS` has **10** entries. `frontend/public/index.html` and
`frontend/public/app.js` contain **zero** references to `methodology`,
`glossary`, `coalitions` or `ge16-process`. Verify this yourself first:

```
grep -ci methodology frontend/public/index.html frontend/public/app.js
```

**Four of the ten nav destinations are unreachable from the map homepage.**
This is the "two navs that disagree" problem #149 set out to kill; Wave 1
unified the nav only on the Python side.

### What to build

1. **Add the four missing items** to `index.html`'s sidebar, as
   `<a class="sb-item">` matching the five existing anchors' shape (icon span +
   label span, `data-i18n` attributes). Targets: `/methodology.html`,
   `/learn/glossary.html`, `/learn/coalitions.html`, `/learn/ge16-process.html`.
   These are content pages with **no in-app view**, so they must **not** be
   added to the click-interception logic in `app.js` (~line 4481) — a plain
   full navigation is correct for them.
2. **Write the contract test** in `tests/test_politikku_site_links.py`. Parse
   `frontend/public/index.html`, extract the sidebar's nav destinations, and
   assert the set equals the destinations `NAV_LINKS` produces. It must fail if
   either side gains or loses an item.
3. **Allowlist the legitimate exceptions inside the test, with a reason
   comment each** — `sb-map` (a button in-app, a link statically), `sb-states`,
   `sb-state-hover-label`, `sb-share`, `sb-about`. The allowlist is the
   documentation; make each entry say *why*.
4. **Write ADR 0016** recording this decision, following `docs/adr/`'s house
   style (see 0012 and 0015). It must state the rejected alternative and why,
   or a future session will "fix" this by building the generator.

### Verify

- `uv sync --python 3.11 --extra dev --extra telegram` then `pytest -q` — must
  reach **705 passed** (704 now, plus your new test).
- Prove the test actually bites: temporarily delete one nav item from
  `index.html`, confirm the test fails, restore it.
- Load the map at `/` and confirm all 10 nav items are present and clickable.

---

## Task 2 — Wave 3 SEO (issue #149, Tracks C and D)

Full spec is in **issue #149** — `gh issue view 149`. Do not re-derive it.
Summary of what is outstanding:

1. **`/ms/` returns 404** while 200+ `/ms/` URLs sit in `sitemap.xml`. Either
   render a BM root or 301 it to `/` — whichever you pick, the sitemap and the
   `hreflang` alternates must agree. A sitemap listing a 404 is the worst of
   the three options.
2. **Redirect hops.** Nav points at `/politicians`, `/dewan`, `/projection`,
   `/sentiment` — all 301s. Only `/bills/` is canonical. Point internal links
   at canonical paths; keep the stubs for external backlinks.
3. **JSON-LD** — `Dataset` for `/projection/`, `Legislation` per bill, `Person`
   per MP profile. `render_shell` already emits a `WebSite` block; extend it,
   do not duplicate.
4. **a11y** — add a `<main>` landmark, fix non-sequential heading order.
5. **Self-host JetBrains Mono.** It is the last Google Fonts request
   (`politikku_shell.py` ~line 699 and `frontend/public/index.html` ~line 24).
   Space Grotesk and Redaction 20 are already self-hosted in
   `frontend/public/fonts/`. Download the woff2, add `@font-face` with an
   **absolute** `/fonts/…` URL, then delete the Google `<link>` and both
   `preconnect`s. Also delete the four now-unused woff2 in `public/fonts/`
   (`newsreader-variable`, `ibm-plex-sans-variable`, `ibm-plex-mono-400`,
   `ibm-plex-mono-500`).

**Absolute URLs matter.** SSR pages are served from `/bills/`, `/dewan/` etc.,
so a relative `url(fonts/…)` resolves to `/bills/fonts/…` and 404s. Every font
URL in `politikku_shell.py` must start with `/fonts/`.

### Verify

Objectively, with `curl` — this whole task is machine-checkable:

- Every URL in `sitemap.xml` returns 200.
- Each page's `<loc>` matches its own `rel=canonical`.
- `/ms/` no longer 404s.
- No internal nav link 301s.
- Zero `fonts.googleapis.com` references remain anywhere.

---

## Dispatching workers

Two options, both proven this session.

**API workers (preferred — quota-free).** `scripts/deepseek_agent.py` drives
any OpenAI-compatible endpoint via `--base-url`. Credentials are in
`.env.agent` at the repo root (gitignored, `chmod 600`) — load with
`set -a; . ./.env.agent; set +a`. **Never print the key.**

```
uv run --python 3.11 python scripts/deepseek_agent.py \
  --task-file <spec.md> --model gpt-5.6-sol \
  --max-turns 45 --max-wall-clock-seconds 1500 \
  --work-dir <scratch>/wt-<name>
```

Models: `gpt-5.6-sol` (flagship — use for judgment work), `gpt-5.6-terra`
(mid-tier — fine for well-specified mechanical work), `gpt-5.6-luna`
(cheapest), `deepseek-v4-flash` (1M context, but used 2× the input tokens of
the GPT models for an identical request). All 8 honour
`tool_choice: "required"`.

The agent commits **in its own worktree** and cannot push, merge, or open a PR
— no such verb exists in its tool schema. Recover its work with
`git cherry-pick <sha>`, or `git -C <worktree> diff > p.patch && git apply
p.patch` if it declined to commit.

**Antigravity workers** (2, Gemini 3.8 Flash) — the user runs these manually;
they were out of quota as of this handoff. Give copy-paste prompts.

### Writing a worker task file — lessons paid for this session

- **State the file allowlist explicitly and say another agent holds the rest.**
  Both workers respected it exactly.
- **Do not contradict yourself.** One task said "edit exactly one file" and
  also "update the test assertions." The worker correctly obeyed the stricter
  rule and reported the failures honestly — the contradiction cost a whole
  extra run.
- **Warn about `test_resolve_repo_root_with_no_explicit_root_finds_the_real_repo`.**
  It asserts the checkout directory is named `live-political-analysis`, but an
  agent worktree is named `worktree`, so it *always* fails there and passes in
  the real repo. Every task file must say to ignore it. **Better: fix the test
  to assert on `pyproject.toml`'s project name instead — it is a 5-minute job
  that stops taxing every future run.**
- **Say "a truthful `blocked` beats a confident wrong answer."** One worker
  used it correctly and stopped rather than committing over an unexplained
  failure.

---

## Why high effort, concretely

`docs/agents/model-effort.md` defines high effort as *"verify each claim
against the real thing before reporting done."* That is not ceremony here.
**Three bugs shipped-and-caught this session all passed the test suite and all
greps:**

| Bug | Tests | Greps | Actually caught by |
| --- | --- | --- | --- |
| Topbar rendered under the sidebar on every page | pass | clean | computed `left` in a browser |
| `/politicians/` cards one-per-row, giant photos | pass | clean | re-running the class sweep including f-string variables |
| Headings not using the display serif | pass | clean | computed `fontFamily` in a browser |

The third is the sharpest warning. A worker added
`h1, h2 { font-family: var(--font-display) }`, tests passed, greps were clean,
and it genuinely worked on `/sentiment/` and `/learn/*`. It silently did
nothing on `/dewan/`, `/bills/` and `/politicians/`, because
`.pol-dir-head h1` (specificity 0,1,1) beat it (0,0,1).

**A green suite is not evidence that a CSS change took effect.** For anything
visual, render the page and read the computed style. `frontend/dev-server.py`
(port 4178) serves the SPA; `python3 -m http.server` over a
`--output-dir` build serves the static pages.

Also: `frontend/public/worker.test.mjs` has **one genuinely failing test** —
the Cloudflare health probe still asserts the service name is `mypolitik` after
the rebrand to `politikku`. It is pre-existing (fails on `48d4384`), unrelated
to any of this work, and a one-line fix nobody has claimed.

---

## Standing rules for this repo

- **Verify under pinned Python 3.11** (`uv run --python 3.11 …`). The local
  shell is 3.12+; CI pins 3.11; this has produced false local passes before.
- **Push straight to `main`.** No PR gate in practice.
- **A push does not deploy.** Dispatch `daily.yml` or wait for `:07`.
- **Re-verify any agent's "done" claim yourself.** Every worker this session
  reported success accurately *and* one of them still shipped a bug that only a
  browser check found.
- Issues live on GitHub via `gh` (`docs/agents/issue-tracker.md`). Domain
  vocabulary comes from `CONTEXT.md` — use Coalition, Seat, Majority,
  Projection, Seat Call, Bill, Division, MP Profile as defined there.
