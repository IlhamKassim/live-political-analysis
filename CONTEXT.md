# Live Political Analysis

Tracks current sentiment on the Malaysian political landscape and projects the outcome of the next general election (GE16).

## Language

**Coalition**:
A group of parties that contests and governs together. The five that matter: PH, BN, PN, GPS, GRS.
_Avoid_: Party, alliance, bloc (use Coalition unless specifically distinguishing an individual party within one)

**Seat**:
One of the 222 parliamentary constituencies in the Dewan Rakyat. The unit an election is actually won or lost in.
_Avoid_: Constituency (fine as a synonym, but prefer Seat for consistency), district

**Majority**:
Holding more than half of the 222 seats (112+). The threshold a Coalition needs to form government alone.
_Avoid_: Win (ambiguous — a Coalition can win a plurality without a Majority)

**Government Coalition**:
The current governing bloc — PH + BN + GPS + GRS plus minor parties — holding the Majority as of the most recent Dewan Rakyat count.
_Avoid_: Unity government (fine in prose, but this is the canonical term in code/data)

**Non-government**:
Every Seat or Coalition outside the Government Coalition. Used in preference to "Opposition" because it is exactly true: PN is the opposition, but WARISAN, KDM, PBM and independents are neither in government nor in it, and calling them opposition asserts an alignment they have not declared. The public page's chamber is a single axis from safest-Government to safest Non-government.
_Avoid_: Opposition (fine for PN specifically; wrong as a label for the whole non-government side)

**Baseline**:
A Seat's GE15 (2022) result and demographic profile — vote share, margin, ethnicity/age breakdown of voters. The fixed starting point every Projection is computed from.
_Avoid_: Historical data (too vague — Baseline specifically means the GE15 snapshot per Seat)

**Sentiment**:
The measured public political mood, tagged per Coalition/party, derived from two sources: continuous News Sentiment (see below) and periodic Poll Calibration (see below). The input signal the Swing Model consumes.

**News Sentiment**:
Sentiment computed from an open-source, self-hosted multilingual sentiment model run as local CPU inference (no external API) against headlines/articles scraped from major Malaysian outlets, in English and Bahasa Malaysia alike (FMT, Malay Mail, NST, The Star, The Vibes, Sinar Daily, Bernama, Berita Harian, Utusan Malaysia). The continuous, day-to-day component of Sentiment. Zero-cost by default, not requirement — see ADR 0002, amended by ADR 0007. Which of those are actually read, and why the rest are not, is `data/outlets.json`.

**Poll Calibration**:
Merdeka Center's periodically published survey results (approval ratings, etc.), ingested whenever a new report drops to sanity-check News Sentiment against real survey data. Not continuous — there is no API, reports appear every few months.

**Swing**:
The estimated shift in vote or seat share for a Coalition, derived from Sentiment and applied against the Baseline.

**State Election Signal**:
Results from state elections held before GE16 (e.g. the 2026 Johor and Malacca elections) — a leading-indicator input into the Swing Model. Distinct from the Baseline, which stays fixed at GE15 federal results.

**Election Status**:
Whether GE16 has been called yet, and the polling date once one is set. "Called" means the Dewan Rakyat has been dissolved — the act that starts a Malaysian general election; the Election Commission announces polling afterwards, so called-with-no-polling-date is a real state. Maintained by hand in `data/election_status.json`. Context for reading a Projection, not an input to one.
_Avoid_: Election date (ambiguous — dissolution, nomination and polling are three different days)

**Swing Model**:
The method for turning Sentiment into a per-Seat or per-Coalition Swing — uniform within each state, per ADR 0001, with a State Election Signal blended in for the state that voted. The hard, research-grade part of this project — distinguish from the Baseline, which is just historical fact.

**Projection**:
The tool's output: a seat-count estimate per Coalition for GE16, whether the Government Coalition retains its Majority, and the Seat-Level Projection behind both.

**Seat-Level Projection**:
The Coalition each of the 222 Seats is projected to fall to, with the projected margin, alongside the aggregate totals. Published as of ADR 0005, which supersedes ADR 0001's deferral. The Swing Model is uniform within a state and carries no Seat-specific signal, so a Seat's call is arithmetic against its GE15 margin — never a bespoke judgement about that constituency, and it must not be presented as one.

**Seat Call**:
One Seat's entry in the Seat-Level Projection: the Coalition projected to take it and the projected margin over the runner-up. Named in code as `SeatCall`.
_Avoid_: Prediction, forecast (both imply a precision ADR 0003 says this model does not have)

**Postcode → Seat Index**:
The lookup table behind PolitikKu's constituency lookup (#76): a Malaysian
postcode mapped to every Seat it could fall in. Postcodes are a Pos Malaysia
delivery construct, not an Election Commission unit, so the mapping is
many-to-one and sometimes ambiguous — a postcode can genuinely straddle two
Seats, and the index represents that as multiple candidates rather than
guessing one. Built in `lpa.postcode_index`/`lpa.config.load_postcode_seat_index`
from `data/postcode_seat_index.json`; see ADR 0008 for how it is sourced and
`scripts/build_postcode_seat_index.py` for how it is built.
_Avoid_: treating a postcode as if it names exactly one Seat.

**MP Profile**:
The sitting Member for a Seat and their record this term — identity, Coalition, GE15 result, contact details, Divisions voted in, Bills sponsored (#78). Built in `lpa.mp_profile`/`lpa.config.load_mp_profiles` from `data/mp_profiles.json`; see ADR 0009 for what each official source does and does not publish. A field with no value must say why it has none: the profile carries an `unverified` block naming every unset field and the reason, and the loader rejects a profile that leaves one unexplained. The Member is identified by `seat_code` alone — name, state and demographics for the Seat live on its Baseline.
_Avoid_: Politician, representative (use MP, or Member, matching Parliament's own usage); filling a blank with a plausible value rather than recording why it is blank.

**Division**:
A counted vote in the Dewan Rakyat (*belah bahagian*, Standing Order 46(4)), in which Hansard names every Member as agreeing, disagreeing, abstaining or absent. The only per-Member voting record that exists in Malaysia, and a rare event — most legislation passes on a voice vote that records no individual position at all, and the 15th Parliament held ten Divisions in three and a half years. A short voting record therefore reflects the House, not a gap in ingestion.
_Avoid_: Vote (too broad — a voice vote is a vote and records nobody), roll call.

**Audience**:
Younger Malaysians who first encounter this project's content secondhand — a shared Seat Call card, a screenshot, a repost — rather than by navigating to the dashboard directly, and who are not already politically engaged. The target for #22 (site-literacy) and #23 (shareable cards). Distinct from an existing politically-engaged reader who would seek the dashboard out regardless.
_Avoid_: Users, readers (both too generic — use Audience when the younger, secondhand-discovery reader is specifically meant)

**Return Trigger**:
A real-world event — a news cycle, a state election, GE16 being called, a Projection swing worth noticing — that makes an Audience member who already knows this site come back to it, as opposed to a scheduled habit (there is no daily check-in loop; the site updates once a day per ADR 0006 and has no accounts or push). Retention here means the site is easy to return to and freshest right at a Return Trigger, not that it earns a recurring visit slot.
_Avoid_: Engagement, retention loop, habit (imply a scheduled/compulsive-use pattern this project isn't building toward)
