// Fetches the client lookup index (public/data/lookup-index.json,
// built by lpa.politikku_lookup_index) once and keeps it in memory. This is
// the one network request the lookup module makes — a static same-origin
// file, not a query endpoint, so nothing about *what the visitor typed or
// where they are* ever leaves the browser (the privacy promise this ticket
// keeps applies to the query, not to fetching the index itself).

import type { ClientLookupIndex } from "./types";

let cached: Promise<ClientLookupIndex> | null = null;

export function loadClientIndex(url = "/data/lookup-index.json"): Promise<ClientLookupIndex> {
  cached ??= fetch(url)
    .then((response) => {
      if (!response.ok) {
        throw new Error(`lookup index fetch failed: ${response.status} ${url}`);
      }
      return response.json() as Promise<unknown>;
    })
    .then((data) => assertClientLookupIndex(data, url));
  return cached;
}

// There is no shared schema between the Python side (lpa.politikku_lookup_
// index) and this type — a build that drifted out of sync would otherwise
// fail silently downstream (e.g. `resolveQuery` indexing into `undefined`)
// rather than loudly at the one place this data actually enters the
// module.
function assertClientLookupIndex(data: unknown, url: string): ClientLookupIndex {
  if (
    typeof data !== "object" ||
    data === null ||
    typeof (data as { seats?: unknown }).seats !== "object" ||
    typeof (data as { postcodes?: unknown }).postcodes !== "object"
  ) {
    throw new Error(`${url} is not a valid client lookup index (missing seats/postcodes)`);
  }
  return data as ClientLookupIndex;
}

/** Test-only: clears the module-level cache between test cases. */
export function _resetClientIndexCache(): void {
  cached = null;
}
