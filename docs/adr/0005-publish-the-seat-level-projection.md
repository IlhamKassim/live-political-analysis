# Publish the Seat-Level Projection, and frame it as arithmetic

[ADR 0001](0001-seat-level-baseline-with-coalition-first-projection.md) staged
the ambition: load the per-Seat Baseline from day one, publish Coalition totals
only, and hold the Seat-Level Projection back until the Swing Model was
validated. **This supersedes that.** The public dashboard (#17) renders the
Dewan Rakyat as 222 named Seats, each carrying the Coalition it is projected to
fall to and by what margin, so the Projection has to publish them.

The Swing Model already computes this and throws it away. `_projected_winner`
runs per Seat and only the tally survives. What changes is what the Projection
carries, not how it decides — no new model, no new signal, no new data.

We considered rendering the chamber from Coalition totals alone: 222 dots in
bloc order, no Seat identity. That is honest and nearly free, and it keeps the
one thing the hero image is about — the Government Coalition's block overrunning
the 112 line. It was rejected because a chamber of anonymous dots invites the
reader to look for their own Seat and find nothing, and because the identity is
already in Storage. Withholding a `SeatBaseline.name` the tool has loaded is not
caution, it is just an omission.

ADR 0001's actual concern stands, though, and it is not answered by shipping
this — the Swing Model is no more validated than it was. So the decision comes
with a constraint on how a per-Seat call is presented, and the constraint is
part of the decision rather than a note attached to it.

**The Swing Model carries no Seat-specific signal.** It applies a *uniform*
swing within each state, so a Seat's call is fully determined by its GE15 margin
plus one state-level figure. Two Seats in the same state with the same GE15
margin get the same answer, always. `SeatBaseline.demographics` is loaded and
read by nothing. A per-Seat call must therefore be framed as *where a uniform
swing of this size puts this Seat* — arithmetic against GE15 — and never as a
judgement about that constituency. Combined with [ADR
0003](0003-provisional-swing-constants.md)'s uncalibrated constants, a named
Seat is the most falsifiable claim this tool makes and the one most likely to be
quoted back at it. The uncertainty encoding on close Seats is load-bearing, not
decoration.

Two things follow from publishing margins that did not matter while only totals
shipped.

**Projected shares must be clamped and renormalised.** The Swing Model's
docstring has carried this as a known limitation: a large Swing can drive a
trailing Coalition below zero, which is not a share of anything and so is not
something a margin can be read off. Projected shares are now floored at zero and
rescaled to the total they had at Baseline.

Where any share survives above zero this changes margins only, not calls:
flooring touches shares already behind every non-negative one, and rescaling
multiplies them all by the same positive number, so order and ties both hold.
The one case it does change is a Swing severe enough to put *every* share at or
below zero. That used to be called for the least-negative Coalition; it is now a
dead heat that falls to the Baseline winner on a margin of zero. Reading an
ordering off numbers that are all outside the vote was never evidence about
anything, and the alternative — publishing a named Seat, with a margin, off it —
is exactly what this ADR is trying not to do. Reaching it takes a Swing against
every Coalition at once, each wider than that Coalition's Baseline share; with
`sentiment_sensitivity` at 0.10 (ADR 0003) Sentiment alone moves at most ten
points, so it takes a State Election Signal far outside anything yet observed.
Recomputing the sixteen stored days both ways confirms it: no Coalition total
changes, and not one of the 3,552 Seat-days lands in the case at all.

**Per-Seat rows are kept for the latest Projection only.** The alternative is
~222 rows a day, ~81k a year, against a free-tier Postgres that [ADR
0002](0002-zero-cost-self-hosted-sentiment-stack.md) commits us to. Nothing
reads per-Seat history: the dashboard's trend line is Coalition totals, and the
public page renders one day. It is also largely recoverable — the Swing Model is
a pure function and the daily Sentiment snapshot is stored, so any past day's
calls can be recomputed, *provided* the Baseline, the config and
`data/state_elections.json` are as they were on the day. That last clause is the
honest limit of the claim — state election signals accumulate as states vote,
and recomputing an old day against today's file would answer a question nobody
asked. It is also why the Coalition totals stay stored per day rather than being
recomputed too.
