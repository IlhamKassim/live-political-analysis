# Build the seat-level baseline first, but ship coalition-level Projections first

We considered predicting GE16 purely at the Coalition level (a single national/regional swing rolled into totals, no per-Seat data) versus going straight for a full Seat-Level Projection (calling all 222 Seats individually).

Per-Seat historical data — GE15 results, margins, and demographics — turns out to be genuinely available (Malaysian Election Corpus, Tindak Malaysia, PolitikMY). The hard part isn't the Baseline, it's the Swing Model: there's no existing source that turns current Sentiment into a credible per-Seat Swing, and building one well is a research-grade problem, not a data-availability one.

Decision: ingest and store the per-Seat Baseline from day one, but the first working Projection only rolls a Swing up to Coalition-level totals (uniform swing, not seat-adjusted). Seat-Level Projection is a planned upgrade once the Swing Model is validated against the Baseline — same data layer, staged ambition, rather than two separate builds later.
