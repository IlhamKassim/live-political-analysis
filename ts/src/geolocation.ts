// "Use my location" (issue #77's own scope text): the design's privacy
// promise is "Location is read in your browser and never sent to us," and
// that must hold for real, not just as copy — the ticket says as much
// explicitly. This module does read a real coordinate fix via the browser
// API, but this pilot's index (ADR 0008) has no boundary/geometry data to
// resolve a coordinate against a Seat with — no postcode-centroid table, no
// point-in-polygon shapefile, nothing. Rather than guess or fake a match,
// `locate()` reads the coordinate and then does nothing else with it: no
// fetch, no beacon, no storage of the raw fix, just an honest "not
// supported yet" result. The promise stays true because the coordinate is
// never used for anything, not because the feature was hidden.
//
// The return type is `ResolutionResult` (the same type `resolve.ts`
// returns for a text query) so a future session that ingests real
// boundary data only has to change this function's body — the state
// machine and DOM layer already handle every case that type can carry.

import type { ResolutionResult } from "./types";

export function isGeolocationSupported(): boolean {
  return Boolean(navigator.geolocation);
}

export function locate(): Promise<ResolutionResult> {
  if (!isGeolocationSupported()) {
    return Promise.resolve({ kind: "notFound", reason: "geolocation-unsupported" });
  }
  return new Promise((resolve) => {
    navigator.geolocation.getCurrentPosition(
      () => {
        // A real fix was read. It is intentionally never inspected, never
        // sent over the network, and never written to storage — this
        // pilot has nothing to resolve it against yet (see module
        // docstring above).
        resolve({ kind: "notFound", reason: "geolocation-unresolvable" });
      },
      (error) => {
        const reason =
          error.code === error.PERMISSION_DENIED
            ? "geolocation-denied"
            : "geolocation-unresolvable";
        resolve({ kind: "notFound", reason });
      },
      { maximumAge: 0, timeout: 10_000 },
    );
  });
}
