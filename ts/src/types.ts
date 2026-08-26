// The constituency lookup's state model (issue #77), verbatim from
// design_handoff_politikku/README.md's "State Management" section:
// lookupState: 'idle' | 'locating' | 'searching' | 'ambiguous' | 'notFound' | 'resolved'
//
// 'searching' is momentary in this pilot (the index is already in memory —
// see index-data.ts — so a postcode/name query resolves synchronously) but
// kept as its own state because README names it explicitly and a future,
// larger index may genuinely need an async step here.

export type LookupState =
  | "idle"
  | "locating"
  | "searching"
  | "ambiguous"
  | "notFound"
  | "resolved";

export interface LookupSeat {
  readonly code: string;
  readonly name: string;
  readonly state: string;
  readonly hasProfile: boolean;
  readonly mpName: string | null;
}

// public/data/lookup-index.json's shape — built by
// lpa.politikku_lookup_index.build_client_index. Keep these two in sync by
// hand; there is no shared schema between the Python and TypeScript sides.
export interface ClientLookupIndex {
  readonly seats: Readonly<Record<string, LookupSeat>>;
  readonly postcodes: Readonly<Record<string, readonly string[]>>;
}

export type NoMatchReason =
  | "not-in-index"
  | "geolocation-unsupported"
  | "geolocation-denied"
  | "geolocation-unresolvable"
  | "index-unavailable";

// The result of resolving one query (postcode, name, or a geolocation fix)
// against the index — never more than the model actually knows. `ambiguous`
// and `resolved` both carry `LookupSeat[]`, not just codes, because the
// ambiguous-state UI needs to print a name/MP-name row for each candidate
// and re-deriving that from the index a second time would be Duplicated
// Code for no reason.
export type ResolutionResult =
  | { readonly kind: "resolved"; readonly seat: LookupSeat }
  | { readonly kind: "ambiguous"; readonly candidates: readonly LookupSeat[] }
  | { readonly kind: "notFound"; readonly reason: NoMatchReason };
