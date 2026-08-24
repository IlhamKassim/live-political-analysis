// Fetches the client lookup index (public/politikku/data/lookup-index.json,
// built by lpa.politikku_lookup_index) once and keeps it in memory. This is
// the one network request the lookup module makes — a static same-origin
// file, not a query endpoint, so nothing about *what the visitor typed or
// where they are* ever leaves the browser (the privacy promise this ticket
// keeps applies to the query, not to fetching the index itself).

import type { ClientLookupIndex } from "./types";

let cached: Promise<ClientLookupIndex> | null = null;

export function loadClientIndex(url = "/politikku/data/lookup-index.json"): Promise<ClientLookupIndex> {
  cached ??= fetch(url).then((response) => {
    if (!response.ok) {
      throw new Error(`lookup index fetch failed: ${response.status} ${url}`);
    }
    return response.json() as Promise<ClientLookupIndex>;
  });
  return cached;
}

/** Test-only: clears the module-level cache between test cases. */
export function _resetClientIndexCache(): void {
  cached = null;
}
