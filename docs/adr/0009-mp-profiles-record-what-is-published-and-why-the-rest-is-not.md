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
its `Parti` field — "PH" for Bangi, not "DAP". Left unset, and #105's sweep
of all 222 Seats sharpened rather than softened the reason. The Election
Commission's ballot line is the Coalition for most Seats, but for the PAS
Seats it reads "PARTI ISLAM SE MALAYSIA (PAS)" and for five Sarawak DAP
Seats "PARTI TINDAKAN DEMOKRATIK (DAP)" — so for 27 Seats a component party
*is* on the record. It is still not published here, because what it records
is the party that Member stood for in November 2022. This term has since
seen four Seats change hands at a by-election and two Members change
Coalition outright; a 2022 ballot line is exactly the sort of fact that goes
stale without saying so, and `MPProfile.party` is documented as the party
the Member belongs to, not the one they were elected under. A future session
that wants the chip should find a source authoritative for *current*
membership.

**Sponsorships.** Every Bill in Parliament's own register for this term was
tabled by a Minister, a Deputy Minister or a Senator; the Member for Bangi
appears nowhere in it. That is a finding rather than a gap — Malaysia has no
working private member's Bill route — so `bills_sponsored` is empty *and*
carries the reason. Two things the register does not cover, and the reason
now says so: a Bill withdrawn before its first reading, for which it
publishes neither a date nor a tabler (four in this term), and Motions,
which it does not list at all. Hansard shows the Member for Bangi asking
after the status of a Motion he had filed, so they exist, but Parliament
publishes no register of them and one cannot be confirmed either way.

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
presents itself as complete. The same argument applies one level down, to
the name lists, and #105 found it had not been honoured there. Hansard
writes a list entry as a number, the Member's name — often prefixed by a
ministerial portfolio with parentheses of its own — and the Seat in brackets,
so the Seat is not "the bracketed part" but *the bracketed part that names a
Seat*. Reading the first one instead silently dropped Lumut and Tanjong
Karang, whose entries carry a naval rank in brackets first, and every
Minister named by portfolio. Matching every bracketed group against the
Election Commission's own 222 Seat names fixes it, and an entry that names
no Seat now stops the build rather than costing a Member their vote.

## Consequences

A profile is honest and partial: fourteen fields populated from named
sources, three (`party`, `attendance`, service-centre hours) explicitly
unset with reasons, and a voting record of ten Divisions rather than the
mock's four — which is the entire recorded voting record of the term, not a
recent slice.

Three Members' records are short of those ten, and say so in
`unverified["divisions"]`. Machang is named in none of the four lists on 17
October 2024, being under the suspension the House agreed on 18 July; Kota
Bharu and Bagan Serai are each named in *two* on 4 March 2025, which
Hansard's own declared counts show cannot both be right. In all three the
Division is left out rather than resolved: the arithmetic points one way
clearly enough — the abstention list matches the Chair's count exactly and
the absence list overshoots by exactly those two names — and following it
would put this pipeline's reasoning next to a named person's vote, which is
the thing this ADR exists to prevent.

That last point will surprise a page designer, and #79 should not present it
as "last 4 divisions". Recorded Divisions are rare in the Dewan Rakyat: most
legislation passes on a voice vote that records nobody's position. Ten in
three and a half years is the House working normally.

**Scope shipped now** (revised by #105): every Seat the sources support,
which is most of the House rather than all of it. The sitting sweep turned
out to be the cheap part — it runs once for all 222 Seats, not once each —
and the tally transcription turned out to need nothing new: a sweep of all
265 sittings found exactly the ten Divisions already transcribed and no
eleventh.

## A Seat with no profile has to say why too (#105)

The same argument that makes `unverified` mandatory inside a profile makes
`_skipped` mandatory outside one. A Seat simply missing from the file is
indistinguishable from a Seat nobody got round to, which is how a blank
starts looking fillable. So every Seat is in the file: profiled, or named in
`_skipped` with what was checked and what it did not support. Four kinds of
refusal, all of them the sources disagreeing rather than this pipeline
giving up:

- **Parliament's directory lists no Member for the Seat.** Three Seats,
  including two whose Members Hansard names in every Division of the term
  and whom the Bills register names as Ministers. Parliament's own listing
  omits them; nothing else consulted here is authoritative for who holds a
  Seat, so nothing is published for them.
- **Parliament states no Coalition.** Six Seats where the directory's caucus
  is blank *and* the Member's own page has no Parti field. `coalition` is
  not an optional field, and the GE15 ballot line is not a substitute for it.
- **The Member is not the GE15 winner.** The check exists to stop a
  predecessor's election result appearing under a successor's name, and it
  fires for both the four Seats that genuinely changed hands at a
  by-election and for a further nine where the two sources write the same
  person's name differently enough — an extra given name, an alias, a
  married name — that a machine cannot tell which case it is looking at.
  Refusing all thirteen is the safe direction: a visibly missing MP is a
  loss, a wrong GE15 result under a real person's name is not recoverable.
- **The Member changed Coalition since GE15.** Two Seats. Their current
  Coalition and their election result are facts about different
  allegiances, and putting them side by side as one would read as a claim
  neither source makes.

**Cadence** (#105 asks): manually triggered, and deliberately not in
`daily.yml`. Nothing in a profile changes daily, and every run costs a full
sweep of the term's 265 sittings — a few hundred megabytes of Parliament's
bandwidth to rewrite a file that changed on none of them. Re-run when the
House rises at the end of a meeting, which is when new Divisions and new
Bills appear, and after a by-election, which is what changes who holds a
Seat. Both are events a human notices; neither is a schedule.

**Trade-off accepted**: a Division's `subject` is Hansard's own heading,
verbatim and in Malay and sometimes carrying the source's own typo ("RANG
INDANG-UNDANG"). Translating or tidying it would put words this pipeline
invented next to a named person's vote, which is the thing this ADR exists to
prevent. Presenting it to an English-reading Audience is #79's problem, and
should be solved by translating at the presentation layer with the original
kept alongside, not by editing the record.
