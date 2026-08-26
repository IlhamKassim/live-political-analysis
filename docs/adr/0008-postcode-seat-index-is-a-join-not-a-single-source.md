# The postcode → Seat index is a join of two sources, shipped as a growing pilot slice

Issue #76 asks for a postcode → Seat index sourced from the Election
Commission's 2018 delimitation, the same provenance the design handoff's
mono footnote credits. No single published dataset does this: the Election
Commission's own open-data portal (`opendata.spr.gov.my`) publishes the
"Senarai BPR" — every polling district (*daerah mengundi*) with its Parlimen
and DUN — but polling districts are locality names, not postcodes. Postcodes
are a Pos Malaysia delivery construct, drawn for mail routing, and were never
aligned to electoral boundaries.

We considered waiting for or requesting a postcode-native dataset from the
Election Commission. None exists, and there is no indication one is coming —
the "Senarai BPR" format has been locality-based since at least the last
delimitation review. Blocking on a dataset that does not exist is not a real
option.

Decision: join the Election Commission's locality-level "Senarai BPR"
(fetched live from `opendata.spr.gov.my/data/senarai-bpr.json`, the same
endpoint the SPR portal's own UI reads) against a Pos Malaysia
postcode-to-town reference (`AsyrafHussin/malaysia-postcodes`, MIT, zero-cost
per ADR 0007) by locality name. Because a Pos Malaysia town name rarely
matches a daerah mengundi string verbatim ("Bandar Baru Bangi" vs. "SEKSYEN 1
BBB"), the town → locality association itself is a **hand-curated,
per-locality-verified table** (`TOWN_LOCALITIES` in
`scripts/build_postcode_seat_index.py`), not a fuzzy string match. The script
resolves each curated locality string against a live fetch of the Election
Commission data and fails loudly if one has gone stale, so a wrong curation
is caught at build time rather than shipped silently. A postcode whose
localities resolve to more than one Seat is recorded as ambiguous — every
candidate Seat, never a guessed single answer — which is the correct
behaviour for a Malaysian postcode, not an edge case to paper over.

This makes the index's accuracy bounded by two things: the curation step's
correctness (checked by hand for every entry currently shipped) and Pos
Malaysia's own postcode-to-town granularity, which is coarser than a street
address. A postcode that resolves to one Seat here could in principle still
contain a specific street that crosses into another — issue #77's "narrow
down by street/Seksyen" fallback exists for exactly this residual case, and
the lookup result should never claim more certainty than the index actually
has.

**Scope shipped now**: Selangor's P.101 Hulu Langat and P.102 Bangi only (12
postcodes; one, 43200/43207 Cheras, is genuinely ambiguous between the two) —
the same pair #78's MP-profile pilot uses. Scaling to all 222 Seats means
repeating the curation step, locality by locality, against the full 7,748-row
Election Commission dataset; it does not scale by search-and-replace, and is
tracked as follow-up work under #76 rather than done here.

**Shipping shape**: `data/postcode_seat_index.json` (comments and source
metadata included, for the file's own auditability) is 1,996 bytes for the
pilot's 12 postcodes; the part a client would actually ship — the
`postcodes` object alone, postcode to a short list of Seat codes — is 258
bytes. Malaysia has on the order of a few thousand postcodes total against
222 Seats, so extrapolating the client payload (roughly 22 bytes/postcode)
puts a full index at well under 100 KB uncompressed — confirming the design
handoff's assumption that this can ship as a static file to the client for
client-side resolution (the geolocation privacy promise in the design
handoff depends on this: "Location is read in your browser and never sent
to us"), with no server endpoint and no logging. This estimate should be
revisited once the index actually scales past a handful of Seats.

Trade-off accepted: this is secondary-source geocoding by locality name, not
primary-source geometry (point-in-polygon against the Election Commission's
actual boundary shapefiles/KMZ, also published on `opendata.spr.gov.my`).
Revisit with a geometric approach if a future session finds postcode-centroid
coordinates and the effort to do proper point-in-polygon against the
Commission's boundaries — that would remove the curation step's manual
verification burden entirely, at the cost of needing a geocoded postcode
centroid dataset this session did not find one of comparably zero-cost and
license-clear.

**Update (#107): nationwide exact-match tier added; full curation still
follow-up work.** Fetching both sources whole (all 16 states/territories,
not just Selangor) confirmed the scaling concern above empirically: of 444
Pos Malaysia towns, only 178 are byte-identical (case/whitespace folded) to
a daerah mengundi string — the rest are overwhelmingly city/district names
one level up from a daerah mengundi ("Johor Bahru", "Kluang", "Alor Setar")
that would need the same per-locality hand-verification the pilot did,
repeated roughly 35x. Rather than wait on that, the build script now has two
tiers: an **exact-match** tier (`auto_match_localities` in
`scripts/build_postcode_seat_index.py`) that needs no human curation at all
— a town name equal to a daerah mengundi string is two sources agreeing, not
a guess — applied across every state, plus the original 7-entry hand-curated
Selangor table kept verbatim (four of those entries, "Semenyih", "Hulu
Langat", "Bandar Baru Bangi", and "Cheras", have no exact match at all and
are unreachable any other way). This took the shipped index from 12
postcodes/2 Seats to 352 postcodes/116 Seats, strictly a superset of the
original 12 — every #76 postcode keeps at least its original Seat(s), which
`tests/test_postcode_index.py` now checks directly rather than trusting by
inspection. The 262 towns that resolve to neither tier are recorded, per
state, in `data/postcode_seat_index_unresolved.json` rather than guessed at
or silently dropped — that file is the concrete starting point for the
follow-up curation this ADR always expected, not a new decision.

Doing this at full scale also surfaced a real correctness gap this ADR's
pilot never exercised: 141 daerah mengundi strings, nationwide, are not
unique within their own state — the identical name appears under two or more
different Parlimen (e.g. Johor's "BUKIT PASIR" under both P.143 Pagoh and
P.150 Batu Pahat). The pilot's own lookup dict was keyed by daerah string and
would have silently kept only one Parlimen for any of these had one been in
scope; at nationwide scale, 6 of the 178 exact-matched towns hit this
directly. `fetch_daerah_to_parlimen_by_state` now keeps every Parlimen a
daerah string resolves to, so these correctly come out multi-Seat — the same
"never a guessed single answer" principle as Cheras, just visible one level
lower than a curated town name. A separate, looser check — whether any *other*
daerah mengundi merely contains an exact-matched town's name as a substring,
under a different Parlimen — found 20 towns with that property, but manual
inspection showed these are the "Penjara Kajang" pattern this ADR already
rejected (e.g. "Sungai Buloh" exact-matches one daerah under P.106, while
"Penjara Sungai Buloh" — a different name entirely — happens to sit under
P.097): coincidental shared wording between distinctly-named daerah, not
evidence of a real boundary split. Those are correctly left as exact-match
singletons, not merged in.

The per-postcode payload size held at ~20 bytes/postcode as predicted (7,157
bytes for 352 postcodes' worth of `postcodes` alone), so the "well under 100
KB uncompressed" estimate for a full ~2,900-postcode index still holds.
