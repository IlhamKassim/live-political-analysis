# Read Poll Calibration off leader approval, attributed as at fieldwork

CONTEXT.md defines Poll Calibration as Merdeka Center's periodic survey
results, ingested to sanity-check News Sentiment. News Sentiment is a signed
score per Coalition. Merdeka Center publishes nothing per Coalition.

What its political reports do publish, issue after issue, is an approval
rating per named leader — satisfied and dissatisfied percentages for seven or
so figures — plus crosstabs of *government* satisfaction broken down by the
respondent's party affiliation. The crosstabs look Coalition-shaped and are
not: "69% of PH supporters are satisfied with the federal government" measures
PH voters' view of the government, not the public's view of PH. Using it as
PH's score would compare a loyalty measure against a coverage-tone measure and
call the gap a finding.

Leader approval points the right way. It is the public rating a person, and
a Coalition's leaders are the most visible thing about it. So: a Coalition's
Poll Calibration is the unweighted mean of the net approval — satisfied minus
dissatisfied, over 100 — of its leaders the report rated.

Three consequences, each deliberate.

**Net, not raw approval.** News Sentiment is signed and centred on zero. A
raw 30% approval is a poor showing but would read as mild warmth at +0.30 on
a −1..+1 axis. Net approval puts the published pair on the axis the trend
already uses without rescaling either published number.

**Unweighted across leaders, as Sentiment is unweighted across Articles.**
Both are means over whatever evidence named the Coalition, so both inherit the
same known limitation: a Coalition whose one rated leader is unpopular scores
worse than one whose three average out. The leader count travels with the
score everywhere it is shown, for exactly that reason.

**A leader counts towards the Coalition their party sat in while the survey
was in the field.** Not at publication, and not today. The March 2026 report
makes the case itself twice over: it rates Khairy Jamaluddin, who was outside
UMNO throughout the 12 March – 9 April fieldwork and was readmitted on 17
April, eight days after it closed; and Rafizi Ramli, who was a PKR member
throughout it and left on 17 May, five weeks after. Attribute by today's
affiliations and the same survey answers move between Coalitions as people
change parties. So the attribution is transcribed into
`data/poll_calibration.json` per report as historical fact, and is *not*
derived from `coalitions.json` — a coalition realignment must not reach back
and re-attribute a survey already taken. `coalitions.json` is still consulted,
but only to reject a Coalition name that does not exist.

A leader who belonged to no Coalition at fieldwork — Khairy, here — is
reported with their rating and left out of every score, never folded in and
never dropped silently. Absence of evidence is not evidence of neutrality, the
same rule `aggregate_sentiment` follows for an Article that names nobody.

## What this does not do

It does not calibrate the Swing Model. ADR 0003 left `sentiment_sensitivity`
and `state_signal_weight` provisional and named issue #10 as where they would
be fitted; #10 as scoped builds the ingestion and the comparison, which is the
prerequisite. Fitting the constants needs a News Sentiment series long enough
to overlap several reports, and at one report every few months that is a
question of elapsed time, not of code. Until then the dashboard shows the two
series side by side and states that they measure different things; nothing
reads Poll Calibration into a Projection.
