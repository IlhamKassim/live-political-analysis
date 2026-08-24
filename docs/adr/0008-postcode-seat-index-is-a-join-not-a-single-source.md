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
