# Zero-cost is the default, not a hard mandate — flag real spend for approval

> **Amends [ADR 0002](0002-zero-cost-self-hosted-sentiment-stack.md).** ADR
> 0002's decisions (self-hosted sentiment inference, free-tier Postgres,
> GitHub Actions, GitHub Pages, no custom domain) all still stand as the
> *default* choice. What changes is the constraint's force: "no recurring
> cost at all" was a hard mandate that ruled options out categorically. It
> is now a strong default that can be spent past, deliberately, with the
> maintainer's explicit sign-off first — never inferred, never silent.
> `no custom domain` is already stale in practice: `public/CNAME` (added
> 24 Aug 2026) points the site at `politikku.my`, a real recurring domain
> cost incurred before this ADR existed to name it. That's the gap this ADR
> closes, not a new departure invented for this document.

## Why

Settled in conversation on 2026-08-24, prompted by planning the PolitikKu
design handoff (#69): the stack decision for that initiative (#70) turned
out not to need paid hosting at all — but the question of *whether paid
options are even on the table* kept shaping the conversation anyway, because
ADR 0002 phrased zero-cost as something the project could not exceed rather
than something it defaults to. The maintainer's actual position, stated
directly: not "I have to pay for nothing," but "zero-cost by default, and
tell me when something would cost money so I can decide."

That's a different rule than ADR 0002 wrote down, and it's the one the
project should actually be run on going forward.

## Decision

**Default to the free option. Always.** Every decision ADR 0002 made stands
as the starting point for its area: self-hosted CPU inference over a paid
LLM API for News Sentiment, GitHub Actions' free tier, a free-tier Postgres,
GitHub Pages. Nothing here reopens any of those choices on its own — this
ADR changes what happens when a free option is worse, not the standing
recommendation.

**A real recurring cost is a decision point, not a wall.** When free is
worse — degrades quality, blocks a feature, or is materially more expensive
in engineering time than a small paid tier would be — that tradeoff gets
surfaced explicitly, with the actual cost named, before anything is
provisioned or committed to. Silently defaulting to free because "the ADR
says zero-cost" is exactly as wrong now as silently reaching for a paid
service because "the constraint's gone" — both skip the maintainer's actual
call.

**This applies project-wide**, not just to new initiatives — any agent
(Claude, DeepSeek, a future session) working anywhere in this repo carries
this posture, per `docs/agents/domain.md`'s instruction to read the ADRs
touching whatever area is being worked in.

## What this does not do

It does not change any of ADR 0002's specific choices today. The sentiment
model is still self-hosted CPU inference; the DB is still free-tier; hosting
is still GitHub Pages. Nothing about News Sentiment's `Zero-cost by
requirement` framing in `CONTEXT.md` describes an active plan to switch to a
paid classifier — it describes the current default remaining the default
until a specific, named tradeoff makes a paid alternative worth raising.

## Consequence

`CONTEXT.md`'s News Sentiment definition ("Zero-cost by requirement — see
ADR 0002") is updated to read as a default rather than a requirement, since
"requirement" is no longer accurate — see the diff alongside this ADR.
