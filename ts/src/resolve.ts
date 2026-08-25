// Pure resolution logic against the client index — no DOM, no network, no
// storage. Kept separate from state-machine.ts/dom.ts so the one piece of
// this module that actually decides "which Seat(s) match" is testable
// without mounting anything.

import type { ClientLookupIndex, LookupSeat, ResolutionResult } from "./types";

const POSTCODE = /^\d{5}$/;

/**
 * Resolve a free-text query — a 5-digit postcode or a Seat/constituency
 * name substring — against the index. Mirrors
 * `lpa.postcode_index.lookup_postcode`'s own discipline: zero matches is
 * "not in the index", more than one is genuinely ambiguous, and neither is
 * ever collapsed into a guess.
 *
 * A name match is case-insensitive substring, since this pilot ships two
 * Seat names total and a stricter match would make the search box appear
 * broken for a query like "bangi " (trailing space) or "BANGI".
 */
export function resolveQuery(
  rawQuery: string,
  index: ClientLookupIndex,
): ResolutionResult {
  const query = rawQuery.trim();
  if (POSTCODE.test(query)) {
    return resolveCodes(index.postcodes[query] ?? [], index);
  }
  if (query.length === 0) {
    return { kind: "notFound", reason: "not-in-index" };
  }
  const needle = query.toLowerCase();
  const codes = Object.entries(index.seats)
    .filter(([, seat]) => seat.name.toLowerCase().includes(needle))
    .map(([code]) => code);
  return resolveCodes(codes, index);
}

function resolveCodes(
  codes: readonly string[],
  index: ClientLookupIndex,
): ResolutionResult {
  const seats = codes
    .map((code) => index.seats[code])
    .filter((seat): seat is LookupSeat => seat !== undefined);
  if (seats.length === 0) {
    return { kind: "notFound", reason: "not-in-index" };
  }
  const [only] = seats;
  if (seats.length === 1 && only) {
    return { kind: "resolved", seat: only };
  }
  return { kind: "ambiguous", candidates: seats };
}
