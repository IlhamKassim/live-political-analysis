# Ship the Swing Model with provisional constants, and say so

The Swing Model turns Sentiment into a Swing through two numbers that live in
`SwingModelConfig`: `sentiment_sensitivity`, the vote share a Sentiment score
of 1.0 is worth (currently 0.10), and `state_signal_weight`, how far a state
election result outweighs Sentiment within that state (currently 0.5).

Neither is fitted to anything. They were chosen so the model produces movement
of a plausible order — a strongly negative news cycle moving a few points of
vote share rather than thirty — and no more than that. There is no published
series mapping Malaysian news sentiment to vote share to fit them against, and
constructing one is the research-grade part of this project, not a prerequisite
for wiring the pipeline together.

We considered blocking the pipeline until the constants were calibrated. That
gets the ordering backwards: calibration needs a running pipeline producing a
daily Sentiment series to calibrate *against*, and the only published check
available — Merdeka Center's periodic polls — arrives every few months.

Decision: ship the constants as provisional, tunable config rather than
hardcoded values, and state plainly wherever the Projection is presented that
it is model-driven and uncalibrated. Calibration against published polling
changes config, not model logic.

**Still true as of issue #10.** #10 built the ingestion and the comparison —
Merdeka Center's reports now reach Storage as Poll Calibration and sit beside
News Sentiment on the dashboard, which is the series that was missing to
calibrate *against*. It fitted neither constant, and nothing reads a poll into
a Projection. Fitting needs a daily Sentiment history long enough to overlap
several reports, and reports arrive every few months, so what remains is
elapsed time rather than code. See
[ADR 0004](0004-leader-approval-as-the-coalition-poll-signal.md), "What this
does not do".

A related lesson is already fixed rather than deferred. An earlier version
averaged state election results into a *national* uniform Swing. Run against
the real 2026 Johor result — BN roughly 25 points above its Johor Baseline —
that alone projected BN from 30 Seats to 78 and PN from 74 to 40, before any
Sentiment was applied. A state election is evidence about that state; its Swing
is now applied to that state's Seats only. Constants can be wrong by a factor
and still be recognisably wrong; a structurally wrong extrapolation produces
confident nonsense, so it did not wait for #10.
