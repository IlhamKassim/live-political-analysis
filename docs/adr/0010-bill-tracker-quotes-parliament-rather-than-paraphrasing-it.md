# The bill tracker quotes Parliament's own words rather than paraphrasing them

Issue #80 asks for the bill tracker's real data: title, plain-language
summary, stage, date, division result, sourced from `parlimen.gov.my`, and
asks explicitly that the plain-language summary's production be decided and
documented rather than left implicit — the design handoff's mock ships one
per Bill and the handoff itself says the mock's own summaries are invented
placeholders, not sourced text.

## Where the pieces come from

**Title, year, stage and stage date** — Parliament's own Bills register
(`parlimen.gov.my/bills-dewan-rakyat.html?uweb=dr`), the same page ADR
0009's `bill_sponsors()` already reads. `stage` is kept as Parliament's own
status word (*Lulus*, *Dirujuk ke JKPK*, *Bacaan Kali Pertama*) rather than
translated or recategorised — the same call ADR 0009 made for a Division's
subject, for the same reason: translating a factual field is a presentation
concern, and doing it in the data layer would put words this pipeline chose
next to a citable claim about Parliament's own state.

**Division result** — not fetched fresh. `lpa.mp_profile`'s ADR 0009
already read Hansard's full Division record for the 15th Parliament and
found exactly ten, transcribed and cross-checked once, shipped in
`data/mp_profiles.json`. A Bill in this pilot either matches one of those
ten by sitting date and subject (curated in `BILL_DIVISIONS`, checked
against a live fetch the same way ADR 0008's `TOWN_LOCALITIES` is) or it
does not — and "does not" is itself a finding, not a gap requiring a fresh
Hansard search, because #78 already established that list is complete.
Re-deriving the same tally independently here would risk the one thing this
initiative keeps refusing to risk: the same real fact recorded twice,
disagreeing.

## The plain-language summary: quoted, not authored

We considered writing an original one-sentence gloss of each Bill ourselves
— genuinely plain language, easier to read than legal drafting. Rejected:
this repo's `docs/agents/model-effort.md` names "editorial judgement on
sensitive content" as its own escalation trigger, and a bill summary is
exactly that — a subtly wrong gloss of what a piece of legislation does
costs trust in a way that is hard to see from the sentence itself. A
paraphrase can be quietly wrong in ways the source text cannot.

Decision: every Malaysian Bill's own PDF carries a "HURAIAN" (Explanation)
section, opening with one or more sentences stating the Bill's purpose
before a clause-by-clause breakdown. `Bill.summary` is a verbatim excerpt
of that opening — specifically, the first sentence containing *bertujuan*
("is intended to"), since a Bill's HURAIAN sometimes opens with a
sentence about its constitutional basis rather than its purpose (the
Freedom of Information Bill 2026, D.R.20/2026, does exactly this — its
first sentence cites the Ninth Schedule, and the purpose sentence is its
second). Falling back to the literal first sentence when none contains
*bertujuan* keeps the rule simple and still verbatim. The only editing
applied is mechanical: internal line breaks the PDF's own layout inserted
are collapsed to spaces, never a change to a word. `summary_source_url`
points at the exact PDF page (`#page=N`), so the excerpt is checkable
against its source in one click.

This ships the summaries in Bahasa Malaysia, the language Parliament wrote
them in. Presenting them to an English-reading Audience is #79's problem —
translate at the presentation layer with the original kept alongside, the
same resolution ADR 0009 gives a Division's subject, not by editing the
record.

## A parsing failure this pipeline made once, and how it is now caught

During development, an early version of the register parser flattened the
whole page to text before searching it. The register embeds each row's
detail popup as a sibling `<div>` rather than nesting it inside the row's
own cell, so flattening interleaves one row's popup with an adjacent row's
visible cells in a way that reads as coherent prose — two different Bills'
tabling Ministers and passage dates appeared to belong to the same D.R.
code. The fix was to parse row by row (`re.split` on `<tr class="maintable">`
before extracting any field), which `_parse_row` does and
`tests/test_bill_tracker.py` checks with a fixture built to reproduce the
exact failure — two adjacent rows whose flattened text would misattribute a
field if the parser regressed to the naive approach.

## Consequences

**Scope shipped now**: four Bills — two with a real, already-verified
Division (D.R.28/2025, D.R. 5/2025), two without (D.R.8/2026, D.R.20/2026,
one of them still short of a second reading). Chosen to exercise both
shapes of the schema rather than to be representative of the register's
full size. Scaling to the whole register means repeating the parse against
more of it (untested past the register's default two-year view) and,
should a Bill's Division fall outside the ten the Parliament term has had
recorded, transcribing a new one the way ADR 0009's `DECLARED_RESULTS`
does — neither is free, and both are follow-up work under #80.

**Trade-off accepted**: `pypdf` is a new dependency, added under a `bills`
extra (`pip install -e ".[bills]"`) rather than the package's core
dependencies, since it is needed only for this manual, occasional
ingestion script and not the daily pipeline. Zero-cost per ADR 0007 — it is
free, open-source, and adds no hosting or API cost.
