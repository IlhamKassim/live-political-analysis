# Cloudflare Worker + KV is a conscious, named departure from static-only hosting

> **Amends [ADR 0002](0002-zero-cost-self-hosted-sentiment-stack.md) and
> [ADR 0007](0007-zero-cost-is-default-not-mandate.md).** Neither is
> reversed. ADR 0007 already established the actual rule this project runs
> on: default to free, but name a real cost explicitly and get sign-off
> before it's incurred — never infer it, never absorb it silently. This ADR
> is that naming, for one specific addition: the site's serving model stops
> being purely static once election-night live mode ships.

## Why

The PolitikKu × `mypolitik` merge (session of 2026-08-29) brought in
`mypolitik`'s election-night live mode: `frontend/worker.js`, a Cloudflare
Worker that reads/writes a KV namespace (`PRN_LIVE`, generalized to
`LIVE_ELECTIONS`-style per-election keys in the Step 6 generalization work)
to serve live seat-count updates during an actual count night, plus serves
every other page as a static asset via the same Worker's `assets` block.

Every other page in this project — including the entire Python-rendered
half of the site — is genuinely zero-cost static: GitHub Actions builds it,
GitHub Pages serves it, no server-side compute runs on a request. Live mode
breaks that pattern by construction: a live count needs *something*
holding current state that many concurrent readers poll, which a
build-once static file cannot do. There is no zero-cost way to serve
"what's the count right now, updated every few minutes, to everyone
refreshing the page during a live count" — this is not a case where a paid
option is merely more convenient than a free one; the free/static option
does not exist for this specific feature.

## Decision

**Election-night live mode runs on Cloudflare Workers + KV, in addition to
GitHub Pages for the rest of the site**, rather than forcing live mode into
the static-only model or dropping it from Phase 1 scope. This is scoped
narrowly: the Worker serves `/api/live/:electionId` (read/write current
count state) and, per `mypolitik`'s existing pattern, the site's static
assets when deployed via Workers rather than Pages — see Step 5 of the
merge plan for the still-open decision of whether the *rest* of the site
also moves to Workers-as-host, or stays on GitHub Pages with only the
live-mode path on Cloudflare.

**In practice this is very likely still free**: Cloudflare Workers' and
Workers KV's free tiers (100,000 requests/day on Workers, 100,000
reads/day + 1,000 writes/day on KV, as of this writing) comfortably cover
a single state election's count night, let alone the between-elections
idle period when the Worker serves almost nothing. This ADR does not claim
a paid tier is being provisioned — it claims the *shape* of "zero-cost
static only" is what's changing, since a live count is server-side compute
by nature, not a happenstance of which specific free tier absorbs it today.
Per ADR 0007, if real traffic (a competitive, high-turnout state election,
or eventually GE16 night) ever pushes past Cloudflare's free tier, that
specific cost gets named and put to the maintainer before anything is
upgraded — this ADR pre-authorizes the free-tier Worker/KV addition itself,
not any future paid tier of it.

## What this does not do

It does not move Sentiment's self-hosted inference, the Postgres database,
or the GitHub Actions pipeline off their existing zero-cost defaults — ADR
0002's and ADR 0007's standing choices for those areas are untouched. It
does not decide Step 5's broader question (whether the *whole* site's
hosting moves to Cloudflare Workers) — that is a separate, larger
infrastructure decision requiring its own sign-off, not implied by scoping
live mode onto Cloudflare narrowly here.

## Consequence

`CONTEXT.md`'s per-component "zero-cost by default" notes stay accurate for
every component except election-night live mode, which should be described
as "served via Cloudflare Workers/KV (free tier today) — see ADR 0013,"
not folded into the same "zero-cost by default, not requirement" language
used for Sentiment, since live mode's constraint is architectural (no
static option exists), not a preference that could in principle default
back to free-and-static the way Sentiment's classifier choice could.
