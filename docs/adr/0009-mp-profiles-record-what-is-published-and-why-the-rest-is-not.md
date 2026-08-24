# An MP Profile records what Parliament actually publishes, and names what it does not

Issue #78 asks for a per-MP profile — identity, Coalition, tenure, GE15
result, contact, attendance, voting record, sponsorships — sourced from SPR,
the Dewan Rakyat Hansard and `parlimen.gov.my`. Half of that list is
published. This records which half, so the other half is not re-researched
every time someone notices a blank, and — more importantly — so nobody fills
one in.

The stakes are why this ADR exists at all. Every figure on a profile is
attached to a named, identifiable person, so a wrong service-centre number
or a misattributed vote is a different class of mistake from a wrong number
on an aggregate chart. The design handoff's own mock for P.102 Bangi shipped
an invented address, an invented phone number, four invented voting-record
rows and two invented Bill titles, all of them plausible; the handoff says
so, but a reader of the rendered page could not have told.

## What is published, and where

**Identity, Coalition and contact** — `parlimen.gov.my`'s Members directory
(`ahli-dewan.html?uweb=dr`) and the per-Member page behind it. Parliament
states the name, the Seat, the Coalition, a telephone number, an email
address and a correspondence address. This is the only official source for
any of them.

**GE15 result** — already in this repo's pipeline. The Baseline Loader reads
Thevesh Theva's Malaysian election dataset (`lpa.sources`), which carries the
Election Commission's candidate-level results *and* `results_parlimen_ge15.csv`
with per-Seat majority, elector count and turnout. Nothing needed sourcing
afresh, and the two files cross-check: ballots in the box less rejected
ballots equals the candidates' votes, and the derived majority equals the
official *majoriti*. `SeatBaseline` keeps the Coalition-level share it
already had; the profile adds only the candidate-level figures.

**Voting record** — the Digital Hansard portal (`hansard.parlimen.gov.my`),
Parliament's own full-text Hansard, published as structured sections rather
than the PDF-per-sitting the older site serves. After a Division it prints
four name lists — *Ahli-Ahli Yang Bersetuju / Tidak Bersetuju / Tidak
Mengundi / Tidak Hadir* — naming every Member. That is what makes a
per-Member voting record possible at all, and it is better than expected:
the record is a matter of fact, not inference from party line.

## What is not published

**Attendance.** Nobody publishes a per-Member attendance figure. Digital
Hansard has a route for one — `/kehadiran/dewan-rakyat`, present in the
site's own build manifest — but it returns HTTP 500 in a browser as well as
to a fetch, and appears in no navigation on the site. The feature is built
and not released. Left unset rather than estimated.

Two near-misses are worth naming, because both are tempting and both would
be wrong. Hansard names who was *absent from a Division*, which measures ten
days out of 265 and is not attendance. Hansard also attributes every speech,
so "sitting days this Member spoke on" is computable (169 of 265 for Bangi)
— but speaking is not attending, and a page that showed that figure under an
attendance label would be asserting something no source says.

**The component party.** Parliament's directory publishes the *Coalition* in
its `Parti` field — "PH" for Bangi, not "DAP". The Election Commission
records the ballot line, which is also the Coalition, because component
parties contested GE15 under their Coalition's registered logo. So neither
official source states the component party, and the design's "DAP" chip has
no primary source behind it. Left unset. A future session that wants it
should find a source that is actually authoritative for party membership
rather than inferring it.

**Sponsorships.** Every Bill in Parliament's own register for this term was
tabled by a Minister or Deputy Minister; the Member for Bangi appears
nowhere in it. That is a finding rather than a gap — Malaysia has no working
private member's Bill route — so `bills_sponsored` is empty *and* carries the
reason. Motions a Member files are a separate matter: Hansard shows the
Member for Bangi asking after the status of one he had filed, so they exist,
but Parliament publishes no register of them and one cannot be confirmed
either way.

## Decision

Model absence as data. `MPProfile.unverified` maps each unset optional field
to the reason it is unset, and `lpa.config.load_mp_profiles` refuses to load
a profile that leaves one unexplained. An unexplained blank is exactly how an
invented value gets in later — it looks like something waiting to be filled —
so the schema does not allow one to exist.

Ingest with `scripts/build_mp_profiles.py`, which reads each Member's
position straight from Hansard's name lists and never curates it, but takes
the Division *tallies* from a hand-transcribed table. The Chair's declaration
is free prose, phrased differently every time ("Yang tidak mengundi ―
seorang"; "Tetapi bersetuju― 146"), and a parser that guessed at it would
fail silently on the next new phrasing. The transcription is checked rather
than trusted, against the number of names Hansard lists in each section — the
same shape as ADR 0008's curated `TOWN_LOCALITIES`, and for the same reason.

A Division the table does not cover is a build failure, not a skip, so a vote
taken at the next sitting cannot quietly go missing from a record that
presents itself as complete.

## Consequences

The pilot profile is honest and partial: fourteen fields populated from named
sources, three (`party`, `attendance`, service-centre hours) explicitly
unset with reasons, and a voting record of ten Divisions rather than the
mock's four — which is the entire recorded voting record of the term, not a
recent slice.

That last point will surprise a page designer, and #79 should not present it
as "last 4 divisions". Recorded Divisions are rare in the Dewan Rakyat: most
legislation passes on a voice vote that records nobody's position. Ten in
three and a half years is the House working normally.

**Scope shipped now**: P.102 Bangi only, the same Seat #76's postcode index
pilots. The shape scales to all 222 — only `SEATS` in the build script is
Bangi-specific — but the tally transcription does not, and the sitting sweep
is not free: the portal offers no search across sittings, so finding
Divisions means fetching all 265 of the term, a few hundred megabytes and
several minutes. Both are follow-up work under #78 rather than done here.

**Trade-off accepted**: a Division's `subject` is Hansard's own heading,
verbatim and in Malay and sometimes carrying the source's own typo ("RANG
INDANG-UNDANG"). Translating or tidying it would put words this pipeline
invented next to a named person's vote, which is the thing this ADR exists to
prevent. Presenting it to an English-reading Audience is #79's problem, and
should be solved by translating at the presentation layer with the original
kept alongside, not by editing the record.
